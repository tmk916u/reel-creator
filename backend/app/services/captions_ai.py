"""動画から AI で投稿用キャプション群を生成する（add-ai-caption-suggest）。

フロー:
  1. 動画ファイルから音声抽出（ffmpeg）
  2. ReazonSpeech で書き起こし（既存 asr.py 流用）
  3. Anthropic Claude に書き起こし + テーマを渡して JSON 構造化生成
  4. Pydantic で検証 + ハッシュタグ正規化

出力: instagram_caption / youtube_title / youtube_description / hashtags(5) / cover_text_candidates(3)
"""
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.services import storage
from app.services.ffmpeg import extract_audio
from app.services.hashtags import normalize_hashtags

logger = logging.getLogger(__name__)


class TranscribeError(RuntimeError):
    """ASR 失敗時に送出。"""


class LLMError(RuntimeError):
    """LLM 呼び出し / JSON 解析失敗時に送出。"""


_SYSTEM_PROMPT = """あなたは TikTok / Instagram Reels / YouTube Shorts 向けの SNS 運用アシスタントです。
整体院 / ヘルスケア領域のリール動画の音声書き起こしを読み、各媒体に最適化された
キャプション・タイトル・説明文・ハッシュタグ・カバー文字案を生成してください。

スタイル指針:
- instagram_caption: 親近感のあるトーン、適度に絵文字、ハッシュタグは含めない、200 文字以内
- youtube_title: クリック率を意識した訴求、70 文字以内
- youtube_description: SEO を意識、結論→詳細→CTA の構造、500 文字以内、末尾にハッシュタグを並べる
- hashtags: 5 個、`#` 付き、各媒体共通で使えるもの
- cover_text_candidates: 3 案、各 7〜12 文字以内、強い訴求、リール冒頭の大きな文字を想定

応答は必ず以下の JSON オブジェクトのみで返してください。前後にテキストを付けないでください。

{
  "instagram_caption": "...",
  "youtube_title": "...",
  "youtube_description": "...",
  "hashtags": ["#xxx", "#yyy", "#zzz", "#aaa", "#bbb"],
  "cover_text_candidates": ["案1", "案2", "案3"]
}"""


class CaptionsResult(BaseModel):
    instagram_caption: str
    youtube_title: str
    youtube_description: str
    hashtags: list[str] = Field(default_factory=list)
    cover_text_candidates: list[str] = Field(default_factory=list)

    @field_validator("hashtags")
    @classmethod
    def _normalize_tags(cls, v: list[str]) -> list[str]:
        # 既存正規化ロジックに通す（# 付与・5 個上限）
        joined = " ".join(v) if v else ""
        normalized = normalize_hashtags(joined)
        return normalized.split() if normalized else []

    @field_validator("cover_text_candidates")
    @classmethod
    def _trim_covers(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s and s.strip()][:3]


# ----- ASR -----

def _transcribe_video(video_id: str) -> str:
    """video_id の動画から書き起こしテキストを得る。"""
    src = storage.source_path(video_id)
    if not src.exists():
        raise TranscribeError("動画ファイルが見つかりません")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_path = tmp.name
    try:
        try:
            extract_audio(str(src), audio_path, preprocess=True)
        except Exception as e:
            raise TranscribeError(f"音声抽出に失敗しました: {e}") from e

        # 遅延 import: 既存 asr.py は重い依存（torch 等）を持つため
        from app.services.asr import transcribe_with_words
        try:
            _, segments, _ = transcribe_with_words(audio_path)
        except Exception as e:
            raise TranscribeError(f"書き起こしに失敗しました: {e}") from e

        text = " ".join(
            (seg.get("text") or "").strip() for seg in segments if seg.get("text")
        ).strip()
        if not text:
            raise TranscribeError("書き起こし結果が空でした")
        return text
    finally:
        Path(audio_path).unlink(missing_ok=True)


# ----- LLM -----

def _call_anthropic(user_text: str) -> str:
    """Anthropic Claude (Haiku 4.5) に JSON 生成を依頼。raw text を返す。"""
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise LLMError("ANTHROPIC_API_KEY が設定されていません")
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_text}],
        )
        text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                text += block.text
        return text or "{}"
    except Exception as e:
        raise LLMError(f"LLM 呼び出しに失敗しました: {e}") from e


def _extract_json(raw: str) -> dict[str, Any]:
    """LLM 応答から JSON を取り出す（コードフェンス対応）。"""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # ```json ... ``` の中身を抽出
        inner = "\n".join(lines[1:-1]) if len(lines) >= 2 else text
        text = inner.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # 部分的に取り出す試み（最初の { から最後の } まで）
        first = text.find("{")
        last = text.rfind("}")
        if first >= 0 and last > first:
            try:
                return json.loads(text[first:last + 1])
            except json.JSONDecodeError:
                pass
        raise LLMError(f"LLM 応答の JSON 解析に失敗: {e}") from e


# ----- 公開関数 -----

def suggest_captions(video_id: str, theme: str | None = None) -> CaptionsResult:
    """指定 video_id の動画から AI キャプション一式を生成する。"""
    transcript = _transcribe_video(video_id)

    user_parts = []
    if theme and theme.strip():
        user_parts.append(f"[テーマ]\n{theme.strip()}\n")
    user_parts.append(f"[書き起こし]\n{transcript}")
    user_text = "\n".join(user_parts)

    raw = _call_anthropic(user_text)
    payload = _extract_json(raw)

    try:
        result = CaptionsResult.model_validate(payload)
    except ValidationError as e:
        raise LLMError(f"LLM 応答スキーマ不正: {e}") from e

    logger.info(
        "captions generated: ig=%d chars, yt_title=%d chars, hashtags=%d, covers=%d",
        len(result.instagram_caption),
        len(result.youtube_title),
        len(result.hashtags),
        len(result.cover_text_candidates),
    )
    return result
