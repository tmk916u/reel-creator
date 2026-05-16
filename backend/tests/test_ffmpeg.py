import pytest
from app.services.ffmpeg import (
    get_video_duration,
    extract_audio,
    _build_cut_concat_filter,
)


def test_get_video_duration_invalid_file():
    with pytest.raises(RuntimeError):
        get_video_duration("/nonexistent/file.mp4")


def test_build_cut_concat_filter_single_segment():
    """1セグメント: trim/scale/pad/atrim/afade/concat+fps を組み立てる"""
    segs = [{"start": 1.0, "end": 5.0}]
    f = _build_cut_concat_filter(segs, audio_fade=0.08)
    # trim + setpts + scale/pad/setsar が連結される
    assert "[0:v]trim=start=1.000:end=5.000,setpts=PTS-STARTPTS," in f
    assert "scale=1080:1920:force_original_aspect_ratio=decrease" in f
    assert "pad=1080:1920" in f
    assert "[v0]" in f
    # 音声側
    assert "[0:a]atrim=start=1.000:end=5.000" in f
    assert "afade=t=in:d=0.080" in f
    assert "afade=t=out:d=0.080:st=3.920" in f
    # concat → fps の 2 段
    assert "[v0][a0]concat=n=1:v=1:a=1[vcat][outa]" in f
    assert f.endswith("[vcat]fps=30[outv]")


def test_build_cut_concat_filter_multiple_segments_order_preserved():
    """3セグメントの順序が concat ラベル列で保持される"""
    segs = [
        {"start": 0.0, "end": 2.0},
        {"start": 5.0, "end": 8.0},
        {"start": 10.0, "end": 11.0},
    ]
    f = _build_cut_concat_filter(segs)
    for i in range(3):
        assert f"[v{i}]" in f
        assert f"[a{i}]" in f
    assert "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[vcat][outa]" in f
    assert "[vcat]fps=30[outv]" in f


def test_build_cut_concat_filter_custom_target_size():
    """target_width/height/fps をパラメータ指定できる"""
    segs = [{"start": 0.0, "end": 1.0}]
    f = _build_cut_concat_filter(segs, target_width=720, target_height=1280, fps=24)
    assert "scale=720:1280" in f
    assert "pad=720:1280" in f
    assert "[vcat]fps=24[outv]" in f


def test_build_cut_concat_filter_short_segment_clamps_fade():
    """seg duration < 3*audio_fade のとき fade_d を dur/3 にクランプ"""
    segs = [{"start": 0.0, "end": 0.15}]
    f = _build_cut_concat_filter(segs, audio_fade=0.08)
    assert "afade=t=in:d=0.050" in f
    assert "afade=t=out:d=0.050:st=0.100" in f


def test_build_cut_concat_filter_zero_duration_no_fade():
    """duration 0 ではフェードを掛けない（afade=d=0 で nan エラーを回避）"""
    segs = [{"start": 5.0, "end": 5.0}]
    f = _build_cut_concat_filter(segs)
    assert "afade" not in f
    assert "[0:a]atrim=start=5.000:end=5.000,asetpts=PTS-STARTPTS[a0]" in f


def test_build_cut_concat_filter_uses_input_zero_for_all_segments():
    """全セグメントが同じ入力(0)を参照する（1パス前提）"""
    segs = [{"start": i, "end": i + 1} for i in range(5)]
    f = _build_cut_concat_filter(segs)
    # 各セグメントが [0:v] と [0:a] から trim される
    assert f.count("[0:v]trim") == 5
    assert f.count("[0:a]atrim") == 5
    # 中間ファイルや別 input は参照されない
    assert "[1:" not in f
    assert "[2:" not in f
