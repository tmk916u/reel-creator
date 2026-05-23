"""LLM Director: トップダウン編集サービス.

OpenSpec: llm-director-editor

LLM に transcript 全文を渡し、 リール用に残すべき clips リストを取得する。
clips は時系列順 (LLM が入れ替えても sort で正規化) で、 整体院動画のような
静的な被写体ではジャンプカットが目立たない。

clips を既存パイプラインの voice_segments 構築に橋渡しすることで、
silence 削除・字幕生成・loudnorm 等の演出層を全部再利用できる。
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


class Clip(TypedDict):
    start: float
    end: float
    role: str
    order: int
    text: str


_VALID_ROLES = {"intro", "main", "supplement", "cta", "hook", "reason", "example"}

DIRECTOR_SYSTEM_PROMPT = """\
あなたは TikTok/Instagram Reels の動画編集 AI ディレクターです。
整体院の話者が話す動画 transcript を読み、 50〜80 秒の縦動画リールに
再構成してください。

**重要なルール**:
- 動画の時系列を入れ替えてはいけない (input transcript の出現順を維持)
- 合計尺は **最低 50 秒、 目標 60 秒以上**
- 元 transcript から「残すべき区間」 を選び、 順番はそのまま

**🚫 重複絶対禁止 (最重要)**:
- 同じ内容の発話が transcript に複数回登場しても、 clip では **必ず 1 回だけ** 採用する
- 例: 「お客様が悩まれているダイエットの食事の話をしようと思います」 が transcript の
  20-32秒 と 30-46秒 に 2 回出てくる場合、 どちらか 1 つ (短い方や状態の良い方) だけ採用
- 「結論から言うと」「一番大事なのは健康です」 等の主張も transcript 内で繰り返されていれば 1 回のみ
- 重複統合で尺が短くなっても、 50 秒を満たすために重複を入れてはいけない
- 50 秒に満たない場合は他の発話 (理由・具体例) を増やして埋める

削除すべき発話:
- 言い直し、 噛み、 フィラー (「えー」「あの」)
- 同じ内容の繰り返し (上記参照、 必ず 1 回まで)
- 結論につながらない雑談
- 長い間 (3 秒以上の無発話)

残すべき発話:
- 結論・主張 (「一番大事なのは○○」)
- 理由・根拠 ・具体例
- 締めくくり・行動喚起

返り値は **必ず JSON** で、 transcript 内の時刻範囲を指定すること。
範囲外の時刻や、 transcript にない発話を含めてはいけない。

出力 JSON 形式:
{
  "clips": [
    {
      "start": <float, transcript 内の開始時刻 (秒)>,
      "end": <float, transcript 内の終了時刻 (秒, start より大)>,
      "role": "intro" | "main" | "supplement" | "cta",
      "text": "<該当区間の発話の要約>"
    },
    ...
  ],
  "summary": "全体の構成意図を 1 文で"
}

注意:
- clips は time-sorted (start が小さい順) で並んでいなければならない
- 順序入れ替えなし
- clips の合計尺 (Σ end-start) は 50〜80 秒
- 50 秒未満なら追加で残すべき発話を含めて伸ばすこと
"""


def _format_segments_for_prompt(segments: list[dict]) -> str:
    lines = []
    for i, s in enumerate(segments, 1):
        lines.append(f"{i}. [{s['start']:.2f}-{s['end']:.2f}] {s['text']}")
    return "\n".join(lines)


def _extract_json(text: str) -> dict[str, Any]:
    """LLM 応答から JSON を抽出 (code fence 除去)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]
    return json.loads(text)


