# backend/tests/test_silence.py
from app.services.silence import compute_voice_segments


def test_compute_voice_segments_basic():
    """無音区間から有音区間を正しく算出する"""
    silences = [
        {"start": 2.0, "end": 4.0},
        {"start": 7.0, "end": 9.0},
    ]
    total_duration = 10.0
    result = compute_voice_segments(silences, total_duration)
    assert result == [
        {"start": 0.0, "end": 2.0},
        {"start": 4.0, "end": 7.0},
        {"start": 9.0, "end": 10.0},
    ]


def test_compute_voice_segments_no_silence():
    """無音区間がない場合は動画全体を返す"""
    result = compute_voice_segments([], 10.0)
    assert result == [{"start": 0.0, "end": 10.0}]


def test_compute_voice_segments_all_silence():
    """全体が無音の場合は空リストを返す"""
    silences = [{"start": 0.0, "end": 10.0}]
    result = compute_voice_segments(silences, 10.0)
    assert result == []


def test_compute_voice_segments_silence_at_start():
    """冒頭が無音の場合"""
    silences = [{"start": 0.0, "end": 3.0}]
    result = compute_voice_segments(silences, 10.0)
    assert result == [{"start": 3.0, "end": 10.0}]


def test_compute_voice_segments_with_extra_cuts():
    """extra_cuts を無音区間とマージして処理する"""
    silences = [{"start": 2.0, "end": 4.0}]
    extra = [{"start": 6.0, "end": 7.0}]
    result = compute_voice_segments(silences, 10.0, extra_cuts=extra)
    assert result == [
        {"start": 0.0, "end": 2.0},
        {"start": 4.0, "end": 6.0},
        {"start": 7.0, "end": 10.0},
    ]


def test_compute_voice_segments_overlapping_cuts():
    """無音と extra_cuts が重複しても二重カウントしない"""
    silences = [{"start": 2.0, "end": 5.0}]
    extra = [{"start": 4.0, "end": 6.0}]
    result = compute_voice_segments(silences, 10.0, extra_cuts=extra)
    assert result == [
        {"start": 0.0, "end": 2.0},
        {"start": 6.0, "end": 10.0},
    ]


def test_compute_voice_segments_only_extra_cuts():
    """無音なしで extra_cuts だけでも動作する"""
    extra = [{"start": 3.0, "end": 5.0}]
    result = compute_voice_segments([], 10.0, extra_cuts=extra)
    assert result == [
        {"start": 0.0, "end": 3.0},
        {"start": 5.0, "end": 10.0},
    ]
