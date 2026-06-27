from types import SimpleNamespace

from app.services import reframe
from app.services.reframe import (
    compute_crop_window,
    smooth_centers,
    _pick_subject_center,
    _median,
)


# === compute_crop_window ===

def test_crop_landscape_centered_default():
    # 1920x1080 (16:9 横) → 9:16 縦crop。中心 None で中央。
    w = compute_crop_window(1920, 1080, None, None)
    # crop_h=1080, crop_w=round(1080*9/16)=608(偶数化), 中央 x=(1920-608)/2
    assert w["h"] == 1080
    assert abs(w["w"] - 608) <= 1
    assert w["y"] == 0
    assert w["x"] == (1920 - w["w"]) // 2 or abs(w["x"] - (1920 - w["w"]) / 2) <= 1


def test_crop_follows_subject_left():
    # 被写体が左寄り(center_x=0.2) → crop x が中央より左
    center = compute_crop_window(1920, 1080, 0.5, 0.5)
    left = compute_crop_window(1920, 1080, 0.2, 0.5)
    assert left["x"] < center["x"]
    assert left["w"] == center["w"]  # サイズは不変


def test_crop_clamps_within_frame():
    # 被写体が極端に右(center_x=0.99) でも crop はフレーム内に収まる
    w = compute_crop_window(1920, 1080, 0.99, 0.5)
    assert w["x"] >= 0
    assert w["x"] + w["w"] <= 1920
    assert w["y"] >= 0
    assert w["y"] + w["h"] <= 1080


def test_crop_aspect_is_9_16():
    w = compute_crop_window(1920, 1080, 0.5, 0.5)
    ar = w["w"] / w["h"]
    assert abs(ar - 9 / 16) < 0.02


def test_crop_tall_source_crops_vertically():
    # 1080x2400 (9:16 より縦長) → 幅全体, 縦方向 crop
    w = compute_crop_window(1080, 2400, 0.5, 0.3)
    assert w["w"] == 1080
    assert w["h"] < 2400
    assert w["y"] + w["h"] <= 2400


# === smooth_centers ===

def test_smooth_preserves_none():
    out = smooth_centers([(0.5, 0.5), None, (0.2, 0.2)], alpha=0.8)
    assert out[1] is None
    assert out[0] == (0.5, 0.5)  # 先頭は素通し


def test_smooth_dampens_jumps():
    # 大きく飛ぶ中心を EMA で緩和(2点目が1点目寄りに引っ張られる)
    out = smooth_centers([(0.1, 0.5), (0.9, 0.5)], alpha=0.8)
    assert out[0] == (0.1, 0.5)
    # 0.8*0.1 + 0.2*0.9 = 0.26 (生の0.9より大幅に手前)
    assert abs(out[1][0] - 0.26) < 1e-6


def test_smooth_empty():
    assert smooth_centers([]) == []


# === _pick_subject_center ===

def test_pick_largest_person():
    # 2人: 小(左) と 大(右) → 大きい方の中心を採用
    boxes = SimpleNamespace(xyxyn=[
        [0.0, 0.4, 0.1, 0.5],   # 小: 面積 0.1*0.1
        [0.6, 0.1, 0.9, 0.9],   # 大: 面積 0.3*0.8
    ])
    c = _pick_subject_center(boxes)
    assert c is not None
    assert abs(c[0] - 0.75) < 1e-6  # 大きい方の中心x=(0.6+0.9)/2
    assert abs(c[1] - 0.5) < 1e-6


def test_pick_no_detection_returns_none():
    assert _pick_subject_center(SimpleNamespace(xyxyn=[])) is None


def test_pick_handles_missing_attr():
    assert _pick_subject_center(SimpleNamespace()) is None


# === _median ===

def test_median_odd_even():
    assert _median([3.0, 1.0, 2.0]) == 2.0
    assert _median([1.0, 2.0, 3.0, 4.0]) == 2.5


# === compute_reframe_windows ガード ===

def test_reframe_returns_none_without_model(monkeypatch):
    # モデルがロードできない環境では None(従来パイプライン)
    monkeypatch.setattr(reframe, "_load_yolo_model", lambda p: None)
    assert reframe.compute_reframe_windows("/tmp/x.mp4", [{"start": 0, "end": 1}]) is None


def test_reframe_skips_vertical_source(monkeypatch):
    # 既に縦動画(9:16以下)は crop の余地なしでスキップ
    monkeypatch.setattr(reframe, "_load_yolo_model", lambda p: object())
    monkeypatch.setattr(reframe, "probe_dimensions", lambda v: (1080, 1920))
    assert reframe.compute_reframe_windows("/tmp/x.mp4", [{"start": 0, "end": 1}]) is None


def test_reframe_empty_segments():
    assert reframe.compute_reframe_windows("/tmp/x.mp4", []) is None
