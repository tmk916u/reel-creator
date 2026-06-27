# backend/tests/test_asr.py
from types import SimpleNamespace

import pytest

from app.services import asr


# === subword → word 変換 ===

def test_reazonspeech_subword_to_word_conversion():
    """隣接 subword の差で word duration を構築する。末尾は segment.end_seconds。"""
    result = SimpleNamespace(
        subwords=[
            SimpleNamespace(seconds=0.0, token="今"),
            SimpleNamespace(seconds=0.3, token="日"),
            SimpleNamespace(seconds=0.6, token="は"),
        ],
        segments=[
            SimpleNamespace(start_seconds=0.0, end_seconds=1.0, text="今日は"),
        ],
    )
    words, segments = asr._reazonspeech_result_to_words_segments(result)
    assert len(words) == 3
    assert words[0] == {"start": 0.0, "end": 0.3, "text": "今", "is_word_start": False}
    assert words[1] == {"start": 0.3, "end": 0.6, "text": "日", "is_word_start": False}
    assert words[2] == {"start": 0.6, "end": 1.0, "text": "は", "is_word_start": False}
    assert segments == [{"start": 0.0, "end": 1.0, "text": "今日は"}]


def test_reazonspeech_strips_bpe_boundary_marker():
    """BPE 境界マーカー (U+2581) を除去し、is_word_start に反映する。"""
    result = SimpleNamespace(
        subwords=[
            SimpleNamespace(seconds=0.0, token="▁今日"),
            SimpleNamespace(seconds=0.5, token="は"),
        ],
        segments=[SimpleNamespace(start_seconds=0.0, end_seconds=1.0, text="今日は")],
    )
    words, _ = asr._reazonspeech_result_to_words_segments(result)
    assert [w["text"] for w in words] == ["今日", "は"]
    assert [w["is_word_start"] for w in words] == [True, False]


def test_reazonspeech_handles_empty_result():
    """subwords も segments も空なら空配列を返す。"""
    result = SimpleNamespace(subwords=[], segments=[])
    words, segments = asr._reazonspeech_result_to_words_segments(result)
    assert words == []
    assert segments == []


def test_reazonspeech_last_subword_falls_back_when_no_segments():
    """segments が空でも、末尾 subword は単一点 +0.3s で end を埋める。"""
    result = SimpleNamespace(
        subwords=[
            SimpleNamespace(seconds=0.0, token="あ"),
            SimpleNamespace(seconds=0.4, token="い"),
        ],
        segments=[],
    )
    words, _ = asr._reazonspeech_result_to_words_segments(result)
    assert words[0]["end"] == 0.4
    assert words[1]["start"] == 0.4
    assert words[1]["end"] == pytest.approx(0.7)


def test_reazonspeech_zero_duration_subword_extends_to_min():
    """end <= start のケースで最小 duration を保証する。"""
    result = SimpleNamespace(
        subwords=[
            SimpleNamespace(seconds=0.5, token="あ"),
            SimpleNamespace(seconds=0.5, token="い"),
        ],
        segments=[SimpleNamespace(start_seconds=0.0, end_seconds=0.5, text="あい")],
    )
    words, _ = asr._reazonspeech_result_to_words_segments(result)
    assert words[0]["end"] > words[0]["start"]
    assert words[1]["end"] > words[1]["start"]


# === 3 段フォールバック ===

def test_fallback_whisperx_success_skips_others(monkeypatch):
    """auto は WhisperX を最優先。成功すれば他は呼ばれず backend='whisperx'。"""
    monkeypatch.delenv("ASR_BACKEND", raising=False)
    calls: list[str] = []
    monkeypatch.setattr(asr, "_transcribe_with_whisperx",
                        lambda *a, **k: (calls.append("wx") or ([{"start": 0, "end": 1, "text": "wx"}], [])))
    monkeypatch.setattr(asr, "_transcribe_with_reazonspeech",
                        lambda p: calls.append("rs") or ([], []))
    monkeypatch.setattr(asr, "_transcribe_with_faster_whisper",
                        lambda *a, **k: calls.append("fw") or ([], []))

    words, segs, backend = asr.transcribe_with_words("/tmp/x.wav")
    assert calls == ["wx"]
    assert backend == "whisperx"
    assert words == [{"start": 0, "end": 1, "text": "wx"}]


