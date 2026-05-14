# backend/app/services/llm.py
import json
import logging
import os
from typing import Any

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class _Range(BaseModel):
    start: float
    end: float
    reason: str = ""


class _RangesResponse(BaseModel):
    ranges: list[_Range] = Field(default_factory=list)


_SYSTEM_PROMPT = """あなたは動画編集を支援するアシスタントです。
入力された日本語の文字起こし（単語ごとのタイムスタンプ付き）を解析し、
言い直し・噛み・冗長な反復に該当する区間を特定してください。

ルール:
- 言い直し: 同じ内容を直後に別の言い方で繰り返している箇所の最初の発話部分
- 噛み: 言いかけて言い直した断片
- フィラー（「えーっと」「あのー」など）は対象外（別途処理されます）
- 確信が持てない箇所は出力しない（保守的に判断）

出力は必ず以下の JSON 形式で返す:
{"ranges": [{"start": 秒, "end": 秒, "reason": "理由"}, ...]}
削除対象がなければ {"ranges": []} を返す。"""


_CORRECTION_SYSTEM_PROMPT = """あなたは日本語音声認識結果の校正アシスタントです。
入力には字幕セグメントが番号付きで複数行渡されます。Whisper の誤認識・聞き取り抜け・冗長表現が含まれます。

**最重要ルール:**
- 各セグメントは独立した字幕。**他のセグメントの内容を混ぜない**
- 出力テキストは元のセグメントとほぼ同じ長さを維持（短く/長くしすぎない）
- 隣のセグメントから単語を移動・結合しない

**積極的に修正する:**
- 同音異義語の誤認識（金肉→筋肉、営養→栄養、結流→血流 など）
- 明らかなタイポ・カタカナ表記の誤り
- 文中で重複している語の整理（例：「血流の流れが」→「血流が」、「血流を血流を」→「血流を」）
- 文として崩れていて意味が通らない箇所の修復（明らかに抜けた助詞「が／を／は／の」の補完）
- 「しようぜ」→「しよう、なぜ」など、音声認識特有の崩れの修正

**変更してはいけない:**
- セグメントの統合・分割
- 文体・口調の書き換え（敬語・タメ口は維持）
- 内容の追加（無い情報を補わない、推測しない）

**保守原則:**
- 文脈から「これは明らかにこう言ったはず」と確信できる箇所だけ直す
- 判断に迷ったら元のまま残す

入力形式:
[0] テキスト
[1] テキスト
...

出力は必ず以下の JSON 形式で返す（変更が必要なセグメントのみ）:
{"corrections": [{"index": 0, "text": "修正後のテキスト"}, ...]}
変更不要なら {"corrections": []} を返す。"""


def _format_transcript(words: list[dict]) -> str:
    lines = []
    for w in words:
        lines.append(f"[{w['start']:.2f}-{w['end']:.2f}] {w['text']}")
    return "\n".join(lines)


def _call_openai(transcript_text: str, system_prompt: str = _SYSTEM_PROMPT) -> str:
    from openai import OpenAI

    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript_text},
        ],
    )
    return resp.choices[0].message.content or "{}"


def _call_anthropic(transcript_text: str, system_prompt: str = _SYSTEM_PROMPT) -> str:
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=system_prompt + "\n\n応答は JSON オブジェクトのみで返してください。",
        messages=[{"role": "user", "content": transcript_text}],
    )
    text = ""
    for block in resp.content:
        if hasattr(block, "text"):
            text += block.text
    return text or "{}"


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def detect_restatements(words: list[dict]) -> list[dict]:
    """LLM を使って言い直し・噛みの削除区間を抽出する。

    LLM_PROVIDER 環境変数で openai / anthropic を切替。
    未設定・API キー欠落・呼び出し失敗時は空リストを返す（degraded mode）。
    """
    if not words:
        return []

    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider not in ("openai", "anthropic"):
        return []

    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        return []
    if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        return []

    transcript_text = _format_transcript(words)
    min_t = min(w["start"] for w in words)
    max_t = max(w["end"] for w in words)

    try:
        if provider == "openai":
            raw = _call_openai(transcript_text)
        else:
            raw = _call_anthropic(transcript_text)
        payload = _extract_json(raw)
        parsed = _RangesResponse.model_validate(payload)
    except (ValidationError, json.JSONDecodeError, Exception) as e:
        logger.warning("LLM restatement detection failed: %s", e)
        return []

    valid: list[dict] = []
    for r in parsed.ranges:
        if r.end <= r.start:
            continue
        if r.start < min_t or r.end > max_t:
            logger.warning("LLM returned out-of-range: %s-%s", r.start, r.end)
            continue
        valid.append({"start": r.start, "end": r.end})

    return valid


