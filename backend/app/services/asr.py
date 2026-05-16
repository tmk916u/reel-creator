# backend/app/services/asr.py
"""音声認識の3段フォールバック層: ReazonSpeech → WhisperX → faster-whisper.

返り値は全バックエンド共通で (words, segments).
words: list[{start: float, end: float, text: str}]
segments: list[{start: float, end: float, text: str}]
"""
from __future__ import annotations

import logging
import os
import time
from functools import lru_cache

logger = logging.getLogger(__name__)

_DEFAULT_INITIAL_PROMPT = "日本語で話している動画の文字起こしです。"


def _backend_env() -> str:
    """ASR_BACKEND: auto | reazonspeech | whisperx | faster-whisper"""
    return os.environ.get("ASR_BACKEND", "auto").lower()


# === ReazonSpeech (NeMo) ===

@lru_cache(maxsize=1)
def _load_reazonspeech_model():
    from reazonspeech.nemo.asr import load_model
    return load_model(device="cpu")


def _reazonspeech_result_to_words_segments(result) -> tuple[list[dict], list[dict]]:
    """NeMo の TranscribeResult を (words, segments) に変換する。

    NeMo の Subword は単一点 timestamp なので、隣接 subword の差で
    word duration を推定する。末尾は segment.end_seconds を使う。
    BPE 境界マーカー (U+2581) は除去する。
    """
    subwords = list(getattr(result, "subwords", None) or [])
    raw_segments = list(getattr(result, "segments", None) or [])

    if raw_segments:
        last_end = float(raw_segments[-1].end_seconds)
    elif subwords:
        last_end = float(subwords[-1].seconds) + 0.3
    else:
        last_end = 0.0

    words: list[dict] = []
    for i, sw in enumerate(subwords):
        raw_token = sw.token or ""
        token_text = raw_token.replace("▁", "")
        if not token_text:
            continue
        start = float(sw.seconds)
        end = float(subwords[i + 1].seconds) if i + 1 < len(subwords) else last_end
        if end <= start:
            end = start + 0.05
        # ▁ は SentencePiece の単語先頭マーカー。subtitle 改行を境界に寄せるのに使う
        words.append({
            "start": start, "end": end, "text": token_text,
            "is_word_start": "▁" in raw_token,
        })

    segments: list[dict] = [
        {
            "start": float(seg.start_seconds),
            "end": float(seg.end_seconds),
            "text": (seg.text or "").strip(),
        }
        for seg in raw_segments
    ]
    return words, segments


def _transcribe_with_reazonspeech(audio_path: str) -> tuple[list[dict], list[dict]] | None:
    """成功時 (words, segments)、失敗時 None."""
    try:
        from reazonspeech.nemo.asr import audio_from_path, transcribe
    except Exception as e:
        logger.info("ReazonSpeech not available: %s", e)
        return None

    try:
        t0 = time.time()
        model = _load_reazonspeech_model()
        audio = audio_from_path(audio_path)
        result = transcribe(model, audio)
        words, segments = _reazonspeech_result_to_words_segments(result)
        logger.info(
            "ReazonSpeech: %d segments, %d subwords, %.1fs",
            len(segments), len(words), time.time() - t0,
        )
        return words, segments
    except Exception as e:
        logger.warning("ReazonSpeech failed, falling back: %s", e)
        return None


# === WhisperX ===

@lru_cache(maxsize=2)
def _load_whisperx_model(model_size: str, language: str, initial_prompt: str):
    import whisperx
    return whisperx.load_model(
        model_size, device="cpu", compute_type="int8",
        language=language,
        asr_options={"initial_prompt": initial_prompt},
    )


@lru_cache(maxsize=1)
def _load_whisperx_align_model(language_code: str):
    import whisperx
    return whisperx.load_align_model(language_code=language_code, device="cpu")