def test_fallback_whisperx_fails_to_reazonspeech(monkeypatch):
    """WhisperX 不可なら ReazonSpeech にフォールバック、backend='reazonspeech'。"""
    monkeypatch.delenv("ASR_BACKEND", raising=False)
    calls: list[str] = []
    monkeypatch.setattr(asr, "_transcribe_with_whisperx",
                        lambda *a, **k: calls.append("wx") or None)
    monkeypatch.setattr(asr, "_transcribe_with_reazonspeech",
                        lambda p: (calls.append("rs") or ([{"start": 0, "end": 1, "text": "rs"}], [])))
    monkeypatch.setattr(asr, "_transcribe_with_faster_whisper",
                        lambda *a, **k: calls.append("fw") or ([], []))

    words, _, backend = asr.transcribe_with_words("/tmp/x.wav")
    assert calls == ["wx", "rs"]
    assert backend == "reazonspeech"
    assert words[0]["text"] == "rs"


def test_fallback_all_through_to_faster_whisper(monkeypatch):
    """WhisperX も ReazonSpeech も不可なら faster-whisper、backend='faster-whisper'。"""
    monkeypatch.delenv("ASR_BACKEND", raising=False)
    calls: list[str] = []
    monkeypatch.setattr(asr, "_transcribe_with_whisperx",
                        lambda *a, **k: calls.append("wx") or None)
    monkeypatch.setattr(asr, "_transcribe_with_reazonspeech",
                        lambda p: calls.append("rs") or None)
    monkeypatch.setattr(asr, "_transcribe_with_faster_whisper",
                        lambda *a, **k: (calls.append("fw") or ([{"start": 0, "end": 1, "text": "fw"}], [])))

    words, _, backend = asr.transcribe_with_words("/tmp/x.wav")
    assert calls == ["wx", "rs", "fw"]
    assert backend == "faster-whisper"
    assert words[0]["text"] == "fw"


def test_force_backend_reazonspeech_raises_when_unavailable(monkeypatch):
    monkeypatch.setenv("ASR_BACKEND", "reazonspeech")
    monkeypatch.setattr(asr, "_transcribe_with_reazonspeech", lambda p: None)
    with pytest.raises(RuntimeError, match="reazonspeech"):
        asr.transcribe_with_words("/tmp/x.wav")


def test_force_backend_whisperx_skips_reazonspeech(monkeypatch):
    monkeypatch.setenv("ASR_BACKEND", "whisperx")
    calls: list[str] = []
    monkeypatch.setattr(asr, "_transcribe_with_reazonspeech",
                        lambda p: calls.append("rs") or ([], []))
    monkeypatch.setattr(asr, "_transcribe_with_whisperx",
                        lambda *a, **k: (calls.append("wx") or ([{"start": 0, "end": 1, "text": "wx"}], [])))

    asr.transcribe_with_words("/tmp/x.wav")
    assert calls == ["wx"]


def test_force_backend_faster_whisper_skips_others(monkeypatch):
    monkeypatch.setenv("ASR_BACKEND", "faster-whisper")
    calls: list[str] = []
    monkeypatch.setattr(asr, "_transcribe_with_reazonspeech",
                        lambda p: calls.append("rs") or ([], []))
    monkeypatch.setattr(asr, "_transcribe_with_whisperx",
                        lambda *a, **k: calls.append("wx") or ([], []))
    monkeypatch.setattr(asr, "_transcribe_with_faster_whisper",
                        lambda *a, **k: (calls.append("fw") or ([{"start": 0, "end": 1, "text": "fw"}], [])))

    asr.transcribe_with_words("/tmp/x.wav")
    assert calls == ["fw"]


def test_subtitle_module_reexports_transcribe_with_words():
    """後方互換: from app.services.subtitle import transcribe_with_words が動く。"""
    from app.services.subtitle import transcribe_with_words as tww
    assert tww is asr.transcribe_with_words


# === ReazonSpeech state error recovery (fix-reazonspeech-model-state-leak) ===

def test_is_state_error_detects_freeze_keywords():
    assert asr._is_state_error(Exception("Cannot unfreeze partially without first freezing"))
    assert asr._is_state_error(Exception("freeze() must be called"))
    assert asr._is_state_error(Exception("partial state mismatch"))
    assert not asr._is_state_error(Exception("audio file not found"))
    assert not asr._is_state_error(Exception("CUDA out of memory"))


def _make_loader_with_cache_clear(model, cleared: dict) -> callable:
    """cache_clear 属性を持つ fake loader を作る。"""
    def loader():
        return model
    def cache_clear():
        cleared["count"] += 1
    loader.cache_clear = cache_clear
    return loader