class _CorrectionItem(BaseModel):
    index: int
    text: str


class _CorrectionsResponse(BaseModel):
    corrections: list[_CorrectionItem] = Field(default_factory=list)


def correct_transcript_segments(segments: list[str]) -> list[str]:
    """LLM で字幕セグメントの誤認識を校正する。

    入力と同じ長さのリストを返す。LLM 未設定・失敗時は入力をそのまま返す。
    LLM は変更が必要なインデックスだけを返すので、未指定のセグメントは元の値を維持。
    """
    if not segments:
        return segments

    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider not in ("openai", "anthropic"):
        return segments

    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        return segments
    if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        return segments

    user_message = "\n".join(f"[{i}] {s}" for i, s in enumerate(segments))

    try:
        if provider == "openai":
            raw = _call_openai(user_message, system_prompt=_CORRECTION_SYSTEM_PROMPT)
        else:
            raw = _call_anthropic(user_message, system_prompt=_CORRECTION_SYSTEM_PROMPT)
        payload = _extract_json(raw)
        parsed = _CorrectionsResponse.model_validate(payload)
    except (ValidationError, json.JSONDecodeError, Exception) as e:
        logger.warning("LLM transcript correction failed: %s", e)
        return segments

    result = list(segments)
    applied = 0
    rejected = 0
    for item in parsed.corrections:
        if not (0 <= item.index < len(result)):
            rejected += 1
            continue
        new_text = item.text.strip()
        if not new_text:
            rejected += 1
            continue
        original = segments[item.index]
        # 文字数が元の 2倍超 / 10文字以上長い場合は LLM がセグメントを統合した可能性が高いので破棄
        if len(new_text) > max(int(len(original) * 2.0), len(original) + 10):
            rejected += 1
            logger.warning(
                "LLM correction rejected (too long): idx=%d orig=%d new=%d",
                item.index, len(original), len(new_text),
            )
            continue
        result[item.index] = new_text
        applied += 1
    logger.info(
        "LLM transcript correction: %d applied, %d rejected, %d total",
        applied, rejected, len(segments),
    )
    return result


_KEYWORDS_SYSTEM_PROMPT = """あなたは動画コンテンツのキーワード抽出アシスタントです。
入力された日本語の文字起こしから、視聴者に強調表示すべき重要なキーワードを抽出してください。

ルール:
- 5〜8個のキーワードを返す
- 1キーワードは2〜6文字程度の名詞・複合語が望ましい
- 動画のテーマや核心となる用語を優先（例: 健康系なら「血流」「筋肉」「老廃物」など）
- 助詞・動詞・一般的すぎる語（人・もの・こと等）は除外
- 重複・類義語は1つにまとめる

出力は必ず以下の JSON 形式で返す:
{"keywords": ["キーワード1", "キーワード2", ...]}"""


class _KeywordsResponse(BaseModel):
    keywords: list[str] = Field(default_factory=list)


