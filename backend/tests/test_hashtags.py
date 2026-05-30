import pytest

from app.services.hashtags import normalize_hashtags


class TestNormalizeHashtags:
    def test_empty(self):
        assert normalize_hashtags(None) == ""
        assert normalize_hashtags("") == ""
        assert normalize_hashtags("   ") == ""

    def test_space_separated_adds_hash(self):
        assert normalize_hashtags("ダイエット 食事改善") == "#ダイエット #食事改善"

    def test_newline_and_comma_separated(self):
        assert normalize_hashtags("ダイエット\n食事改善, ボディメイク") == (
            "#ダイエット #食事改善 #ボディメイク"
        )

    def test_existing_hash_preserved_single(self):
        assert normalize_hashtags("#ダイエット ##食事改善") == "#ダイエット #食事改善"

    def test_dedupe(self):
        assert normalize_hashtags("#a a #a") == "#a"

    def test_five_ok(self):
        out = normalize_hashtags("a b c d e")
        assert out == "#a #b #c #d #e"

    def test_six_raises(self):
        with pytest.raises(ValueError):
            normalize_hashtags("a b c d e f")
