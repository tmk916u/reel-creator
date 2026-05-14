# backend/tests/test_llm.py
from unittest.mock import patch

from app.services import llm


def _words():
    return [
        {"start": 0.0, "end": 1.0, "text": "今日は"},
        {"start": 1.0, "end": 2.0, "text": "いや"},
        {"start": 2.0, "end": 3.0, "text": "明日は"},
        {"start": 3.0, "end": 4.0, "text": "雨です"},
    ]


def test_detect_restatements_unset_provider(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert llm.detect_restatements(_words()) == []


def test_detect_restatements_missing_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert llm.detect_restatements(_words()) == []


def test_detect_restatements_empty_words(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    assert llm.detect_restatements([]) == []


def test_detect_restatements_openai_success(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    fake = '{"ranges": [{"start": 1.0, "end": 2.0, "reason": "言い直し"}]}'
    with patch.object(llm, "_call_openai", return_value=fake):
        result = llm.detect_restatements(_words())
    assert result == [{"start": 1.0, "end": 2.0}]


def test_detect_restatements_anthropic_success(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    fake = '{"ranges": [{"start": 0.5, "end": 1.5}]}'
    with patch.object(llm, "_call_anthropic", return_value=fake):
        result = llm.detect_restatements(_words())
    assert result == [{"start": 0.5, "end": 1.5}]


def test_detect_restatements_out_of_range_discarded(monkeypatch):
    """transcript の時間範囲外の range は破棄される"""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    fake = '{"ranges": [{"start": 1.0, "end": 2.0}, {"start": 100.0, "end": 200.0}]}'
    with patch.object(llm, "_call_openai", return_value=fake):
        result = llm.detect_restatements(_words())
    assert result == [{"start": 1.0, "end": 2.0}]


def test_detect_restatements_empty_ranges(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    with patch.object(llm, "_call_openai", return_value='{"ranges": []}'):
        result = llm.detect_restatements(_words())
    assert result == []


def test_detect_restatements_api_error_returns_empty(monkeypatch):
    """LLM 呼び出しが例外でも空リストを返す（degraded mode）"""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    with patch.object(llm, "_call_openai", side_effect=RuntimeError("boom")):
        assert llm.detect_restatements(_words()) == []


def test_detect_restatements_invalid_json(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    with patch.object(llm, "_call_openai", return_value="not json"):
        assert llm.detect_restatements(_words()) == []


def test_detect_restatements_negative_range_discarded(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    fake = '{"ranges": [{"start": 2.0, "end": 1.0}]}'
    with patch.object(llm, "_call_openai", return_value=fake):
        assert llm.detect_restatements(_words()) == []


def test_extract_json_handles_code_fence():
    raw = '```json\n{"ranges": []}\n```'
    assert llm._extract_json(raw) == {"ranges": []}
