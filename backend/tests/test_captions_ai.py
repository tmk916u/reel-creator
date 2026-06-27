import pytest

from app.services import captions_ai
from app.services.captions_ai import (
    CaptionsResult,
    LLMError,
    TranscribeError,
    _extract_json,
    suggest_captions,
)


# --- _extract_json ---

class TestExtractJson:
    def test_plain_json(self):
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_with_code_fence(self):
        text = "```json\n{\"a\": 1}\n```"
        assert _extract_json(text) == {"a": 1}

    def test_with_surrounding_text(self):
        text = "Here is the result:\n{\"a\": 1}\nThanks."
        assert _extract_json(text) == {"a": 1}

    def test_invalid_raises(self):
        with pytest.raises(LLMError):
            _extract_json("not json at all")


# --- CaptionsResult validation ---

class TestCaptionsResult:
    def test_normal(self):
        r = CaptionsResult(
            instagram_caption="やせる食事",
            youtube_title="ダイエット",
            youtube_description="詳細",
            hashtags=["#a", "#b", "#c", "#d", "#e"],
            cover_text_candidates=["案1", "案2", "案3"],
        )
        assert len(r.hashtags) == 5
        assert len(r.cover_text_candidates) == 3

    def test_hashtag_normalization(self):
        """`#` 無しタグも `#` 付きに揃う。"""
        r = CaptionsResult(
            instagram_caption="a", youtube_title="b", youtube_description="c",
            hashtags=["ダイエット", "#食事改善", "ボディメイク"],
            cover_text_candidates=[],
        )
        assert r.hashtags == ["#ダイエット", "#食事改善", "#ボディメイク"]

    def test_hashtag_over_limit_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CaptionsResult(
                instagram_caption="a", youtube_title="b", youtube_description="c",
                hashtags=["#a", "#b", "#c", "#d", "#e", "#f"],
                cover_text_candidates=[],
            )

    def test_cover_text_trim_to_three(self):
        r = CaptionsResult(
            instagram_caption="a", youtube_title="b", youtube_description="c",
            hashtags=[],
            cover_text_candidates=["a", "b", "c", "d", "e"],
        )
        assert r.cover_text_candidates == ["a", "b", "c"]

    def test_cover_text_empty_stripped(self):
        r = CaptionsResult(
            instagram_caption="a", youtube_title="b", youtube_description="c",
            hashtags=[],
            cover_text_candidates=["案1", "  ", "案2", ""],
        )
        assert r.cover_text_candidates == ["案1", "案2"]


# --- suggest_captions (end-to-end with mocks) ---

class TestSuggestCaptions:
    def test_success(self, monkeypatch):
        monkeypatch.setattr(captions_ai, "_transcribe_video", lambda vid: "これは整体院の動画です")
        monkeypatch.setattr(
            captions_ai, "_call_anthropic",
            lambda text, system_prompt=None: '{"instagram_caption":"IG","youtube_title":"YT","youtube_description":"説明","hashtags":["#a","#b","#c","#d","#e"],"cover_text_candidates":["案1","案2","案3"]}',
        )
        result = suggest_captions("vid-123", theme="ダイエット")
        assert result.instagram_caption == "IG"
        assert result.youtube_title == "YT"
        assert len(result.hashtags) == 5
        assert len(result.cover_text_candidates) == 3

    def test_transcribe_failure_propagates(self, monkeypatch):
        def raise_(vid):
            raise TranscribeError("音声抽出に失敗")
        monkeypatch.setattr(captions_ai, "_transcribe_video", raise_)
        with pytest.raises(TranscribeError):
            suggest_captions("vid", theme=None)

    def test_llm_failure_propagates(self, monkeypatch):
        monkeypatch.setattr(captions_ai, "_transcribe_video", lambda vid: "transcript text")
        def raise_(text, system_prompt=None):
            raise LLMError("API down")
        monkeypatch.setattr(captions_ai, "_call_anthropic", raise_)
        with pytest.raises(LLMError):
            suggest_captions("vid", theme=None)

    def test_llm_invalid_json_propagates(self, monkeypatch):
        monkeypatch.setattr(captions_ai, "_transcribe_video", lambda vid: "transcript")
        monkeypatch.setattr(captions_ai, "_call_anthropic", lambda text, system_prompt=None: "not json")
        with pytest.raises(LLMError):
            suggest_captions("vid", theme=None)

    def test_llm_schema_mismatch_propagates(self, monkeypatch):
        """LLM が必須フィールドを欠いた JSON を返す場合。"""
        monkeypatch.setattr(captions_ai, "_transcribe_video", lambda vid: "transcript")
        monkeypatch.setattr(
            captions_ai, "_call_anthropic",
            lambda text, system_prompt=None: '{"hashtags": []}',  # 必須フィールド欠落
        )
        with pytest.raises(LLMError):
            suggest_captions("vid", theme=None)
