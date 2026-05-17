import pytest
from app.services.ffmpeg import (
    get_video_duration,
    extract_audio,
    _build_cut_concat_filter,
    _fit_overlay_text,
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


def test_fit_overlay_text_short_keeps_base_size():
    """短いテキストはそのまま base_size で 1 行"""
    wrapped, size = _fit_overlay_text("短い", base_size=80)
    assert wrapped == "短い"
    assert size == 80


def test_fit_overlay_text_long_wraps_to_two_lines():
    """長いテキストは句読点位置で 2 行に折返し、フォントを縮める"""
    wrapped, size = _fit_overlay_text("痛みの原因は筋肉ではなく、血流だった", base_size=80)
    assert "\n" in wrapped
    line1, line2 = wrapped.split("\n", 1)
    # 句読点「、」の直後で改行されている
    assert line1.endswith("、")
    assert line2 == "血流だった"
    # フォントは縮められている (80→75 程度)
    assert size < 80
    assert size >= 40  # min_size 以上


def test_fit_overlay_text_break_priority_punctuation_over_particle():
    """句読点があれば助詞より優先して使う"""
    wrapped, _ = _fit_overlay_text("これはとても、長いテキストです", base_size=80)
    # 「、」で切れる
    assert wrapped.split("\n", 1)[0].endswith("、")


def test_fit_overlay_text_no_breaker_falls_back_to_middle():
    """区切り文字が無い場合は中央で分割"""
    text = "ABCDEFGHIJKLMNOP"  # 16文字、区切りなし
    wrapped, size = _fit_overlay_text(text, base_size=80, max_chars_per_line=8)
    assert "\n" in wrapped
    line1, line2 = wrapped.split("\n", 1)
    assert len(line1) + len(line2) == len(text)


def test_fit_overlay_text_min_size_respected():
    """極端に長いテキストでも min_size を下回らない"""
    text = "あ" * 100
    _, size = _fit_overlay_text(text, base_size=80, min_size=40)
    assert size >= 40