def _call_llm(user_prompt: str, system_prompt: str = DIRECTOR_SYSTEM_PROMPT) -> str:
    """既存パターンに合わせて OpenAI / Anthropic を切り替えて呼ぶ。"""
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    if provider == "openai":
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model=os.environ.get("DIRECTOR_OPENAI_MODEL", "gpt-4o"),
            response_format={"type": "json_object"},
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content or "{}"
    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=os.environ.get("DIRECTOR_ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            max_tokens=4096,
            temperature=0,
            system=system_prompt + "\n\n応答は JSON オブジェクトのみで返してください。",
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                text += block.text
        return text or "{}"
    else:
        raise RuntimeError(f"Unknown LLM_PROVIDER: {provider}")


def _validate_clips(raw_clips: list[Any], duration: float) -> list[Clip]:
    """範囲外・不正な clip を破棄し、 時系列順に並べる。"""
    valid: list[Clip] = []
    for c in raw_clips:
        if not isinstance(c, dict):
            continue
        try:
            start = float(c["start"])
            end = float(c["end"])
            role = str(c.get("role", "")).lower()
            text = str(c.get("text", ""))
        except (KeyError, ValueError, TypeError) as e:
            logger.warning("director clip 破棄 (parse): %s -> %s", c, e)
            continue
        if start < 0 or end > duration + 0.5 or start >= end:
            logger.warning(
                "director clip 破棄 (range): start=%.2f end=%.2f dur=%.2f",
                start, end, duration,
            )
            continue
        if role not in _VALID_ROLES:
            logger.warning("director clip 破棄 (role): %s", role)
            continue
        # transcript 範囲を超える end を clamp
        end_clamped = min(end, duration)
        valid.append({
            "start": start,
            "end": end_clamped,
            "role": role,
            "order": 0,  # 下で振り直す
            "text": text,
        })
    valid.sort(key=lambda c: c["start"])
    for i, c in enumerate(valid, 1):
        c["order"] = i
    return valid


def _normalize_for_dedup(text: str) -> str:
    """重複判定用に text を正規化 (空白・記号除去)."""
    return re.sub(r"[\s、。!?,.・　「」『』ー〜]+", "", text)


def _text_similarity(a: str, b: str) -> float:
    """2 つの text の文字 3-gram Jaccard 類似度 (短い方を基準).

    短い方の n-gram のうち長い方に含まれる割合を返す。
    重複検出に十分な精度で計算が軽い。
    """
    na = _normalize_for_dedup(a)
    nb = _normalize_for_dedup(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(shorter) < 3:
        # 短すぎる text は substring 完全一致で判定
        return 1.0 if shorter in longer else 0.0
    ngrams = [shorter[i:i + 3] for i in range(len(shorter) - 2)]
    hits = sum(1 for g in ngrams if g in longer)
    return hits / len(ngrams)


def _dedupe_clips(
    clips: list[Clip],
    similarity_threshold: float = 0.6,
    max_time_gap: float = 30.0,
) -> list[Clip]:
    """LLM が「重複は 1 回」 ルールを守らなかった場合の後処理。

    各 clip pair で text 類似度を見て、 類似 (≥ threshold) かつ近接
    (time gap ≤ max_time_gap) のものは後発を破棄する。 これにより
    「お客様が悩まれているダイエット」 を 3 回繰り返すような出力を防ぐ。

    Args:
        clips: validate 済み clip list (時系列順)
        similarity_threshold: この値以上の類似度で重複と判定 (0.0-1.0)
        max_time_gap: この秒数以内の近接 clip 同士のみ重複扱い (離れた繰り返しは別話題の可能性)

    Returns:
        重複除去後の clip list (時系列順、 order を 1 から振り直す)
    """
    if len(clips) < 2:
        return list(clips)
    kept: list[Clip] = [dict(clips[0])]  # type: ignore[arg-type]
    dropped_count = 0
    for c in clips[1:]:
        # 既に採用した clips の中で最も近接するものと比較
        time_gap = c["start"] - kept[-1]["end"]
        sim = _text_similarity(kept[-1]["text"], c["text"])
        if sim >= similarity_threshold and time_gap <= max_time_gap:
            logger.info(
                "director dedup: 破棄 clip (sim=%.2f, gap=%.1fs): %r ≈ %r",
                sim, time_gap, kept[-1]["text"][:30], c["text"][:30],
            )
            dropped_count += 1
            continue
        kept.append(dict(c))  # type: ignore[arg-type]
    if dropped_count:
        for i, c in enumerate(kept, 1):
            c["order"] = i
    return kept


def design_story(
    segments: list[dict],
    duration: float,
    video_context: str = "",
    target_duration_min: float = 30.0,
    target_duration_max: float = 90.0,
) -> list[Clip]:
    """LLM director に投げて clips を返す。

    失敗時 (LLM エラー、 JSON 不正、 全 clip 破棄、 合計尺範囲外) は空 list を
    返す。 呼出側はこれを検知して rule_based にフォールバックする。

    Args:
        segments: ASR の segment リスト [{start, end, text}]
        duration: 元動画の総尺 (秒)
        video_context: summarize_with_mishearings の文脈サマリー (オプション)
        target_duration_min: 出力尺の下限 (秒)
        target_duration_max: 出力尺の上限 (秒)

    Returns:
        valid clips の list (時系列順)。 失敗時は空 list。
    """
    if not segments:
        logger.info("director: segments が空、 スキップ")
        return []

    transcript_text = _format_segments_for_prompt(segments)
    context_block = f"[動画の文脈]\n{video_context}\n\n" if video_context else ""
    user_prompt = (
        f"動画の総尺: {duration:.1f} 秒\n"
        f"目標尺: {target_duration_min:.0f}〜{target_duration_max:.0f} 秒のリール\n\n"
        f"{context_block}"
        f"[transcript (segment 単位、 時刻付き)]\n{transcript_text}\n\n"
        f"上記から、 リール構造に従って残すべき clips を JSON で返してください。"
    )

    try:
        raw = _call_llm(user_prompt)
    except Exception as e:
        logger.exception("director: LLM 呼出失敗: %s", e)
        return []

    try:
        data = _extract_json(raw)
    except Exception as e:
        logger.warning("director: JSON 解析失敗: %s\nraw=%r", e, raw[:500])
        return []

    raw_clips = data.get("clips") if isinstance(data, dict) else None
    if not isinstance(raw_clips, list):
        logger.warning("director: clips フィールド欠落 or 型違反: %r", type(raw_clips))
        return []

    clips = _validate_clips(raw_clips, duration)
    if not clips:
        logger.warning("director: 有効な clip が 0 個 (全 %d 破棄)", len(raw_clips))
        return []

    # LLM が「重複は 1 回」 ルールを守らないケースの後処理
    pre_dedup = len(clips)
    clips = _dedupe_clips(clips)
    if len(clips) < pre_dedup:
        logger.info(
            "director: 重複除去 %d → %d clips",
            pre_dedup, len(clips),
        )

    total = sum(c["end"] - c["start"] for c in clips)
    if total < target_duration_min - 5 or total > target_duration_max + 10:
        logger.warning(
            "director: 合計尺 %.1fs が範囲 [%.0f-%.0f] 外、 フォールバック",
            total, target_duration_min, target_duration_max,
        )
        return []

    summary = data.get("summary", "") if isinstance(data, dict) else ""
    logger.info(
        "director: %d clips, total=%.1fs, summary=%s",
        len(clips), total, summary[:80],
    )
    return clips


def snap_clips_to_words(clips: list[Clip], words: list[dict]) -> list[Clip]:
    """各 clip の [start, end] を word 境界に snap する。

    word の途中で動画が切れて音声が途切れる現象を防ぐ。
    word リストが空なら clips をそのまま返す (snap 不能)。
    """
    if not words:
        return list(clips)
    word_starts = [w["start"] for w in words]
    word_ends = [w["end"] for w in words]
    out: list[Clip] = []
    for c in clips:
        # clip.start 以前の最も近い word.start
        candidates_start = [s for s in word_starts if s <= c["start"]]
        snapped_start = max(candidates_start) if candidates_start else c["start"]
        # clip.end 以後の最も近い word.end
        candidates_end = [e for e in word_ends if e >= c["end"]]
        snapped_end = min(candidates_end) if candidates_end else c["end"]
        if snapped_end > snapped_start + 0.1:
            new = dict(c)
            new["start"] = snapped_start
            new["end"] = snapped_end
            out.append(new)  # type: ignore[arg-type]
    return out


def clips_to_voice_segments(
    clips: list[Clip],
    silences: list[dict],
) -> list[dict]:
    """clips から voice_segments を構築する。 各 clip と silero VAD silences の
    差集合 (clip ∩ ¬silences) を計算し、 実発話区間だけを残す。

    Returns:
        voice_segments [{"start", "end"}] (時系列順、 重複なし)
    """
    if not clips:
        return []
    voices: list[dict] = []
    sorted_silences = sorted(silences, key=lambda s: s["start"])
    for c in clips:
        cur_start = c["start"]
        cur_end = c["end"]
        # clip 範囲内の silences を順に取り出して切り出す
        for s in sorted_silences:
            if s["end"] <= cur_start:
                continue
            if s["start"] >= cur_end:
                break
            # overlap あり
            overlap_start = max(s["start"], cur_start)
            overlap_end = min(s["end"], cur_end)
            # silence 前の発話を voice として確定
            if overlap_start > cur_start + 0.05:
                voices.append({"start": cur_start, "end": overlap_start})
            cur_start = max(cur_start, overlap_end)
        # 末尾の発話
        if cur_end > cur_start + 0.05:
            voices.append({"start": cur_start, "end": cur_end})
    return voices
