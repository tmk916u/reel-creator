from pathlib import Path

from app.services.ffmpeg import (
    LUT_FILES,
    _build_color_grade_filter,
    resolve_lut_path,
)

LUTS_DIR = Path(__file__).resolve().parents[1] / "app" / "data" / "luts"


def test_resolve_none_returns_none(tmp_path):
    assert resolve_lut_path("none", tmp_path) is None


def test_resolve_unknown_returns_none(tmp_path):
    assert resolve_lut_path("sepia", tmp_path) is None


def test_resolve_missing_file_returns_none(tmp_path):
    # テイスト名は既知だがファイルが無い → None
    assert resolve_lut_path("cinematic", tmp_path) is None


def test_resolve_existing_file(tmp_path):
    (tmp_path / "cinematic.cube").write_text("LUT_3D_SIZE 2\n", encoding="utf-8")
    resolved = resolve_lut_path("cinematic", tmp_path)
    assert resolved == str(tmp_path / "cinematic.cube")


def test_build_filter_none():
    assert _build_color_grade_filter(None) is None


def test_build_filter_path():
    assert _build_color_grade_filter("/x/y.cube") == "lut3d=file=/x/y.cube"


def test_bundled_luts_exist_and_valid():
    # 同梱 .cube が全テイストで存在し、LUT_3D_SIZE^3 のデータ行を持つことを検証
    for name, filename in LUT_FILES.items():
        path = LUTS_DIR / filename
        assert path.exists(), f"{filename} 未配置（gen_luts.py を実行）"
        size = None
        data_rows = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("TITLE"):
                continue
            if line.startswith("LUT_3D_SIZE"):
                size = int(line.split()[1])
                continue
            parts = line.split()
            assert len(parts) == 3, f"{filename}: 不正なデータ行 {line!r}"
            data_rows += 1
        assert size is not None, f"{filename}: LUT_3D_SIZE 行が無い"
        assert data_rows == size ** 3, f"{filename}: 行数 {data_rows} != {size}^3"


def test_resolve_works_with_bundled_assets():
    # 実アセットに対して各テイストが解決できる
    for name in ("minimal", "cinematic", "monochrome", "pop"):
        resolved = resolve_lut_path(name, LUTS_DIR)
        assert resolved is not None
        assert resolved.endswith(f"{name}.cube")
