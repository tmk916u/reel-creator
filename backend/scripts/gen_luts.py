#!/usr/bin/env python3
"""テイスト別 .cube 3D LUT を手続き的に生成する。

外部 LUT のライセンス問題を避けるため、gain/コントラスト/彩度カーブから
ゼロベースで .cube を生成する（生成物は CC0 相当）。見栄えは簡易だが安全。
差し替えたい場合は backend/app/data/luts/<name>.cube を上書きすればよい。

実行:
    cd backend && python scripts/gen_luts.py
"""
from __future__ import annotations

from pathlib import Path

LUT_SIZE = 33
OUT_DIR = Path(__file__).resolve().parents[1] / "app" / "data" / "luts"


def _clamp(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _luma(r: float, g: float, b: float) -> float:
    return 0.299 * r + 0.587 * g + 0.114 * b


def _contrast(x: float, amount: float) -> float:
    # 0.5 を中心にした線形コントラスト
    return _clamp(0.5 + (x - 0.5) * amount)


def _saturate(r: float, g: float, b: float, sat: float) -> tuple[float, float, float]:
    l = _luma(r, g, b)
    return (
        _clamp(l + (r - l) * sat),
        _clamp(l + (g - l) * sat),
        _clamp(l + (b - l) * sat),
    )


def t_minimal(r: float, g: float, b: float) -> tuple[float, float, float]:
    # 軽いコントラスト + わずかな彩度低下。雑誌風の落ち着き。
    r, g, b = _contrast(r, 1.06), _contrast(g, 1.06), _contrast(b, 1.06)
    return _saturate(r, g, b, 0.92)


def t_cinematic(r: float, g: float, b: float) -> tuple[float, float, float]:
    # ティール&オレンジ: シャドウを青緑へ、ハイライトをオレンジへ。
    l = _luma(r, g, b)
    r, g, b = _contrast(r, 1.12), _contrast(g, 1.10), _contrast(b, 1.12)
    hi = l * l            # ハイライト重み
    sh = (1.0 - l) ** 2   # シャドウ重み
    r = _clamp(r + 0.06 * hi - 0.02 * sh)
    g = _clamp(g + 0.015 * hi + 0.015 * sh)
    b = _clamp(b - 0.05 * hi + 0.07 * sh)
    return _saturate(r, g, b, 1.05)


def t_monochrome(r: float, g: float, b: float) -> tuple[float, float, float]:
    # 彩度0のグレースケール + わずかな暖色ティント + 軽いコントラスト。
    l = _contrast(_luma(r, g, b), 1.08)
    return _clamp(l * 1.03), _clamp(l), _clamp(l * 0.97)


def t_pop(r: float, g: float, b: float) -> tuple[float, float, float]:
    # 彩度・明度ブースト。SNS 映えの元気め。
    r, g, b = _contrast(r, 1.08), _contrast(g, 1.08), _contrast(b, 1.08)
    r, g, b = _saturate(r, g, b, 1.28)
    return _clamp(r + 0.02), _clamp(g + 0.02), _clamp(b + 0.02)


TASTES = {
    "minimal": t_minimal,
    "cinematic": t_cinematic,
    "monochrome": t_monochrome,
    "pop": t_pop,
}


def write_cube(name: str, fn) -> Path:
    lines = [f'TITLE "{name}"', f"LUT_3D_SIZE {LUT_SIZE}", ""]
    n = LUT_SIZE - 1
    # .cube は red が最速で変化する（r 内側ループ）
    for bi in range(LUT_SIZE):
        for gi in range(LUT_SIZE):
            for ri in range(LUT_SIZE):
                r, g, b = fn(ri / n, gi / n, bi / n)
                lines.append(f"{r:.6f} {g:.6f} {b:.6f}")
    out = OUT_DIR / f"{name}.cube"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, fn in TASTES.items():
        path = write_cube(name, fn)
        print(f"wrote {path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
