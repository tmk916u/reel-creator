"""オートリフレーム: 被写体(人物)を検出して 9:16 にクロップする仮想カメラ。

横/引きの動画でも被写体を中心に保ったまま縦リールへ変換する。静的 letterbox
正規化 (ffmpeg.py の vf_resize) の代わりに、voice_segment ごとに被写体中心へ寄せた
crop 窓を ffmpeg に渡す。

設計方針 (v1):
- YOLOv8(person) で各サンプルフレームの人物 bbox を検出
- segment 内サンプルの中心座標の median を採る (移動・誤検出にロバスト)
- 隣接 segment 間で中心を EMA 平滑化し、カット境界での飛びを抑える
- 未検出 segment は中央 crop にフォールバック
- crop は常に 9:16 でフレーム内にクランプ

既知の制限: segment 内では静的 crop のため、長い segment 中に被写体が大きく動くと
枠から外れうる (トーク主体の動画では実用上問題にならない)。重い依存(ultralytics)は
遅延 import し、enable_auto_reframe=False のときは一切ロードしない。
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

TARGET_W = 1080
TARGET_H = 1920
TARGET_AR = TARGET_W / TARGET_H  # 9:16 = 0.5625


def _model_path() -> str:
    return os.environ.get("REFRAME_MODEL_PATH", "/opt/models/yolov8n.pt")


@lru_cache(maxsize=1)
def _load_yolo_model(model_path: str):
    """YOLO モデルを遅延ロード(プロセス内で1回)。ultralytics 未導入なら None。"""
    try:
        from ultralytics import YOLO
    except Exception as e:  # pragma: no cover - 環境依存
        logger.warning("ultralytics not available, auto-reframe disabled: %s", e)
        return None
    try:
        return YOLO(model_path)
    except Exception as e:  # pragma: no cover - 環境依存
        logger.warning("YOLO model load failed (%s): %s", model_path, e)
        return None


def probe_dimensions(video_path: str) -> tuple[int, int] | None:
    """動画の (width, height) を ffprobe で取得。失敗時 None。"""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0:s=,", video_path],
            capture_output=True, text=True, check=True,
        )
        w, h = out.stdout.strip().split(",")
        return int(w), int(h)
    except Exception as e:
        logger.warning("probe_dimensions failed: %s", e)
        return None


def compute_crop_window(
    width: int,
    height: int,
    center_x: float | None,
    center_y: float | None,
    padding: float = 0.0,
) -> dict:
    """被写体中心(正規化 0..1)から 9:16 の crop 窓 {w,h,x,y}(px,整数) を計算する。

    center_x/center_y が None のときは中央 crop。crop は必ずフレーム内に収め、
    アスペクトは 9:16 を厳密に保つ。padding は将来用(現状は中心計算に影響なし)。

    純粋関数(I/O なし)なのでユニットテスト可能。
    """
    src_ar = width / height
    if src_ar > TARGET_AR:
        # ソースが 9:16 より横長 → 横方向にクロップ(高さは全体)
        crop_h = height
        crop_w = int(round(height * TARGET_AR))
    else:
        # ソースが 9:16 より縦長/同等 → 縦方向にクロップ(幅は全体)
        crop_w = width
        crop_h = int(round(width / TARGET_AR))
    crop_w = max(2, min(crop_w, width))
    crop_h = max(2, min(crop_h, height))

    cx = (center_x if center_x is not None else 0.5) * width
    cy = (center_y if center_y is not None else 0.5) * height

    x = int(round(cx - crop_w / 2))
    y = int(round(cy - crop_h / 2))
    # フレーム内クランプ
    x = max(0, min(x, width - crop_w))
    y = max(0, min(y, height - crop_h))
    return {"w": crop_w, "h": crop_h, "x": x, "y": y}


def smooth_centers(
    centers: list[tuple[float, float] | None],
    alpha: float = 0.85,
) -> list[tuple[float, float] | None]:
    """segment 列の中心を EMA で平滑化し、カット境界の飛びを抑える。

    None(未検出)は平滑化対象外でそのまま残す(下流で中央フォールバック)。
    alpha は「前フレーム寄り」の強さ(0..1, 大きいほど滑らか)。純粋関数。
    """
    out: list[tuple[float, float] | None] = []
    prev: tuple[float, float] | None = None
    for c in centers:
        if c is None:
            out.append(None)
            continue
        if prev is None:
            sm = c
        else:
            sm = (
                alpha * prev[0] + (1 - alpha) * c[0],
                alpha * prev[1] + (1 - alpha) * c[1],
            )
        out.append(sm)
        prev = sm
    return out


def _pick_subject_center(boxes) -> tuple[float, float] | None:
    """YOLO の boxes(person)から代表被写体の正規化中心を選ぶ。

    最大面積の人物を採用(画面の主役)。boxes は ultralytics Boxes 互換
    (.xyxyn が [N,4] の正規化座標)。検出なしは None。
    """
    try:
        xyxyn = boxes.xyxyn
    except Exception:
        return None
    if xyxyn is None or len(xyxyn) == 0:
        return None
    best = None
    best_area = -1.0
    for b in xyxyn:
        x1, y1, x2, y2 = float(b[0]), float(b[1]), float(b[2]), float(b[3])
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        if area > best_area:
            best_area = area
            best = ((x1 + x2) / 2, (y1 + y2) / 2)
    return best


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _detect_segment_center(
    model, video_path: str, start: float, end: float, sample_fps: float,
) -> tuple[float, float] | None:
    """[start,end] を sample_fps で抽出し、人物中心の median を返す。未検出 None。"""
    duration = max(0.0, end - start)
    if duration <= 0:
        return None
    with tempfile.TemporaryDirectory(prefix="reframe_") as td:
        pattern = os.path.join(td, "f_%04d.jpg")
        cmd = [
            "ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", video_path,
            "-t", f"{duration:.3f}", "-vf", f"fps={sample_fps}",
            "-q:v", "3", pattern, "-loglevel", "error",
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True, timeout=120)
        except Exception as e:
            logger.warning("reframe frame sampling failed [%.1f-%.1f]: %s", start, end, e)
            return None
        frames = sorted(Path(td).glob("f_*.jpg"))
        if not frames:
            return None
        xs: list[float] = []
        ys: list[float] = []
        for fp in frames:
            try:
                res = model.predict(str(fp), classes=[0], verbose=False)
            except Exception as e:  # pragma: no cover - 環境依存
                logger.warning("YOLO predict failed: %s", e)
                continue
            if not res:
                continue
            c = _pick_subject_center(res[0].boxes)
            if c is not None:
                xs.append(c[0])
                ys.append(c[1])
        if not xs:
            return None
        return _median(xs), _median(ys)


def compute_reframe_windows(
    video_path: str,
    segments: list[dict],
    sample_fps: float = 3.0,
    smoothing: float = 0.85,
    padding: float = 0.15,
    model_path: str | None = None,
) -> list[dict | None] | None:
    """各 voice_segment に対する crop 窓のリストを返す。

    返り値: segments と同順・同数の [{w,h,x,y} | None]。None は「この segment は
    従来の letterbox にフォールバック」を意味する。全体が無効(モデル無し/縦動画で
    crop 不要)なら None を返し、呼び出し側は従来パイプラインを使う。
    """
    if not segments:
        return None
    model = _load_yolo_model(model_path or _model_path())
    if model is None:
        logger.info("auto-reframe: model unavailable, skipping")
        return None
    dims = probe_dimensions(video_path)
    if dims is None:
        return None
    width, height = dims
    # 既に 9:16 以下(縦長)の動画は crop の余地が乏しいのでスキップ(従来処理)
    if width / height <= TARGET_AR:
        logger.info("auto-reframe: source already vertical (%dx%d), skipping", width, height)
        return None

    raw_centers: list[tuple[float, float] | None] = [
        _detect_segment_center(model, video_path, float(s["start"]), float(s["end"]), sample_fps)
        for s in segments
    ]
    detected = sum(1 for c in raw_centers if c is not None)
    logger.info("auto-reframe: %d/%d segments に被写体検出", detected, len(segments))
    if detected == 0:
        return None
    smoothed = smooth_centers(raw_centers, alpha=smoothing)
    windows: list[dict | None] = []
    for c in smoothed:
        if c is None:
            windows.append(None)
        else:
            windows.append(compute_crop_window(width, height, c[0], c[1], padding))
    return windows
