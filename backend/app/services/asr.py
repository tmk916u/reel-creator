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


# === Ensemble ASR (ReazonSpeech + WhisperX) ===

def _normalize_for_compare(text: str) -> str:
    """ensemble の text 比較用に正規化 (空白・記号除去)。"""
    import re as _re
    return _re.sub(r"[\s、。!?,.・]+", "", text).strip()


def _overlap_ratio(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    """2 つの時刻範囲の overlap 割合 (短い方を分母) を返す。"""
    if a_end <= a_start or b_end <= b_start:
        return 0.0
    inter = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    shorter = min(a_end - a_start, b_end - b_start)
    return inter / shorter if shorter > 0 else 0.0


def _ensemble_merge(
    r_words: list[dict], w_words: list[dict], overlap_min: float = 0.5,
) -> list[dict]:
    """ReazonSpeech と WhisperX の word ストリームを ensemble する。

    アルゴリズム:
    1. WhisperX words を基準にループ
    2. 各 WhisperX word と時刻 overlap ≥ overlap_min の ReazonSpeech subwords をクラスタ
    3. クラスタ結合 text と WhisperX word.text を比較:
       - 同じ → WhisperX 採用 (source="agree")
       - 違う → WhisperX 採用 + 不一致記録 (source="disagreement", rs_text, wx_text)
    4. WhisperX に対応しない ReazonSpeech subwords は補完で追加 (source="rs_only")

    Returns:
        merged words の list。 各 word に "source" が含まれる
    """
    if not w_words and not r_words:
        return []
    if not w_words:
        return [{**w, "source": "rs_only"} for w in r_words]
    if not r_words:
        return [{**w, "source": "wx_only"} for w in w_words]

    merged: list[dict] = []
    used_r_indices: set[int] = set()

    for w in w_words:
        # この WhisperX word に overlap する ReazonSpeech subwords を集める
        cluster: list[tuple[int, dict]] = []
        for i, r in enumerate(r_words):
            if i in used_r_indices:
                continue
            if _overlap_ratio(w["start"], w["end"], r["start"], r["end"]) >= overlap_min:
                cluster.append((i, r))

        if not cluster:
            # ReazonSpeech 側に対応する subword が無い
            merged.append({
                "start": w["start"],
                "end": w["end"],
                "text": w["text"],
                "source": "wx_only",
            })
            continue

        # クラスタの subwords を結合した text と WhisperX text を比較
        for i, _ in cluster:
            used_r_indices.add(i)
        cluster_text = "".join(r["text"] for _, r in cluster)
        if _normalize_for_compare(cluster_text) == _normalize_for_compare(w["text"]):
            merged.append({
                "start": w["start"],
                "end": w["end"],
                "text": w["text"],
                "source": "agree",
            })
        else:
            merged.append({
                "start": w["start"],
                "end": w["end"],
                "text": w["text"],  # WhisperX 優先
                "source": "disagreement",
                "wx_text": w["text"],
                "rs_text": cluster_text,
            })

    # WhisperX に拾われなかった ReazonSpeech subwords を補完
    for i, r in enumerate(r_words):
        if i in used_r_indices:
            continue
        merged.append({
            "start": r["start"],
            "end": r["end"],
            "text": r["text"],
            "source": "rs_only",
            "is_word_start": r.get("is_word_start", True),
        })

    # 時刻順に sort
    merged.sort(key=lambda x: x["start"])
    return merged


def transcribe_ensemble(
    audio_path: str,
    initial_prompt: str | None = None,
    model_size: str = "medium",
    timeout: int = 600,
) -> tuple[list[dict], list[dict], dict]:
    """ReazonSpeech + WhisperX の ensemble 1段目 transcribe。

    両 ASR を並列実行し、 _ensemble_merge で 1 つの word ストリームに統合。

    Returns:
        (merged_words, merged_segments, debug_info)
        debug_info = {"r_words": [...], "w_words": [...], "disagreements": [...]}
    """
    import concurrent.futures
    prompt = initial_prompt or _DEFAULT_INITIAL_PROMPT
    t0 = time.time()

    r_result = None
    w_result = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f_r = ex.submit(_transcribe_with_reazonspeech, audio_path)
        f_w = ex.submit(_transcribe_with_whisperx, audio_path, prompt, model_size)
        try:
            r_result = f_r.result(timeout=timeout)
        except Exception as e:
            logger.warning("ensemble: ReazonSpeech failed: %s", e)
        try:
            w_result = f_w.result(timeout=timeout)
        except Exception as e:
            logger.warning("ensemble: WhisperX failed: %s", e)

    r_words = r_result[0] if r_result else []
    r_segments = r_result[1] if r_result else []
    w_words = w_result[0] if w_result else []
    w_segments = w_result[1] if w_result else []

    if not w_words and not r_words:
        # 両方失敗 → faster-whisper にフォールバック
        logger.warning("ensemble: both R and W failed, falling back to faster-whisper")
        fw_words, fw_segments = _transcribe_with_faster_whisper(
            audio_path, prompt, model_size,
        )
        return fw_words, fw_segments, {
            "r_words": [], "w_words": [], "disagreements": [],
            "fallback": "faster-whisper",
        }

    merged = _ensemble_merge(r_words, w_words)
    disagreements = [w for w in merged if w.get("source") == "disagreement"]

    # segments は WhisperX を優先、 無ければ ReazonSpeech
    merged_segments = w_segments if w_segments else r_segments

    elapsed = time.time() - t0
    logger.info(
        "ensemble: %d merged words (agree=%d, disagree=%d, rs_only=%d, wx_only=%d), %.1fs",
        len(merged),
        sum(1 for w in merged if w.get("source") == "agree"),
        len(disagreements),
        sum(1 for w in merged if w.get("source") == "rs_only"),
        sum(1 for w in merged if w.get("source") == "wx_only"),
        elapsed,
    )
    return merged, merged_segments, {
        "r_words": r_words,
        "w_words": w_words,
        "disagreements": disagreements,
    }
