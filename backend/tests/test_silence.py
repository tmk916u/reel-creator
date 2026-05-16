# backend/tests/test_silence.py
from app.services.silence import compute_voice_segments


def test_compute_voice_segments_basic():
    """無音区間から有音区間を正しく算出する（padding 無効化）"""
    silences = [
        {"start": 2.0, "end": 4.0},
        {"start": 7.0, "end": 9.0},
    ]
    total_duration = 10.0
    result = compute_voice_segments(silences, total_duration, padding=0)
    assert result == [
        {"start": 0.0, "end": 2.0},
        {"start": 4.0, "end": 7.0},
        {"start": 9.0, "end": 10.0},
    ]


def test_compute_voice_segments_no_silence():
    """無音区間がない場合は動画全体を返す"""
    result = compute_voice_segments([], 10.0, padding=0)
    assert result == [{"start": 0.0, "end": 10.0}]


def test_compute_voice_segments_trim_leading_is_noop():
    """trim_leading=True は現状 no-op（副作用のため無効化）。冒頭無音は
    VAD が silences に含めて自動削除されるため、voice_segments[0].start
    は無音区間の終端のままで字幕の時刻マッピングが壊れない。"""
    silences = [{"start": 0.0, "end": 4.0}]
    out_true = compute_voice_segments(silences, total_duration=10.0, padding=0.0, trim_leading=True)
    out_false = compute_voice_segments(silences, total_duration=10.0, padding=0.0)
    # 両者同じ動作: voice 区間は元動画の 4.0-10.0 として返す
    assert out_true == out_false
    assert out_true == [{"start": 4.0, "end": 10.0}]


def test_compute_voice_segments_all_silence():
    """全体が無音の場合は空リストを返す"""
    silences = [{"start": 0.0, "end": 10.0}]
    result = compute_voice_segments(silences, 10.0, padding=0)
    assert result == []


def test_compute_voice_segments_silence_at_start():
    """冒頭が無音の場合"""
    silences = [{"start": 0.0, "end": 3.0}]
    result = compute_voice_segments(silences, 10.0, padding=0)
    assert result == [{"start": 3.0, "end": 10.0}]


def test_compute_voice_segments_with_extra_cuts():
    """extra_cuts を無音区間とマージして処理する"""
    silences = [{"start": 2.0, "end": 4.0}]
    extra = [{"start": 6.0, "end": 7.0}]
    result = compute_voice_segments(silences, 10.0, padding=0, extra_cuts=extra)
    assert result == [
        {"start": 0.0, "end": 2.0},
        {"start": 4.0, "end": 6.0},
        {"start": 7.0, "end": 10.0},
    ]


def test_compute_voice_segments_overlapping_cuts():
    """無音と extra_cuts が重複しても二重カウントしない"""
    silences = [{"start": 2.0, "end": 5.0}]
    extra = [{"start": 4.0, "end": 6.0}]
    result = compute_voice_segments(silences, 10.0, padding=0, extra_cuts=extra)
    assert result == [
        {"start": 0.0, "end": 2.0},
        {"start": 6.0, "end": 10.0},
    ]


def test_compute_voice_segments_only_extra_cuts():
    """無音なしで extra_cuts だけでも動作する"""
    extra = [{"start": 3.0, "end": 5.0}]
    result = compute_voice_segments([], 10.0, padding=0, extra_cuts=extra)
    assert result == [
        {"start": 0.0, "end": 3.0},
        {"start": 5.0, "end": 10.0},
    ]


def test_compute_voice_segments_min_cut_length_filters_short_cuts():
    """min_cut_length より短いカットは無視される（ジッタ除去）"""
    silences = [{"start": 2.0, "end": 2.05}, {"start": 5.0, "end": 6.0}]
    result = compute_voice_segments(silences, 10.0, padding=0, min_cut_length=0.08)
    # 0.05秒のカットは無視され、5.0-6.0だけが削除される
    assert result == [
        {"start": 0.0, "end": 5.0},
        {"start": 6.0, "end": 10.0},
    ]


def test_compute_voice_segments_padding_expands_segments():
    """padding により有音区間が前後に少し広がる"""
    silences = [{"start": 2.0, "end": 4.0}]
    result = compute_voice_segments(silences, 10.0, padding=0.1)
    assert result == [
        {"start": 0.0, "end": 2.1},
        {"start": 3.9, "end": 10.0},
    ]


def test_compute_voice_segments_padding_merges_overlap():
    """padding 拡張で隣接する有音区間が重なれば統合される"""
    silences = [{"start": 2.0, "end": 2.15}]
    result = compute_voice_segments(silences, 10.0, padding=0.1, min_cut_length=0.05)
    # padding により有音区間 [0, 2.1] と [2.05, 10.0] が重なるので統合
    assert result == [{"start": 0.0, "end": 10.0}]