def extract_keywords(transcript_text: str, max_keywords: int = 8) -> list[str]:
    """LLM で動画の文字起こしから強調すべきキーワードを抽出する。

    LLM 未設定・失敗時は空リストを返す。
    """
    if not transcript_text.strip():
        return []

    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider not in ("openai", "anthropic"):
        return []
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        return []
    if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        return []

    try:
        if provider == "openai":
            raw = _call_openai(transcript_text, system_prompt=_KEYWORDS_SYSTEM_PROMPT)
        else:
            raw = _call_anthropic(transcript_text, system_prompt=_KEYWORDS_SYSTEM_PROMPT)
        payload = _extract_json(raw)
        parsed = _KeywordsResponse.model_validate(payload)
    except (ValidationError, json.JSONDecodeError, Exception) as e:
        logger.warning("LLM keyword extraction failed: %s", e)
        return []

    # 重複除去・空文字除外・最大数制限
    seen: set[str] = set()
    result: list[str] = []
    for kw in parsed.keywords:
        kw = kw.strip()
        if kw and kw not in seen:
            seen.add(kw)
            result.append(kw)
        if len(result) >= max_keywords:
            break
    logger.info("LLM keyword extraction: %d keywords (%s)", len(result), ", ".join(result))
    return result


_GENERATE_HOOK_SYSTEM_PROMPT = """あなたは TikTok・Instagram Reels の動画フック生成アシスタントです。
入力された動画の文字起こしを読み、視聴者を3秒で釘付けにする「冒頭フック」テキストを1つだけ生成してください。

ルール:
- 動画の核心を凝縮した1文（12〜25文字）
- 「99%が知らない」「実は◯◯」「◯◯した結果...」などのテンプレを参考に
- 数字・意外性・断定形を使うと効果的
- 動画の内容と整合する（嘘・誇大表現はNG）

出力は必ず以下の JSON 形式で返す:
{"hook": "フックテキスト"}"""


class _HookResponse(BaseModel):
    hook: str = ""


def generate_hook(transcript_text: str) -> str:
    """LLM で動画の冒頭フックテキストを生成する。

    LLM 未設定・失敗時は空文字を返す。
    """
    if not transcript_text.strip():
        return ""

    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider not in ("openai", "anthropic"):
        return ""
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        return ""
    if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        return ""

    try:
        if provider == "openai":
            raw = _call_openai(transcript_text, system_prompt=_GENERATE_HOOK_SYSTEM_PROMPT)
        else:
            raw = _call_anthropic(transcript_text, system_prompt=_GENERATE_HOOK_SYSTEM_PROMPT)
        payload = _extract_json(raw)
        parsed = _HookResponse.model_validate(payload)
    except (ValidationError, json.JSONDecodeError, Exception) as e:
        logger.warning("LLM hook generation failed: %s", e)
        return ""

    hook = parsed.hook.strip()
    if hook:
        logger.info("LLM hook generated: %s", hook)
    return hook


_TOPICS_SYSTEM_PROMPT = """あなたは動画コンテンツの構造化アシスタントです。
入力された日本語の文字起こしを 2〜4個の「ポイント／章」に分割し、画面に「①②③」と番号表示するための情報を返してください。

ルール:
- ポイントは話の論理的な区切りで分ける（例: 「問題提起」「原因」「解決策」など）
- 各ポイントには 8文字以内の短いラベルを付ける
- start_seg は分割の開始セグメント番号（入力の [N] の N）
- 動画が短すぎる or 単一トピックの場合は分割しない

入力形式:
[0] テキスト
[1] テキスト
...

出力は必ず以下の JSON 形式で返す:
{"topics": [{"index": 1, "start_seg": 0, "label": "原因"}, ...]}
分割不要なら {"topics": []}"""


class _TopicItem(BaseModel):
    index: int
    start_seg: int
    label: str = ""


class _TopicsResponse(BaseModel):
    topics: list[_TopicItem] = Field(default_factory=list)


