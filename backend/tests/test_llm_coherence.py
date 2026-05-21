# backend/tests/test_llm_coherence.py
"""detect_coherence_violations のユニットテスト。

OpenSpec: openspec/changes/llm-coherence-pass/
"""
from unittest.mock import patch

from app.services import llm


def _words(n: int = 6, step: float = 1.0) -> list[dict]:
    """短尺（総尺 n*step 秒）の word 列を作る。"""
    return [
        {"start": i * step, "end": (i + 1) * step, "text": f"word{i}"}
        for i in range(n)
    ]


def _long_words() -> list[dict]:
    """長尺（210 秒、3 チャンク予想）の word 列を作る。"""
    return [
        {"start": float(i), "end": float(i + 1), "text": f"w{i}"}
        for i in range(210)
    ]


# --- Scenario 7.1: フラグ OFF で即座に空 ---

def test_coherence_disabled_returns_empty(monkeypatch):
    monkeypatch.delenv("ENABLE_LLM_COHERENCE_PASS", raising=False)
    result = llm.detect_coherence_violations(_words())
    assert result["deletions"] == []
    assert result["chunks_total"] == 0


def test_coherence_disabled_zero_env(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COHERENCE_PASS", "0")
    result = llm.detect_coherence_violations(_words())
    assert result["deletions"] == []


# --- Scenario 7.2: LLM 未設定で空 ---

def test_coherence_missing_provider(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COHERENCE_PASS", "1")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    result = llm.detect_coherence_violations(_words())
    assert result["deletions"] == []


def test_coherence_missing_api_key(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COHERENCE_PASS", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = llm.detect_coherence_violations(_words())
    assert result["deletions"] == []


def test_coherence_empty_words(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COHERENCE_PASS", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    result = llm.detect_coherence_violations([])
    assert result["deletions"] == []


# --- Scenario 7.3: 短尺で LLM 1 回だけ呼ばれる ---

def test_coherence_short_calls_llm_once(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COHERENCE_PASS", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    fake = '{"deletions": [{"start": 2.0, "end": 3.0, "reason": "重複", "confidence": 0.8}], "summary": "ok"}'
    with patch.object(llm, "_call_openai", return_value=fake) as m:
        result = llm.detect_coherence_violations(_words(6))  # 6秒 < 60秒
    assert m.call_count == 1
    assert result["chunks_total"] == 1
    assert len(result["deletions"]) == 1
    assert result["deletions"][0]["confidence"] == 0.8


# --- Scenario 7.4: 長尺でチャンク分割呼出 ---

def test_coherence_long_calls_llm_per_chunk(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COHERENCE_PASS", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    fake = '{"deletions": [], "summary": ""}'
    with patch.object(llm, "_call_openai", return_value=fake) as m:
        result = llm.detect_coherence_violations(_long_words())  # 210 秒
    # 90 秒 - 15 秒 overlap = 75 秒 step。 210 秒なら 3 チャンク予想
    assert m.call_count >= 2
    assert result["chunks_total"] == m.call_count


# --- Scenario 7.5: 暴走ガード（削除総時間 > 30%） ---

def test_coherence_runaway_guard_drops_chunk(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COHERENCE_PASS", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    # 6 秒尺で 3 秒（50%）削除 → ガード作動でチャンク丸ごと破棄
    fake = '{"deletions": [{"start": 0.5, "end": 3.5, "reason": "", "confidence": 0.5}], "summary": ""}'
    with patch.object(llm, "_call_openai", return_value=fake):
        result = llm.detect_coherence_violations(_words(6))
    assert result["deletions"] == []
    assert any("runaway" in g for g in result["guard_actions"])


# --- Scenario 7.6: 8 秒超の単一削除ドロップ ---

def test_coherence_drops_long_single_deletion(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COHERENCE_PASS", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    # 30 秒尺、 単一 9 秒削除 → 個別にドロップ。 ただし他の 1 秒削除は残る
    words = _words(30, 1.0)
    fake = (
        '{"deletions": ['
        '{"start": 5.0, "end": 14.0, "reason": "long", "confidence": 0.6},'
        '{"start": 20.0, "end": 21.0, "reason": "short", "confidence": 0.9}'
        '], "summary": ""}'
    )
    with patch.object(llm, "_call_openai", return_value=fake):
        result = llm.detect_coherence_violations(words)
    assert len(result["deletions"]) == 1
    assert result["deletions"][0]["start"] == 20.0
    assert any("> 8.0s" in g or "exceed" in g.lower() for g in result["guard_actions"])


# --- Scenario 7.7: LLM 例外時 ---

def test_coherence_llm_error_returns_empty(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COHERENCE_PASS", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    with patch.object(llm, "_call_openai", side_effect=RuntimeError("boom")):
        result = llm.detect_coherence_violations(_words())
    assert result["deletions"] == []
    assert result["chunks_failed"] == 1


# --- Scenario 7.8: Pydantic スキーマ違反 ---

def test_coherence_schema_violation_skipped(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COHERENCE_PASS", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    # 必須 start を欠落させたペイロード
    fake = '{"deletions": [{"end": 1.0}], "summary": ""}'
    with patch.object(llm, "_call_openai", return_value=fake):
        result = llm.detect_coherence_violations(_words())
    assert result["deletions"] == []
    assert result["chunks_failed"] == 1


def test_coherence_invalid_json_skipped(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COHERENCE_PASS", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    with patch.object(llm, "_call_openai", return_value="not json at all"):
        result = llm.detect_coherence_violations(_words())
    assert result["deletions"] == []
    assert result["chunks_failed"] == 1


# --- 範囲外削除候補のドロップ ---

def test_coherence_out_of_range_dropped(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COHERENCE_PASS", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    words = _words(10, 1.0)  # 0-10s
    fake = (
        '{"deletions": ['
        '{"start": 2.0, "end": 3.0, "reason": "in", "confidence": 0.8},'
        '{"start": 100.0, "end": 200.0, "reason": "outofrange", "confidence": 0.9}'
        '], "summary": ""}'
    )
    with patch.object(llm, "_call_openai", return_value=fake):
        result = llm.detect_coherence_violations(words)
    assert len(result["deletions"]) == 1
    assert result["deletions"][0]["start"] == 2.0
    assert any("out-of-range" in g for g in result["guard_actions"])


# --- Anthropic provider ---

def test_coherence_anthropic_success(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COHERENCE_PASS", "1")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    fake = '{"deletions": [{"start": 1.0, "end": 2.0, "reason": "r", "confidence": 0.7}], "summary": "s"}'
    with patch.object(llm, "_call_anthropic", return_value=fake) as m:
        result = llm.detect_coherence_violations(_words())
    assert m.call_count == 1
    assert len(result["deletions"]) == 1
    assert result["summary"] == "s"


# --- 1 チャンク失敗で他チャンクの結果は採用 ---

def test_coherence_partial_chunk_failure(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COHERENCE_PASS", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    # 長尺：1 つ目チャンクは成功、 2 つ目は例外
    call_count = [0]

    def side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return '{"deletions": [{"start": 5.0, "end": 6.0, "reason": "", "confidence": 0.5}], "summary": ""}'
        raise RuntimeError("chunk 2 boom")

    with patch.object(llm, "_call_openai", side_effect=side_effect):
        result = llm.detect_coherence_violations(_long_words())

    assert len(result["deletions"]) == 1
    assert result["chunks_failed"] >= 1
    assert result["chunks_total"] >= 2


# --- confidence は 0-1 にクランプ ---

def test_coherence_confidence_clamped(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COHERENCE_PASS", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    # 30 秒尺で 2 秒削除（6.7%）→ 暴走ガード（30%）に引っかからない
    fake = (
        '{"deletions": ['
        '{"start": 1.0, "end": 2.0, "reason": "", "confidence": 1.5},'
        '{"start": 3.0, "end": 4.0, "reason": "", "confidence": -0.5}'
        '], "summary": ""}'
    )
    with patch.object(llm, "_call_openai", return_value=fake):
        result = llm.detect_coherence_violations(_words(30, 1.0))
    confidences = [d["confidence"] for d in result["deletions"]]
    assert len(confidences) == 2
    assert all(0.0 <= c <= 1.0 for c in confidences)
    assert confidences[0] == 1.0
    assert confidences[1] == 0.0