def test_reazonspeech_retries_on_state_error_with_cache_clear(monkeypatch):
    """state error 発生時、 cache_clear → fresh load → retry が走り成功する。"""
    cleared = {"count": 0}
    fake_model = SimpleNamespace(freeze=lambda: None)
    monkeypatch.setattr(asr, "_load_reazonspeech_model", _make_loader_with_cache_clear(fake_model, cleared))

    call_count = {"n": 0}
    fake_result = SimpleNamespace(
        subwords=[SimpleNamespace(seconds=0.0, token="あ")],
        segments=[SimpleNamespace(start_seconds=0.0, end_seconds=0.5, text="あ")],
    )

    def fake_transcribe(model, audio):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise Exception("Cannot unfreeze partially without first freezing")
        return fake_result

    import sys
    fake_module = SimpleNamespace(
        audio_from_path=lambda p: SimpleNamespace(samples=[], rate=16000),
        transcribe=fake_transcribe,
    )
    sys.modules["reazonspeech.nemo.asr"] = fake_module

    try:
        result = asr._transcribe_with_reazonspeech("/tmp/x.wav")
        assert result is not None
        words, _ = result
        assert len(words) == 1
        assert cleared["count"] == 1  # cache_clear が 1 回呼ばれた
        assert call_count["n"] == 2  # transcribe が 2 回呼ばれた (retry あり)
    finally:
        sys.modules.pop("reazonspeech.nemo.asr", None)


def test_reazonspeech_no_retry_for_non_state_error(monkeypatch):
    """state 以外のエラー (file not found 等) は retry せず None を返す。"""
    cleared = {"count": 0}
    fake_model = SimpleNamespace(freeze=lambda: None)
    monkeypatch.setattr(asr, "_load_reazonspeech_model", _make_loader_with_cache_clear(fake_model, cleared))

    def fake_audio_from_path(p):
        raise FileNotFoundError("audio not found")

    import sys
    fake_module = SimpleNamespace(
        audio_from_path=fake_audio_from_path,
        transcribe=lambda model, audio: None,
    )
    sys.modules["reazonspeech.nemo.asr"] = fake_module

    try:
        result = asr._transcribe_with_reazonspeech("/tmp/nonexistent.wav")
        assert result is None
        assert cleared["count"] == 0  # cache_clear は呼ばれない
    finally:
        sys.modules.pop("reazonspeech.nemo.asr", None)


# === clamp_oversized_word_ends ===

def test_clamp_oversized_word_ends_fixes_long_word():
    """duration > max の word は文字数ベースの妥当な end にクランプ"""
    words = [
        {"start": 0.0, "end": 0.5, "text": "あ"},  # 通常
        {"start": 33.06, "end": 45.14, "text": "お"},  # 12.08s 異常
        {"start": 45.14, "end": 45.30, "text": "客"},  # 通常
    ]
    out = asr.clamp_oversized_word_ends(words, max_word_duration=1.0, chars_per_sec=8.0)
    assert out[0] == words[0]  # 変更なし
    # 「お」 1文字 → 1/8 = 0.125s に補正 → end = 33.06 + 0.125 = 33.185
    assert out[1]["start"] == 33.06
    assert abs(out[1]["end"] - 33.185) < 0.001
    assert "text" in out[1]
    assert out[2] == words[2]  # 変更なし


def test_clamp_oversized_word_ends_respects_min_duration():
    """min_duration を下回らない (1文字でも 0.1秒は確保)"""
    words = [{"start": 0.0, "end": 5.0, "text": "あ"}]
    out = asr.clamp_oversized_word_ends(words, max_word_duration=1.0, chars_per_sec=100.0, min_duration=0.1)
    # 1文字 / 100 = 0.01s だが min=0.1 で 0.1 にクランプ
    assert abs(out[0]["end"] - 0.1) < 0.001


def test_clamp_oversized_word_ends_multichar_word():
    """複数文字 word は文字数比例で妥当な duration"""
    words = [{"start": 10.0, "end": 25.0, "text": "あいうえお"}]  # 5文字, 15s
    out = asr.clamp_oversized_word_ends(words, max_word_duration=1.0, chars_per_sec=8.0)
    # 5/8 = 0.625s
    assert abs(out[0]["end"] - 10.625) < 0.001


def test_clamp_oversized_word_ends_preserves_other_fields():
    """他の word フィールドは保持"""
    words = [{"start": 0.0, "end": 5.0, "text": "あ", "source": "agree", "is_word_start": True}]
    out = asr.clamp_oversized_word_ends(words, max_word_duration=1.0)
    assert out[0]["source"] == "agree"
    assert out[0]["is_word_start"] is True
    assert out[0]["text"] == "あ"


def test_clamp_oversized_word_ends_uses_word_field_as_fallback():
    """WhisperX 形式 (word キー) でも動作"""
    words = [{"start": 0.0, "end": 5.0, "word": "あいう"}]
    out = asr.clamp_oversized_word_ends(words, max_word_duration=1.0, chars_per_sec=8.0)
    # 3文字 / 8 = 0.375s
    assert abs(out[0]["end"] - 0.375) < 0.001


def test_clamp_oversized_word_ends_empty():
    assert asr.clamp_oversized_word_ends([]) == []
