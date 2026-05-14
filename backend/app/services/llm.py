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


def _format_transcript(words: list[dict]) -> str:
    lines = []
    for w in words:
        lines.append(f"[{w['start']:.2f}-{w['end']:.2f}] {w['text']}")
    return "\n".join(lines)


def _call_openai(transcript_text: str) -> str:
    from openai import OpenAI

    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": transcript_text},
        ],
    )
    return resp.choices[0].message.content or "{}"


def _call_anthropic(transcript_text: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=_SYSTEM_PROMPT + "\n\n応答は JSON オブジェクトのみで返してください。",
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
