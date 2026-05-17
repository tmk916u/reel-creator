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


_SYSTEM_PROMPT = """あなたは動画編集の冗長削除アシスタントです。
入力された日本語の文字起こし（単語ごとのタイムスタンプ付き）を解析し、
動画の流れから削除すべき**冗長な区間**を特定してください。

**削除対象（積極的に検出）:**
1. **言い直し（直後リフレーズ）**: 同じ内容を直後に別の言い方で繰り返している前半
   例:「健康に良いんですよ、体に良いんですね」→ 前半「健康に良いんですよ、」を削除
2. **同じ話の二回目（数十秒〜数分後）**: 動画内で前に話した内容を、ほぼ同じ趣旨で再度繰り返している箇所（後半を削除）
   例: 30秒目で「血流が大事です」と言い、90秒目で「血流が大事なんですよ」と再び言う → 90秒目側を削除
3. **噛み・言いかけ**: 「整体院、いや整体を」のような断片
4. **冗長な反復**: 同じ単語/フレーズを3回以上連続している箇所の重複部分

**特に注意（自撮り動画の典型パターン）:**
- スマホ自撮りでは「前半で要点を話す → 中盤で詳細 → **後半で再度同じ要点をまとめる**」構成が多い。
  後半の「まとめパート」が前半の言い直しになっていたら、まとめ側を削除候補に。
- 「言い直し」は前半削除、「2回目のまとめ」は後半削除、という区別を意識する。
- 動画の前半 30% と後半 30% で同じトピックが現れた場合、後半を疑う。

**対象外:**
- フィラー（「えーっと」「あのー」）は別途処理されるので無視
- 強調のための意図的な反復（例:「絶対、絶対大事です」）は保護
- 異なる文脈での偶然の重複（同じ単語が違う話の中で出てくる）は保護

**判断基準:**
- 「ほぼ同じ意味」を機械的にチェックするのではなく、視聴者として「これ前にも聞いた」と思う箇所だけを対象に
- 削除して動画が壊れない（前後がつながる）ことを確認

出力は必ず以下の JSON 形式で返す:
{"ranges": [{"start": 秒, "end": 秒, "reason": "理由"}, ...]}
削除対象がなければ {"ranges": []} を返す。"""


