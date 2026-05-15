# backend/app/services/vad.py
"""Voice Activity Detection using Silero VAD.

ffmpeg silencedetect の高精度な代替。呼吸・小声と発話を区別できる。
"""
import logging

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16000


def snap_silences_to_word_boundaries(
    silences: list[dict],
    words: list[dict],
    margin: float = 0.05,
) -> list[dict]:
    """無音区間が単語の中で切らないように、単語境界に合わせて補正する。

    Args:
        silences: [{"start": float, "end": float}, ...] 無音区間
        words: [{"start": float, "end": float, "text": str}, ...] Whisper単語
        margin: 単語境界からこの秒数だけ離して切る（音の余韻を残す）

    Returns:
        補正済み無音区間リスト
    """
    if not silences or not words:
        return silences
    sorted_words = sorted(words, key=lambda w: w["start"])
    out: list[dict] = []
    for s in silences:
        new_start = s["start"]
        new_end = s["end"]
        for w in sorted_words:
            ws = w["start"]
            we = w["end"]
            if we < new_start or ws > new_end:
                continue  # 重複なし
            # silence の開始が単語の途中にある → 単語の終わり+margin まで遅らせる
            if ws < new_start < we:
                new_start = we + margin
            # silence の終了が単語の途中にある → 単語の始まり-margin まで早める
            if ws < new_end < we:
                new_end = ws - margin
        if new_end > new_start + 0.05:
            out.append({"start": new_start, "end": new_end})
    return out


def detect_silence_silero(
    audio_path: str,
    threshold: float = 0.5,
    min_silence_duration: float = 0.4,
    min_speech_duration: float = 0.2,
    speech_pad: float = 0.05,
) -> list[dict] | None:
    """Silero VAD で発話区間を検出し、無音区間リストを返す。

    Args:
        audio_path: 入力音声ファイルパス
        threshold: 発話判定のしきい値（0.0-1.0、高いほど厳しい）
        min_silence_duration: この秒数未満の無音は無視（連結）
        min_speech_duration: この秒数未満の発話は無視（短すぎる雑音を除外）
        speech_pad: 発話区間の前後に追加するパディング（秒）

    Returns:
        無音区間リスト [{"start": float, "end": float}, ...]
        失敗時は空リスト（呼び出し側で ffmpeg にフォールバック）
    """
    try:
        from silero_vad import load_silero_vad, get_speech_timestamps, read_audio
    except Exception as e:
        logger.warning("Silero VAD not available: %s", e)
        return None

    try:
        model = load_silero_vad()
        wav = read_audio(audio_path, sampling_rate=_SAMPLE_RATE)
        total_samples = wav.shape[0]
        total_duration = total_samples / _SAMPLE_RATE

        speech_ts = get_speech_timestamps(
            wav, model,
            sampling_rate=_SAMPLE_RATE,
            threshold=threshold,
            min_speech_duration_ms=int(min_speech_duration * 1000),
            min_silence_duration_ms=int(min_silence_duration * 1000),
            speech_pad_ms=int(speech_pad * 1000),
        )
    except Exception as e:
        logger.warning("Silero VAD failed: %s", e)
        return None

    # 発話区間（秒）を構築
    speech_ranges = [
        {"start": ts["start"] / _SAMPLE_RATE, "end": ts["end"] / _SAMPLE_RATE}
        for ts in speech_ts
    ]

    # 発話区間 → 無音区間に反転
    silences: list[dict] = []
    prev_end = 0.0
    for sp in speech_ranges:
        if sp["start"] > prev_end + 0.01:
            silences.append({"start": prev_end, "end": sp["start"]})
        prev_end = sp["end"]
    if prev_end < total_duration - 0.01:
        silences.append({"start": prev_end, "end": total_duration})

    logger.info(
        "Silero VAD: %d speech segments, %d silence ranges (%.1fs total)",
        len(speech_ranges), len(silences), total_duration,
    )
    return silences
