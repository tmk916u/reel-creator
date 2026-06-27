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


def _lift(x: float, amount: float) -> float:
    # 黒を持ち上げてマット/フィルム調にする（0..1 を amount..1 に圧縮）
    return _clamp(amount + x * (1.0 - amount))


def t_minimal(r: float, g: float, b: float) -> tuple[float, float, float]:
    # エディトリアル: しっかりコントラスト + 彩度をかなり落とし + 黒を少し持ち上げて
    # マットに + ごく薄い寒色。雑誌のモノトーン特集のような洗練。
    r, g, b = _contrast(r, 1.14), _contrast(g, 1.14), _contrast(b, 1.14)
    r, g, b = _saturate(r, g, b, 0.78)
    r, g, b = _lift(r, 0.03), _lift(g, 0.03), _lift(b, 0.045)  # 影をわずかに寒色マット
    return r, g, b


def t_cinematic(r: float, g: float, b: float) -> tuple[float, float, float]:
    # ティール&オレンジ（強め）: シャドウを青緑、ハイライトをオレンジへはっきり振る。
    l = _luma(r, g, b)
    r, g, b = _contrast(r, 1.20), _contrast(g, 1.16), _contrast(b, 1.20)
    hi = l * l            # ハイライト重み
    sh = (1.0 - l) ** 2   # シャドウ重み
    r = _clamp(r + 0.13 * hi - 0.05 * sh)
    g = _clamp(g + 0.02 * hi + 0.03 * sh)
    b = _clamp(b - 0.10 * hi + 0.14 * sh)
    r, g, b = _saturate(r, g, b, 1.12)
    r, g, b = _lift(r, 0.025), _lift(g, 0.03), _lift(b, 0.04)  # シャドウにティールのマット
    return r, g, b


def t_monochrome(r: float, g: float, b: float) -> tuple[float, float, float]:
    # 彩度0 + 強めコントラストでメリハリ + わずかな暖色ティント（セピア寄り）。
    l = _contrast(_luma(r, g, b), 1.18)
    l = _lift(l, 0.02)
    return _clamp(l * 1.06), _clamp(l), _clamp(l * 0.92)


def t_pop(r: float, g: float, b: float) -> tuple[float, float, float]:
    # 彩度・明度を大きくブースト。SNS 映えのビビッド。
    r, g, b = _contrast(r, 1.14), _contrast(g, 1.14), _contrast(b, 1.14)
    r, g, b = _saturate(r, g, b, 1.45)
    return _clamp(r + 0.03), _clamp(g + 0.03), _clamp(b + 0.03)


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