_CORRECTION_SYSTEM_PROMPT = """あなたは日本語動画字幕の校正・編集アシスタントです。
入力は番号付きの字幕セグメント。Whisper の誤認識・崩れた日本語・冗長表現を含むので、
**視聴者が読みやすい自然な日本語**に改善してください。意訳OK（音声と完全一致でなくて良い）。

**目的:** ネイティブの視聴者が読んで違和感のない自然な字幕。

**積極的に改善:**
- 同音異義語の誤認識（金肉→筋肉、結流→血流 など）
- 不自然な日本語を自然に書き換え
  例:「血流が悪くなり筋肉の状態が良くないというのは」→「血流が悪いと筋肉も硬くなる」
- 冗長な部分を簡潔に（同じ語の繰り返し、フィラー、言い直しの整理）
- 抜けた助詞・主語の補完
- 砕けた口語の整理（「ですね」を文末に整える程度）
- **句読点の補完**: ASR は句読点が抜けがち。意味の区切りに必要なら読点(、)や句点(。)を追加して読みやすくする

**意訳の範囲（要約・簡潔化OK）:**
- 元の意味を保ったまま短く言い換え
- 動画のトーン・話者の口調は維持（敬語/タメ口は揃える）
- 専門用語・固有名詞は変えない

**変更してはいけない:**
- 内容の主張・結論・数字を改変
- 嘘・誇大表現の追加
- セグメントの統合・分割（番号は維持）
- 隣のセグメントから単語を移動

**長さ制約:**
- 各セグメントは元のセグメントの -50% 〜 +30% 程度の長さ
- 大きく増やさない（読み切れなくなる）

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


class _SummaryResponse(BaseModel):
    summary: str = ""


def summarize_with_mishearings(transcript_text: str) -> tuple[str, dict[str, str]]:
    """動画 transcript から (summary, dynamic_corrections) を返す。

    1回の LLM 呼出で「動画の核心要約」+「この動画固有の誤認識ペア辞書」を
    同時に取得する。動的辞書(dynamic_corrections)はそのジョブ内で
    apply_corrections_to_text に渡され、辞書ファイル(jp_corrections.txt)を
    手書きで増やさなくても動画ごとに最適化された補正が効く(イタチごっこ対策)。

    LLM 未設定・失敗時は ("", {}) を返す。
    """
    if not transcript_text.strip():
        return "", {}
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider not in ("openai", "anthropic"):
        return "", {}
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        return "", {}
    if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        return "", {}

    text = transcript_text[:1500]
    try:
        if provider == "openai":
            raw = _call_openai(text, system_prompt=_SUMMARIZE_AND_MISHEAR_PROMPT)
        else:
            raw = _call_anthropic(text, system_prompt=_SUMMARIZE_AND_MISHEAR_PROMPT)
        payload = _extract_json(raw)
        parsed = _ContextWithMishearingsResponse.model_validate(payload)
    except (ValidationError, json.JSONDecodeError, Exception) as e:
        logger.warning("Video context+mishearings failed: %s", e)
        return "", {}

    summary = parsed.summary.strip()
    mishearings: dict[str, str] = {}
    for item in parsed.likely_mishearings:
        w = item.wrong.strip()
        r = item.right.strip()
        # 1-6文字の短い置換単位のみ採用、助詞だけ等は除外
        if w and r and w != r and 1 <= len(w) <= 6 and 1 <= len(r) <= 8:
            mishearings[w] = r
    if summary:
        logger.info("Video context summary: %s", summary)
    if mishearings:
        sample = ", ".join(f"{w}→{r}" for w, r in list(mishearings.items())[:5])
        logger.info("Video-specific mishearings (%d): %s", len(mishearings), sample)
    return summary, mishearings


def summarize_video_context(transcript_text: str) -> str:
    """後方互換: summary のみ返す。新規呼出は summarize_with_mishearings を推奨。"""
    summary, _ = summarize_with_mishearings(transcript_text)
    return summary


def correct_transcript_segments(segments: list[str], video_context: str = "") -> list[str]:
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
    correction_prompt = _with_context(_CORRECTION_SYSTEM_PROMPT, video_context)

    try:
        if provider == "openai":
            raw = _call_openai(user_message, system_prompt=correction_prompt)
        else:
            raw = _call_anthropic(user_message, system_prompt=correction_prompt)
        payload = _extract_json(raw)
        parsed = _CorrectionsResponse.model_validate(payload)
    except (ValidationError, json.JSONDecodeError, Exception) as e:
        logger.warning("LLM transcript correction failed: %s", e)
        return segments

    result = list(segments)
    applied = 0
    rejected = 0
    rejected_indices: list[int] = []
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
            rejected_indices.append(item.index)
            logger.warning(
                "LLM correction rejected (too long): idx=%d orig=%d new=%d",
                item.index, len(original), len(new_text),
            )
            continue
        result[item.index] = new_text
        applied += 1

    # rejected を「控えめ校正」プロンプトで再試行（誤字のみ、意訳禁止）
    retry_applied = 0
    if rejected_indices:
        retry_segs = [(i, segments[i]) for i in rejected_indices]
        retry_user = "\n".join(f"[{n}] {s}" for n, (_, s) in enumerate(retry_segs))
        retry_prompt = _with_context(_CORRECTION_RETRY_PROMPT, video_context)
        try:
            if provider == "openai":
                raw2 = _call_openai(retry_user, system_prompt=retry_prompt)
            else:
                raw2 = _call_anthropic(retry_user, system_prompt=retry_prompt)
            payload2 = _extract_json(raw2)
            parsed2 = _CorrectionsResponse.model_validate(payload2)
            for it in parsed2.corrections:
                if not (0 <= it.index < len(retry_segs)):
                    continue
                orig_idx, original = retry_segs[it.index]
                new_text = it.text.strip()
                if not new_text:
                    continue
                # 控えめモードでは元の長さ +5 文字以内のみ採用
                if len(new_text) > len(original) + 5:
                    continue
                result[orig_idx] = new_text
                retry_applied += 1
        except Exception as e:
            logger.warning("LLM transcript correction retry failed: %s", e)

    logger.info(
        "LLM transcript correction: %d applied, %d rejected, %d retry-applied, %d total",
        applied, rejected, retry_applied, len(segments),
    )
    return result


_SUMMARIZE_CONTEXT_PROMPT = """あなたは動画の文脈把握アシスタントです。
入力された日本語の動画 transcript(誤認識を含む可能性あり)を読み、
**動画の核心を 1〜2 文(80文字以内)** で要約してください。

