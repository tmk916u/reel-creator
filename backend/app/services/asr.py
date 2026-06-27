# backend/app/services/asr.py
"""音声認識の3段フォールバック層: WhisperX → ReazonSpeech → faster-whisper.

transcribe_with_words の返り値は (words, segments, backend)。
内部の _transcribe_with_* は従来どおり (words, segments) を返す。
words: list[{start: float, end: float, text: str}]
segments: list[{start: float, end: float, text: str}]
backend: 実際に結果を生成したエンジン名（clamp 要否の判定に使う）
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


_STATE_ERROR_KEYWORDS = ("freeze", "unfreeze", "partial")


def _is_state_error(err: Exception) -> bool:
    """ReazonSpeech NeMo の freeze/unfreeze 系の状態破損エラーかを判定。"""
    msg = str(err).lower()
    return any(kw in msg for kw in _STATE_ERROR_KEYWORDS)


def _transcribe_with_reazonspeech(audio_path: str) -> tuple[list[dict], list[dict]] | None:
    """成功時 (words, segments)、失敗時 None.

    NeMo の transcribe() は同一プロセス内の連続呼出で
    「Cannot unfreeze partially without first freezing」 等の
    状態破損エラーを raise することがあるため、 検出時は
    lru_cache を破棄して fresh load で 1 回 retry する。
    """
    try:
        from reazonspeech.nemo.asr import audio_from_path, transcribe
    except Exception as e:
        logger.info("ReazonSpeech not available: %s", e)
        return None

    last_error: Exception | None = None
    for attempt in (1, 2):
        try:
            t0 = time.time()
            model = _load_reazonspeech_model()
            # 防御的に状態を強制リセット (NeMo の freeze() API)
            try:
                if hasattr(model, "freeze"):
                    model.freeze()
            except Exception:
                pass
            audio = audio_from_path(audio_path)
            result = transcribe(model, audio)
            words, segments = _reazonspeech_result_to_words_segments(result)
            logger.info(
                "ReazonSpeech: %d segments, %d subwords, %.1fs (attempt %d)",
                len(segments), len(words), time.time() - t0, attempt,
            )
            return words, segments
        except Exception as e:
            last_error = e
            if attempt == 1 and _is_state_error(e):
                logger.warning(
                    "ReazonSpeech state error on attempt 1, invalidating cache and retrying: %s",
                    e,
                )
                if hasattr(_load_reazonspeech_model, "cache_clear"):
                    _load_reazonspeech_model.cache_clear()
                continue
            break

    logger.warning("ReazonSpeech failed, falling back: %s", last_error)
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
) -> tuple[list[dict], list[dict], str]:
    """3段フォールバック: WhisperX → ReazonSpeech → faster-whisper.

    返り値は (words, segments, backend)。backend は実際に結果を生成したエンジン名
    ("whisperx" | "reazonspeech" | "faster-whisper")。呼び出し側はこれを使って
    clamp_oversized_word_ends の要否を判断する（ReazonSpeech のみ subword 単一点
    timestamp 由来の異常長 word を持つため clamp が必要。WhisperX/faster-whisper は
    forced alignment / word_timestamps で真の word.end を返すため clamp 不要）。

    ASR_BACKEND 環境変数で個別バックエンド強制可能。
    """
    prompt = initial_prompt or _DEFAULT_INITIAL_PROMPT
    backend = _backend_env()

    if backend in ("auto", "whisperx"):
        result = _transcribe_with_whisperx(audio_path, prompt, model_size)
        if result is not None:
            return result[0], result[1], "whisperx"
        if backend == "whisperx":
            raise RuntimeError("ASR_BACKEND=whisperx ですが WhisperX が利用できません")

    if backend in ("auto", "reazonspeech"):
        result = _transcribe_with_reazonspeech(audio_path)
        if result is not None:
            return result[0], result[1], "reazonspeech"
        if backend == "reazonspeech":
            raise RuntimeError("ASR_BACKEND=reazonspeech ですが ReazonSpeech が利用できません")

    words, segments = _transcribe_with_faster_whisper(audio_path, prompt, model_size)
    return words, segments, "faster-whisper"


def clamp_oversized_word_ends(
    words: list[dict],
    max_word_duration: float = 1.0,
    chars_per_sec: float = 8.0,
    min_duration: float = 0.1,
) -> list[dict]:
    """word.end が異常に長い word の end を文字数ベースの妥当な値にクランプする。

    ReazonSpeech NeMo は subword 単位の単一点 timestamp で、 word.end は実際の
    発話終了ではなく「次の subword の検出位置」を反映する。 発話間に長い無音が
    あると word.end が大幅に後ろにズレ、 word.duration が 5-21秒になることがある。

    現実：
    - word.start = 発話開始時刻 (おおむね正確)
    - word.end = 次の subword 検出位置 (発話の終わりとは限らない)
    - duration > 1秒の word は、 実発話 + 無音 + 次の発話の境界推定ノイズ

    補正：word.end を「word.start + (文字数 / chars_per_sec)」にクランプ。
    これで字幕タイミングが実発話に近づき、 word の後ろの無音区間は別途
    silence detection で削除される。

    Args:
        words: word-level transcript [{"start", "end", "text" | "word", ...}]
        max_word_duration: この秒数を超える word のみ補正対象
        chars_per_sec: 文字数からの duration 逆算レート (日本語発話の平均 ~8)
        min_duration: 最低 duration (1文字でも 0.1秒は確保)

    Returns:
        補正後 word リスト (元 word の他フィールドは保持)
    """
    out: list[dict] = []
    fixed_count = 0
    SHRINK_THRESHOLD = 0.2  # この秒数以上の短縮があった時のみ clamp 扱いに
    for w in words:
        dur = w["end"] - w["start"]
        if dur > max_word_duration:
            text = (w.get("text") or w.get("word") or "").strip()
            char_count = max(1, len(text))
            reasonable_dur = max(char_count / chars_per_sec, min_duration)
            new_end = w["start"] + min(reasonable_dur, dur)
            # 有意な短縮があった時のみ clamp 適用 + _orig_end 保存
            # (例: 文字数と duration が概ね一致する word は ASR ノイズではないので
            # 触らない。 「皆さんが悩まれている」 10 文字 ≈ 1.25s 等)
            if w["end"] - new_end >= SHRINK_THRESHOLD:
                # _orig_end を保存: 下流で「クランプ前の範囲」を「ASR が認識し損なった
                # 発話の可能性が高い区間」として扱える。 word_gap_cuts はこの区間を
                # ギャップとして削除しないようにする。
                out.append({**w, "end": new_end, "_orig_end": w["end"]})
                fixed_count += 1
            else:
                out.append(w)
        else:
            out.append(w)
    if fixed_count:
        logger.info(
            "clamp_oversized_word_ends: %d/%d words 補正 (max=%.1fs, chars/s=%.1f)",
            fixed_count, len(words), max_word_duration, chars_per_sec,
        )
    return out
