# backend/tests/test_jump_cut.py
from pathlib import Path

from app.services.jump_cut import (
    detect_filler_ranges,
    detect_tempo_ranges,
    load_fillers,
    merge_ranges,
)


def test_load_fillers_returns_set():
    """デフォルトの辞書がロードできる"""
    fillers = load_fillers()
    assert isinstance(fillers, set)
    assert "えー" in fillers
    assert "あのー" in fillers


def test_load_fillers_missing_file(tmp_path: Path):
    """ファイルが無い場合は空セットを返す"""
    fillers = load_fillers(tmp_path / "nonexistent.txt")
    assert fillers == set()


def test_load_fillers_custom_path(tmp_path: Path):
    """カスタムパスから読み込める。コメント行と空行は無視される"""
    p = tmp_path / "fillers.txt"
    p.write_text("# comment\nfoo\n\nbar\n", encoding="utf-8")
    fillers = load_fillers(p)
    assert fillers == {"foo", "bar"}


def test_detect_filler_ranges_basic():
    """フィラー単語の範囲を抽出する"""
    words = [
        {"start": 0.0, "end": 0.3, "text": "えー"},
        {"start": 0.3, "end": 1.0, "text": "今日は"},
        {"start": 1.0, "end": 1.3, "text": "あのー"},
        {"start": 1.3, "end": 2.0, "text": "雨です"},
    ]
    fillers = {"えー", "あのー"}
    ranges = detect_filler_ranges(words, fillers)
    assert ranges == [
        {"start": 0.0, "end": 0.3},
        {"start": 1.0, "end": 1.3},
    ]


def test_detect_filler_ranges_strips_punctuation():
    """句読点付き単語もマッチする"""
    words = [
        {"start": 0.0, "end": 0.3, "text": "えー、"},
    ]
    ranges = detect_filler_ranges(words, {"えー"})
    assert ranges == [{"start": 0.0, "end": 0.3}]


def test_detect_filler_ranges_empty_fillers():
    """フィラー辞書が空なら何も検出しない"""
    words = [{"start": 0.0, "end": 0.3, "text": "えー"}]
    assert detect_filler_ranges(words, set()) == []


def test_detect_tempo_ranges_long_pause():
    """文末で長い間があれば短縮区間を作る"""
    words = [
        {"start": 0.0, "end": 1.0, "text": "こんにちは。"},
        {"start": 2.0, "end": 3.0, "text": "今日は"},
    ]
    ranges = detect_tempo_ranges(words, max_pause=0.4, target_pause=0.2)
    assert len(ranges) == 1
    assert ranges[0]["start"] == 1.2
    assert ranges[0]["end"] == 2.0


def test_detect_tempo_ranges_short_pause_preserved():
    """短い間は維持する"""
    words = [
        {"start": 0.0, "end": 1.0, "text": "こんにちは。"},
        {"start": 1.3, "end": 2.0, "text": "今日は"},
    ]
    assert detect_tempo_ranges(words, max_pause=0.4) == []


def test_detect_tempo_ranges_non_punctuation_ignored():
    """句読点でない単語末尾は対象外"""
    words = [
        {"start": 0.0, "end": 1.0, "text": "こんにちは"},
        {"start": 2.0, "end": 3.0, "text": "今日は"},
    ]
    assert detect_tempo_ranges(words) == []


def test_merge_ranges_overlapping():
    """重複する区間を1つに統合する"""
    ranges = [
        {"start": 0.0, "end": 1.0},
        {"start": 0.5, "end": 1.5},
    ]
    assert merge_ranges(ranges) == [{"start": 0.0, "end": 1.5}]


def test_merge_ranges_adjacent_within_threshold():
    """閾値以下のギャップは連結する"""
    ranges = [
        {"start": 0.0, "end": 1.0},
        {"start": 1.02, "end": 2.0},
    ]
    assert merge_ranges(ranges, join_threshold=0.05) == [{"start": 0.0, "end": 2.0}]


def test_merge_ranges_disjoint():
    """離れた区間はそのまま"""
    ranges = [
        {"start": 0.0, "end": 1.0},
        {"start": 2.0, "end": 3.0},
    ]
    assert merge_ranges(ranges) == [
        {"start": 0.0, "end": 1.0},
        {"start": 2.0, "end": 3.0},
    ]


def test_merge_ranges_unsorted_input():
    """未ソート入力でも正しく統合する"""
    ranges = [
        {"start": 2.0, "end": 3.0},
        {"start": 0.0, "end": 1.0},
    ]
    assert merge_ranges(ranges) == [
        {"start": 0.0, "end": 1.0},
        {"start": 2.0, "end": 3.0},
    ]


def test_merge_ranges_empty():
    assert merge_ranges([]) == []