要約は後続の校正・字幕生成・HOOK 生成 LLM が「この動画は何の話か」を
理解するための文脈情報として使われます。話者の専門・トピック・主張を
具体的に書く(例:「整体師が食事と健康の関係について解説。暴飲暴食を翌日
リセットすることが大切と主張」)。

出力 JSON: {"summary": "..."}"""


_SUMMARIZE_AND_MISHEAR_PROMPT = """あなたは動画の文脈把握 + 誤認識検出アシスタントです。
入力された日本語の動画 transcript(ASR 出力で誤認識を含む可能性あり)を読み、
以下を JSON で返してください。

1. **summary**: 動画の核心を 1〜2 文(80文字以内)で要約。
   後続の校正・字幕・HOOK 生成 LLM が「この動画は何の話か」を理解する
   ための文脈情報として使う。話者の専門・トピック・主張を具体的に書く。

2. **likely_mishearings**: この動画固有の誤認識候補リスト。
   ASR が音響的に近い別語を出した可能性のあるペアを
   {"wrong":"誤認識","right":"正解"} の形で挙げる。
   例:
   - 整体の話で「収走」が出てきたら {"wrong":"収走","right":"愁訴"}
   - ダイエットの話で「折った」が出てきたら {"wrong":"折った","right":"食べた"}
   ルール:
   - 文脈から **明らかに誤り** と判断できるもののみ
   - 0〜10 個程度。自信が無いものは含めない
   - 短い置換単位(1〜6文字)を優先(長い文の置換は副作用が大きい)
   - 助詞だけ・句読点だけの置換は禁止

出力 JSON:
{
  "summary": "...",
  "likely_mishearings": [{"wrong": "...", "right": "..."}, ...]
}"""


class _MishearingItem(BaseModel):
    wrong: str = ""
    right: str = ""


class _ContextWithMishearingsResponse(BaseModel):
    summary: str = ""
    likely_mishearings: list[_MishearingItem] = Field(default_factory=list)


def _with_context(system_prompt: str, video_context: str) -> str:
    """system_prompt の末尾に「動画の文脈」を追加する。

    文脈は誤認識を補正したり、自然な表現を選ぶための補助情報として
    LLM に渡る。video_context が空なら system_prompt をそのまま返す。
    """
    if not video_context:
        return system_prompt
    return (
        f"{system_prompt}\n\n"
        f"# この動画の文脈(必ず参考にする)\n"
        f"{video_context}\n\n"
        f"判断に迷う誤認識・不自然な表現があれば、上記文脈に合う表現を選んでください。"
    )


_CORRECTION_RETRY_PROMPT = """あなたは日本語字幕の控えめな校正アシスタントです。
入力は番号付きの短い字幕セグメント。前回の校正で「長すぎる」と却下された分の再校正です。
**意訳・統合・要約は禁止**。元の意味・長さをほぼ維持したまま、誤字脱字と不自然な助詞のみ修正してください。

ルール:
- 元の長さ +5 文字以内に収める（超えたら出力しない）
- セグメントの統合・分割は禁止
- 隣のセグメントから単語を移動しない
- 確信のある修正だけ返す（修正不要なら出力に含めない）

出力 JSON: {"corrections": [{"index": 0, "text": "..."}, ...]}"""


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


def extract_keywords(transcript_text: str, max_keywords: int = 8, video_context: str = "") -> list[str]:
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

    keywords_prompt = _with_context(_KEYWORDS_SYSTEM_PROMPT, video_context)
    try:
        if provider == "openai":
            raw = _call_openai(transcript_text, system_prompt=keywords_prompt)
        else:
            raw = _call_anthropic(transcript_text, system_prompt=keywords_prompt)
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


def generate_hook(transcript_text: str, video_context: str = "") -> str:
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

    hook_prompt = _with_context(_GENERATE_HOOK_SYSTEM_PROMPT, video_context)
    try:
        if provider == "openai":
            raw = _call_openai(transcript_text, system_prompt=hook_prompt)
        else:
            raw = _call_anthropic(transcript_text, system_prompt=hook_prompt)
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


def detect_topics(segments: list[str], max_topics: int = 4, video_context: str = "") -> list[dict]:
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
            raw = _call_openai(user_message, system_prompt=_with_context(_TOPICS_SYSTEM_PROMPT, video_context))
        else:
            raw = _call_anthropic(user_message, system_prompt=_with_context(_TOPICS_SYSTEM_PROMPT, video_context))
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
