# backend/tests/test_jump_cut.py
from pathlib import Path

from app.services.jump_cut import (
    detect_filler_ranges,
    detect_oversized_words,
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


def test_detect_oversized_words_finds_silence_in_long_word():
    """word duration > max_word_duration かつ word 内に VAD silence がある場合、
    silence 部分のみを margin 引いて削除候補にする。"""
    # 「首」 が 4.24秒 続くケース。 word 内に 3.5秒の VAD silence
    words = [
        {"start": 37.18, "end": 41.42, "text": "首"},
        {"start": 41.42, "end": 41.66, "text": "が"},
    ]
    vad_silences = [{"start": 37.30, "end": 41.10}]  # word 内に 3.8s 無音
    cuts = detect_oversized_words(
        words, vad_silences, max_word_duration=1.0, margin=0.1,
    )
    assert len(cuts) == 1
    # 37.30 + 0.1 = 37.40, 41.10 - 0.1 = 41.00
    assert abs(cuts[0]["start"] - 37.40) < 1e-6
    assert abs(cuts[0]["end"] - 41.00) < 1e-6


def test_detect_oversized_words_protects_speech_in_long_word():
    """VAD-aware の本質テスト: ASR が誤って 12秒の word を推定した場合、
    word 内に実発話があれば VAD silence と重なる部分だけを削除する。

    例: 「お」 word (33.06-45.14, 12.08s) 内に
        - 無音 33.20-42.86 (9.66s) → 削除
        - 発話 42.86-45.14 (「お客様が悩まれているダイエット」) → 保護
    """
    words = [{"start": 33.06, "end": 45.14, "text": "お"}]
    vad_silences = [{"start": 33.20, "end": 42.86}]  # word 内の無音のみ
    cuts = detect_oversized_words(words, vad_silences, max_word_duration=1.0)
    assert len(cuts) == 1
    # 削除は無音区間内のみ。 word の末尾 (発話部分) は保護される
    assert cuts[0]["end"] <= 42.86, f"発話領域まで削除している: {cuts[0]}"


def test_detect_oversized_words_no_silence_in_word_skips():
    """long word でも word 内に VAD silence が無い場合は削除しない (安全側)"""
    words = [{"start": 0.0, "end": 5.0, "text": "あ"}]  # 5秒の long word
    vad_silences = [{"start": 10.0, "end": 15.0}]  # 別の場所
    cuts = detect_oversized_words(words, vad_silences, max_word_duration=1.0)
    assert cuts == []


def test_detect_oversized_words_skips_short_word():
    """通常の word は VAD silence の有無に関わらず対象外"""
    words = [
        {"start": 0.0, "end": 0.5, "text": "あ"},
        {"start": 0.5, "end": 1.4, "text": "い"},
    ]
    vad_silences = [{"start": 0.2, "end": 1.3}]
    cuts = detect_oversized_words(words, vad_silences, max_word_duration=1.0)
    assert cuts == []


def test_detect_oversized_words_min_cut_length_filters_tiny_silences():
    """word 内 silence が min_cut_length 未満なら削除しない"""
    words = [{"start": 0.0, "end": 5.0, "text": "あ"}]
    # margin=0.1 を引くと有効長 0.1s しかない
    vad_silences = [{"start": 1.0, "end": 1.3}]
    cuts = detect_oversized_words(
        words, vad_silences, max_word_duration=1.0,
        min_cut_length=0.3, margin=0.1,
    )
    assert cuts == []


def test_detect_oversized_words_empty():
    assert detect_oversized_words([], []) == []


def test_detect_redundant_speech_too_few_words():
    """word 数が少なすぎる場合は空"""
    words = _make_words(["短", "い", "発", "話"])
    cuts = detect_redundant_speech(words, window_words=10)
    assert cuts == []


def test_oversized_cut_inside_word_is_dropped_by_snap():
    """oversized_cuts は word 内部の中央削除なので、 snap を通すと両端が word 端に
    弾かれて削除区間が反転 → 破棄されることを確認する（バグの再現）。

    このため video.py では oversized_cuts を snap から除外し、 snap 後に
    merge_ranges で統合する必要がある。
    """
    from app.services.vad import snap_silences_to_word_boundaries

    # ReazonSpeech subword timestamp 推定ノイズによる oversized word (5.12s)
    words = [{"start": 3.59, "end": 8.71, "text": "お"}]
    # detect_oversized_words 相当: word の中央 (keep_head=0.2, keep_tail=0.2) を削除
    oversized = [{"start": 3.79, "end": 8.51}]  # 4.72s 削除候補

    snapped = snap_silences_to_word_boundaries(oversized, words)
    # word 内部のため両端とも word 境界で反転 → 破棄
    assert snapped == [], (
        f"snap で oversized が破棄される想定だが、 残った: {snapped}"
    )


def test_oversized_cut_preserved_when_merged_after_snap():
    """video.py の修正フロー: oversized_cuts を snap 後に merge することで、
    word 内部の中央削除を保ちつつ、 silences/extra_cuts の word 境界 snap も両立できる。
    """
    from app.services.vad import snap_silences_to_word_boundaries

    words = [
        {"start": 3.59, "end": 8.71, "text": "お"},
        {"start": 9.05, "end": 9.30, "text": "結"},
    ]
    # word の境界をまたぐ silence (snap で word 端に揃えるべき)
    silences = [{"start": 8.65, "end": 9.10}]
    # word 内部の oversized 削除 (snap させてはいけない)
    oversized = [{"start": 3.79, "end": 8.51}]

    snapped = snap_silences_to_word_boundaries(silences, words)
    final = merge_ranges(snapped + oversized)

    # oversized の中央削除が最終結果に残っている
    assert any(
        abs(c["start"] - 3.79) < 0.01 and abs(c["end"] - 8.51) < 0.01
        for c in final
    ), f"oversized 削除が残っていない: {final}"