def _transcribe_with_whisperx(
    audio_path: str, initial_prompt: str, model_size: str
) -> tuple[list[dict], list[dict]] | None:
    try:
        import whisperx  # noqa: F401
        try:
            import torch.serialization
            from omegaconf.listconfig import ListConfig
            from omegaconf.dictconfig import DictConfig
            from omegaconf.base import ContainerMetadata, Metadata
            from omegaconf.nodes import AnyNode
            import typing
            torch.serialization.add_safe_globals([
                ListConfig, DictConfig, ContainerMetadata, Metadata, AnyNode,
                typing.Any, typing.List, typing.Dict, typing.Tuple, typing.Optional,
                typing.Union, typing.Sequence, typing.Mapping,
            ])
        except Exception as patch_e:
            logger.warning("WhisperX safe-globals patch skipped: %s", patch_e)
    except Exception as e:
        logger.info("WhisperX not available: %s", e)
        return None

    try:
        import whisperx
        t0 = time.time()
        audio = whisperx.load_audio(audio_path)
        model = _load_whisperx_model(model_size, "ja", initial_prompt)
        result = model.transcribe(audio, language="ja", batch_size=4)
        align_model, metadata = _load_whisperx_align_model("ja")
        result = whisperx.align(
            result["segments"], align_model, metadata, audio, device="cpu",
            return_char_alignments=False,
        )

        words: list[dict] = []
        segments: list[dict] = []
        for seg in result.get("segments", []):
            segments.append({
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "text": (seg.get("text") or "").strip(),
            })
            for w in seg.get("words", []):
                if "start" not in w or "end" not in w:
                    continue
                words.append({
                    "start": float(w["start"]),
                    "end": float(w["end"]),
                    "text": w.get("word", "") or w.get("text", ""),
                })
        logger.info(
            "WhisperX: %d segments, %d aligned words, %.1fs",
            len(segments), len(words), time.time() - t0,
        )
        return words, segments
    except Exception as e:
        logger.warning("WhisperX failed, falling back to faster-whisper: %s", e)
        return None


# === faster-whisper ===

@lru_cache(maxsize=2)
def _load_faster_whisper_model(model_size: str):
    from faster_whisper import WhisperModel
    return WhisperModel(model_size, device="cpu", compute_type="int8")


def _transcribe_with_faster_whisper(
    audio_path: str, initial_prompt: str, model_size: str
) -> tuple[list[dict], list[dict]]:
    t0 = time.time()
    model = _load_faster_whisper_model(model_size)
    segments_iter, _info = model.transcribe(
        audio_path,
        language="ja",
        word_timestamps=True,
        initial_prompt=initial_prompt,
    )

    words: list[dict] = []
    segments: list[dict] = []
    for seg in segments_iter:
        segments.append({"start": seg.start, "end": seg.end, "text": seg.text})
        if seg.words:
            for w in seg.words:
                words.append({"start": w.start, "end": w.end, "text": w.word})
    logger.info(
        "faster-whisper: %d segments, %d words, %.1fs",
        len(segments), len(words), time.time() - t0,
    )
    return words, segments


def transcribe_with_words(
    audio_path: str,
    initial_prompt: str | None = None,
    model_size: str = "medium",
) -> tuple[list[dict], list[dict]]:
    """3段フォールバック: ReazonSpeech → WhisperX → faster-whisper.

    ASR_BACKEND 環境変数で個別バックエンド強制可能。
    """
    prompt = initial_prompt or _DEFAULT_INITIAL_PROMPT
    backend = _backend_env()

    if backend in ("auto", "reazonspeech"):
        result = _transcribe_with_reazonspeech(audio_path)
        if result is not None:
            return result
        if backend == "reazonspeech":
            raise RuntimeError("ASR_BACKEND=reazonspeech ですが ReazonSpeech が利用できません")

    if backend in ("auto", "whisperx"):
        result = _transcribe_with_whisperx(audio_path, prompt, model_size)
        if result is not None:
            return result
        if backend == "whisperx":
            raise RuntimeError("ASR_BACKEND=whisperx ですが WhisperX が利用できません")

    return _transcribe_with_faster_whisper(audio_path, prompt, model_size)