def detect_topics(segments: list[str], max_topics: int = 4) -> list[dict]:
    """LLM で動画から話のポイント（章）を検出する。

    Args:
        segments: 字幕セグメントのテキストリスト
        max_topics: 最大ポイント数

    Returns:
        [{"index": int, "start_seg": int, "label": str}, ...] 失敗時は []
    """
    if not segments:
        return []

    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider not in ("openai", "anthropic"):
        return []
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        return []
    if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        return []

    user_message = "\n".join(f"[{i}] {s}" for i, s in enumerate(segments))

    try:
        if provider == "openai":
            raw = _call_openai(user_message, system_prompt=_TOPICS_SYSTEM_PROMPT)
        else:
            raw = _call_anthropic(user_message, system_prompt=_TOPICS_SYSTEM_PROMPT)
        payload = _extract_json(raw)
        parsed = _TopicsResponse.model_validate(payload)
    except (ValidationError, json.JSONDecodeError, Exception) as e:
        logger.warning("LLM topic detection failed: %s", e)
        return []

    result: list[dict] = []
    for t in parsed.topics:
        if not (0 <= t.start_seg < len(segments)):
            continue
        result.append({
            "index": t.index,
            "start_seg": t.start_seg,
            "label": t.label.strip()[:12],
        })
        if len(result) >= max_topics:
            break
    result.sort(key=lambda x: x["start_seg"])
    logger.info("LLM topic detection: %d topics", len(result))
    return result


_BGM_STYLE_SYSTEM_PROMPT = """あなたは動画の雰囲気から最適な BGM スタイルを選定するアシスタントです。
入力された日本語の文字起こしを読み、3種類の中から最適なBGMを1つ選んでください。

選択肢:
- "calm": 落ち着いた・解説・教育系・健康系
- "upbeat": 明るい・エンタメ・テンポ重視・モチベーション
- "focused": ビジネス・ニュース・集中系・真面目

出力は必ず以下の JSON 形式で返す:
{"style": "calm"}"""


class _BgmStyleResponse(BaseModel):
    style: str = ""


def select_bgm_style(transcript_text: str) -> str:
    """LLM で動画の雰囲気に合った BGM スタイルを選定する。

    Returns:
        "calm" | "upbeat" | "focused" | "" (失敗・未設定時)
    """
    if not transcript_text.strip():
        return ""

    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider not in ("openai", "anthropic"):
        return ""
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        return ""
    if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        return ""

    try:
        if provider == "openai":
            raw = _call_openai(transcript_text, system_prompt=_BGM_STYLE_SYSTEM_PROMPT)
        else:
            raw = _call_anthropic(transcript_text, system_prompt=_BGM_STYLE_SYSTEM_PROMPT)
        payload = _extract_json(raw)
        parsed = _BgmStyleResponse.model_validate(payload)
    except (ValidationError, json.JSONDecodeError, Exception) as e:
        logger.warning("LLM BGM style selection failed: %s", e)
        return ""

    style = parsed.style.strip().lower()
    if style not in ("calm", "upbeat", "focused"):
        return ""
    logger.info("LLM BGM style: %s", style)
    return style


_CAPTIONS_SYSTEM_PROMPT = """あなたは TikTok / Instagram Reels の投稿文を作成するアシスタントです。
入力された日本語の文字起こしから、それぞれのプラットフォームに最適化された投稿文とハッシュタグを生成してください。

ルール:
- **tiktok_caption**: TikTok向け。煽り強め、絵文字多用、120文字以内、改行可
- **instagram_caption**: Instagram向け。落ち着き目、教育的、200文字以内、改行可、最後にCTA
- **hashtags**: 10〜15個、日本語＋英語混在OK、人気＋ニッチタグの混合、#つき
- 動画内容と整合（誇大表現はNG）
- 文字数を厳密に守る

出力は必ず以下の JSON 形式で返す:
{
  "tiktok_caption": "...",
  "instagram_caption": "...",
  "hashtags": "#tag1 #tag2 ..."
}"""


class _CaptionsResponse(BaseModel):
    tiktok_caption: str = ""
    instagram_caption: str = ""
    hashtags: str = ""


