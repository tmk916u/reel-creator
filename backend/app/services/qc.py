"""出力動画の自動 QC（品質チェック）。

処理後の指標から、投稿前に気づきたい問題（尺崩れ・縦型でない・誤字幕など）を
検出して警告リストを返す。evaluate_qc は純粋関数（I/O なし）でテスト可能。

各 issue: {"severity": "warn"|"info", "code": str, "message": str}
severity warn = 確認推奨 / info = 念のため通知。
"""
from __future__ import annotations

# 縦型(9:16)とみなす許容（これを超える横長はリールで余白が入りうる）
_VERTICAL_AR = 9 / 16
_VERTICAL_TOLERANCE = 0.02

# 誤字幕とみなす suspicious セグメント比率の閾値
_HALLUCINATION_RATIO = 0.4


def evaluate_qc(metrics: dict) -> list[dict]:
    """処理後の指標から QC 警告リストを返す（純粋関数）。

    metrics keys:
      original_duration, processed_duration: float
      width, height: int | None
      subtitles_enabled: bool
      segment_count: int
      suspicious_count: int
    """
    issues: list[dict] = []

    original = float(metrics.get("original_duration") or 0.0)
    processed = float(metrics.get("processed_duration") or 0.0)

    # 1) 出力が極端に短い（無音判定が厳しすぎる等の事故）
    if processed < 3.0:
        issues.append({
            "severity": "warn",
            "code": "tiny_output",
            "message": (
                f"出力が約{processed:.1f}秒と極端に短いです。"
                "無音判定が厳しすぎる可能性があります（しきい値を緩めて再処理を検討）。"
            ),
        })
    # 2) 元尺から大幅に短縮（削りすぎの疑い）
    elif original >= 20.0 and processed / original < 0.2:
        issues.append({
            "severity": "warn",
            "code": "heavy_trim",
            "message": (
                f"元の{original:.0f}秒から{processed:.0f}秒へ大幅に短縮されました。"
                "意図しない削りすぎでないか確認してください。"
            ),
        })

    # 3) 縦型(9:16)でない
    width = metrics.get("width")
    height = metrics.get("height")
    if width and height:
        ar = width / height
        if ar > _VERTICAL_AR + _VERTICAL_TOLERANCE:
            issues.append({
                "severity": "warn",
                "code": "not_vertical",
                "message": (
                    f"縦型(9:16)ではありません（{width}x{height}）。"
                    "リールでは上下に余白が入る可能性があります。"
                ),
            })

    # 4) 字幕の誤認識（プロンプト反響・断片化の多発）
    subtitles_enabled = bool(metrics.get("subtitles_enabled"))
    segment_count = int(metrics.get("segment_count") or 0)
    suspicious_count = int(metrics.get("suspicious_count") or 0)
    if subtitles_enabled and segment_count > 0:
        ratio = suspicious_count / segment_count
        if ratio >= _HALLUCINATION_RATIO:
            issues.append({
                "severity": "warn",
                "code": "caption_hallucination",
                "message": (
                    f"字幕の約{round(ratio * 100)}%に誤認識の疑いがあります。"
                    "字幕を確認・修正するか、字幕オフを検討してください。"
                ),
            })
    # 5) 字幕 ON なのに 0 件
    elif subtitles_enabled and segment_count == 0:
        issues.append({
            "severity": "info",
            "code": "no_captions",
            "message": (
                "字幕 ON ですが字幕が生成されませんでした"
                "（音声が無い/小さい可能性があります）。"
            ),
        })

    # warn を先頭に並べる
    issues.sort(key=lambda i: 0 if i["severity"] == "warn" else 1)
    return issues
