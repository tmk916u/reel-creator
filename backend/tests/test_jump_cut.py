# backend/tests/test_jump_cut.py
from pathlib import Path

from app.services.jump_cut import (
    detect_filler_ranges,
    detect_redundant_speech,
    detect_tempo_ranges,
    detect_word_gaps,
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


def _make_words(texts: list[str], start_offset: float = 0.0, dur: float = 0.4) -> list[dict]:
    return [
        {"start": start_offset + i * dur, "end": start_offset + (i + 1) * dur, "text": t}
        for i, t in enumerate(texts)
    ]


def test_detect_redundant_speech_finds_distant_repeat():
    """離れた2箇所で似た発話 → 後段を削除候補に"""
    intro = _make_words(["健", "康", "は", "運", "動", "睡", "眠", "栄", "養", "が", "大", "事", "だ"])
    middle = _make_words(["別", "の", "話", "を", "し", "て", "い", "る", "間", "に", "時", "間", "が", "流", "れ", "る"], start_offset=10.0)
    repeat = _make_words(["健", "康", "は", "運", "動", "睡", "眠", "栄", "養", "が", "大", "事", "だ"], start_offset=30.0)
    words = intro + middle + repeat
    cuts = detect_redundant_speech(words, window_words=12, similarity_threshold=0.7, min_gap_seconds=5.0)
    assert len(cuts) >= 1
    # 削除対象は後段の repeat 周辺
    assert all(c["start"] >= 30.0 for c in cuts)


def test_detect_redundant_speech_ignores_near_repeats():
    """直近の言い直し（5秒以内）は LLM 担当のためスキップする"""
    a = _make_words(["こ", "ん", "に", "ち", "は", "私", "は", "山", "田", "で", "す", "今", "日"])
    # 同じ内容を 2 秒後（min_gap=5.0 未満）に繰り返し → 検出されないはず
    b = _make_words(["こ", "ん", "に", "ち", "は", "私", "は", "山", "田", "で", "す", "今", "日"], start_offset=2.0)
    cuts = detect_redundant_speech(a + b, window_words=12, similarity_threshold=0.7, min_gap_seconds=5.0)
    assert cuts == []


def test_detect_redundant_speech_no_duplicate_no_cuts():
    """重複がない普通の発話は cut 0 件"""
    words = _make_words(["今", "日", "は", "晴", "れ", "の", "い", "い", "天", "気", "で", "散", "歩"]) + \
            _make_words(["明", "日", "は", "雨", "の", "予", "報", "だ", "か", "ら", "出", "か", "け"], start_offset=20.0)
    cuts = detect_redundant_speech(words, window_words=10, similarity_threshold=0.7)
    assert cuts == []


def test_detect_word_gaps_compresses_long_gap():
    """word 間ギャップが max_gap を超えると target_gap まで圧縮される"""
    words = [
        {"start": 0.0, "end": 1.0, "text": "あ"},
        {"start": 2.0, "end": 3.0, "text": "い"},  # gap 1.0s
    ]
    cuts = detect_word_gaps(words, max_gap=0.25, target_gap=0.10)
    assert len(cuts) == 1
    # 1.0s の word.end + 0.10s target_gap = 1.10 から 2.0s までを削除
    assert cuts[0]["start"] == 1.10
    assert cuts[0]["end"] == 2.0


def test_detect_word_gaps_short_gap_kept():
    """max_gap 以下のギャップは削除しない（自然な発話の間を保護）"""
    words = [
        {"start": 0.0, "end": 1.0, "text": "あ"},
        {"start": 1.20, "end": 2.20, "text": "い"},  # gap 0.20s（句読点不問でも保護）
    ]
    cuts = detect_word_gaps(words, max_gap=0.25, target_gap=0.10)
    assert cuts == []


def test_detect_word_gaps_ignores_punctuation():
    """detect_tempo_ranges と違い、word の句読点は問わない（あらゆる境界が対象）"""
    words = [
        {"start": 0.0, "end": 1.0, "text": "あ"},  # 句読点なし
        {"start": 1.50, "end": 2.0, "text": "い"},  # gap 0.50s
    ]
    cuts = detect_word_gaps(words, max_gap=0.25, target_gap=0.10)
    assert len(cuts) == 1
    assert cuts[0]["start"] == 1.10
    assert cuts[0]["end"] == 1.50


def test_detect_word_gaps_empty_words():
    assert detect_word_gaps([]) == []


def test_detect_word_gaps_single_word():
    assert detect_word_gaps([{"start": 0.0, "end": 1.0, "text": "あ"}]) == []


def test_detect_redundant_speech_too_few_words():
    """word 数が少なすぎる場合は空"""
    words = _make_words(["短", "い", "発", "話"])
    cuts = detect_redundant_speech(words, window_words=10)
    assert cuts == []