def generate_captions(transcript_text: str) -> dict[str, str]:
    """LLM で TikTok / Instagram 用のキャプションとハッシュタグを生成する。

    Returns:
        {"tiktok_caption": str, "instagram_caption": str, "hashtags": str}
        失敗・未設定時は全て空文字。
    """
    empty = {"tiktok_caption": "", "instagram_caption": "", "hashtags": ""}
    if not transcript_text.strip():
        return empty

    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider not in ("openai", "anthropic"):
        return empty
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        return empty
    if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        return empty

    try:
        if provider == "openai":
            raw = _call_openai(transcript_text, system_prompt=_CAPTIONS_SYSTEM_PROMPT)
        else:
            raw = _call_anthropic(transcript_text, system_prompt=_CAPTIONS_SYSTEM_PROMPT)
        payload = _extract_json(raw)
        parsed = _CaptionsResponse.model_validate(payload)
    except (ValidationError, json.JSONDecodeError, Exception) as e:
        logger.warning("LLM captions generation failed: %s", e)
        return empty

    result = {
        "tiktok_caption": parsed.tiktok_caption.strip(),
        "instagram_caption": parsed.instagram_caption.strip(),
        "hashtags": parsed.hashtags.strip(),
    }
    logger.info(
        "LLM captions generated: TikTok %d chars, IG %d chars, %d hashtags",
        len(result["tiktok_caption"]),
        len(result["instagram_caption"]),
        result["hashtags"].count("#"),
    )
    return result


_BUZZ_SCORE_SYSTEM_PROMPT = """あなたは TikTok / Reels のバズり予測アシスタントです。
入力された動画の文字起こしを読み、8つの軸で 0-10 点評価し、改善案も提示してください。

評価軸:
- hook: 冒頭3秒で釘付けになるか
- clarity: テーマの明確さ
- density: 情報密度（飽きずに見られるか）
- structure: 構造（起承転結、ポイント整理）
- cta: 視聴後の行動誘導
- pace: テンポ（カット・間）
- searchability: トレンドワード・検索性
- length_fit: プラットフォーム適合（30〜90秒推奨）

各軸は 0-10 の整数。総合は8軸の平均（小数1桁）。

出力は必ず以下の JSON 形式で返す:
{
  "overall": 7.6,
  "scores": {"hook": 9, "clarity": 8, ...},
  "strengths": ["強み1", "強み2", ...],
  "weaknesses": ["改善点1", "改善点2", ...],
  "suggestions": ["具体的アクション1", "具体的アクション2", ...]
}

strengths は最大3個、weaknesses は最大4個、suggestions は最大4個、優先順に並べる。"""


class _ScoresDetail(BaseModel):
    hook: int = 0
    clarity: int = 0
    density: int = 0
    structure: int = 0
    cta: int = 0
    pace: int = 0
    searchability: int = 0
    length_fit: int = 0


class _BuzzScoreResponse(BaseModel):
    overall: float = 0.0
    scores: _ScoresDetail = Field(default_factory=_ScoresDetail)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


def predict_buzz_score(transcript_text: str) -> dict | None:
    """LLM で動画のバズり予測スコアと改善案を生成する。

    Returns:
        dict (overall, scores, strengths, weaknesses, suggestions) or None on failure.
    """
    if not transcript_text.strip():
        return None

    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider not in ("openai", "anthropic"):
        return None
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        return None
    if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        return None

    try:
        if provider == "openai":
            raw = _call_openai(transcript_text, system_prompt=_BUZZ_SCORE_SYSTEM_PROMPT)
        else:
            raw = _call_anthropic(transcript_text, system_prompt=_BUZZ_SCORE_SYSTEM_PROMPT)
        payload = _extract_json(raw)
        parsed = _BuzzScoreResponse.model_validate(payload)
    except (ValidationError, json.JSONDecodeError, Exception) as e:
        logger.warning("LLM buzz score prediction failed: %s", e)
        return None

    result = {
        "overall": round(float(parsed.overall), 1),
        "scores": parsed.scores.model_dump(),
        "strengths": parsed.strengths[:3],
        "weaknesses": parsed.weaknesses[:4],
        "suggestions": parsed.suggestions[:4],
    }
    logger.info("LLM buzz score: %.1f / 10", result["overall"])
    return result
