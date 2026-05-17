# backend/tests/test_silence.py
from app.services.silence import (
    compute_voice_segments,
    protect_words_from_silences,
    build_orig_to_cut2_mapping,
    remap_words_with_mapping,
)


def test_compute_voice_segments_basic():
    """無音区間から有音区間を正しく算出する（padding 無効化）"""
    silences = [
        {"start": 2.0, "end": 4.0},
        {"start": 7.0, "end": 9.0},
    ]
    total_duration = 10.0
    result = compute_voice_segments(silences, total_duration, padding=0)
    assert result == [
        {"start": 0.0, "end": 2.0},
        {"start": 4.0, "end": 7.0},
        {"start": 9.0, "end": 10.0},
    ]


def test_compute_voice_segments_no_silence():
    """無音区間がない場合は動画全体を返す"""
    result = compute_voice_segments([], 10.0, padding=0)
    assert result == [{"start": 0.0, "end": 10.0}]


def test_compute_voice_segments_trim_leading_is_noop():
    """trim_leading=True は現状 no-op（副作用のため無効化）。冒頭無音は
    VAD が silences に含めて自動削除されるため、voice_segments[0].start
    は無音区間の終端のままで字幕の時刻マッピングが壊れない。"""
    silences = [{"start": 0.0, "end": 4.0}]
    out_true = compute_voice_segments(silences, total_duration=10.0, padding=0.0, trim_leading=True)
    out_false = compute_voice_segments(silences, total_duration=10.0, padding=0.0)
    # 両者同じ動作: voice 区間は元動画の 4.0-10.0 として返す
    assert out_true == out_false
    assert out_true == [{"start": 4.0, "end": 10.0}]


def test_compute_voice_segments_all_silence():
    """全体が無音の場合は空リストを返す"""
    silences = [{"start": 0.0, "end": 10.0}]
    result = compute_voice_segments(silences, 10.0, padding=0)
    assert result == []


def test_compute_voice_segments_silence_at_start():
    """冒頭が無音の場合"""
    silences = [{"start": 0.0, "end": 3.0}]
    result = compute_voice_segments(silences, 10.0, padding=0)
    assert result == [{"start": 3.0, "end": 10.0}]


def test_compute_voice_segments_with_extra_cuts():
    """extra_cuts を無音区間とマージして処理する"""
    silences = [{"start": 2.0, "end": 4.0}]
    extra = [{"start": 6.0, "end": 7.0}]
    result = compute_voice_segments(silences, 10.0, padding=0, extra_cuts=extra)
    assert result == [
        {"start": 0.0, "end": 2.0},
        {"start": 4.0, "end": 6.0},
        {"start": 7.0, "end": 10.0},
    ]


def test_compute_voice_segments_overlapping_cuts():
    """無音と extra_cuts が重複しても二重カウントしない"""
    silences = [{"start": 2.0, "end": 5.0}]
    extra = [{"start": 4.0, "end": 6.0}]
    result = compute_voice_segments(silences, 10.0, padding=0, extra_cuts=extra)
    assert result == [
        {"start": 0.0, "end": 2.0},
        {"start": 6.0, "end": 10.0},
    ]


def test_compute_voice_segments_only_extra_cuts():
    """無音なしで extra_cuts だけでも動作する"""
    extra = [{"start": 3.0, "end": 5.0}]
    result = compute_voice_segments([], 10.0, padding=0, extra_cuts=extra)
    assert result == [
        {"start": 0.0, "end": 3.0},
        {"start": 5.0, "end": 10.0},
    ]


def test_compute_voice_segments_min_cut_length_filters_short_cuts():
    """min_cut_length より短いカットは無視される（ジッタ除去）"""
    silences = [{"start": 2.0, "end": 2.05}, {"start": 5.0, "end": 6.0}]
    result = compute_voice_segments(silences, 10.0, padding=0, min_cut_length=0.08)
    # 0.05秒のカットは無視され、5.0-6.0だけが削除される
    assert result == [
        {"start": 0.0, "end": 5.0},
        {"start": 6.0, "end": 10.0},
    ]


def test_compute_voice_segments_padding_expands_segments():
    """padding により有音区間が前後に少し広がる"""
    silences = [{"start": 2.0, "end": 4.0}]
    result = compute_voice_segments(silences, 10.0, padding=0.1)
    assert result == [
        {"start": 0.0, "end": 2.1},
        {"start": 3.9, "end": 10.0},
    ]


def test_compute_voice_segments_padding_merges_overlap():
    """padding 拡張で隣接する有音区間が重なれば統合される"""
    silences = [{"start": 2.0, "end": 2.15}]
    result = compute_voice_segments(silences, 10.0, padding=0.1, min_cut_length=0.05)
    # padding により有音区間 [0, 2.1] と [2.05, 10.0] が重なるので統合
    assert result == [{"start": 0.0, "end": 10.0}]


def test_protect_words_from_silences_boundary_overlap():
    """silence の末尾近くで word が重なる場合、 silence は word の前で切れる。

    再現: silero VAD が 0.0-20.75 を無音と判定したが、 1段目 ASR が 20.38 で
    「客」を認識 → 該当範囲を silence から除外して voice_segments に保護する。
    """
    silences = [{"start": 0.0, "end": 20.75}]
    words = [{"start": 20.38, "end": 20.70, "text": "客"}]
    result = protect_words_from_silences(silences, words, margin=0.1)
    # word.start - margin = 20.28 まで silence、 word.end + margin = 20.80 > silence.end なので後ろは無し
    assert len(result) == 1
    assert result[0]["start"] == 0.0
    assert abs(result[0]["end"] - 20.28) < 1e-9


def test_protect_words_from_silences_middle_split():
    """silence の中央に word がある場合は 2 つに分割される。"""
    silences = [{"start": 0.0, "end": 30.0}]
    words = [{"start": 10.0, "end": 12.0, "text": "あ"}]
    result = protect_words_from_silences(silences, words, margin=0.1)
    assert len(result) == 2
    assert abs(result[0]["start"] - 0.0) < 1e-9
    assert abs(result[0]["end"] - 9.9) < 1e-9
    assert abs(result[1]["start"] - 12.1) < 1e-9
    assert abs(result[1]["end"] - 30.0) < 1e-9


def test_protect_words_from_silences_no_overlap_is_noop():
    """silence と重なる word が無い場合は元の silences を返す。"""
    silences = [{"start": 5.0, "end": 10.0}]
    words = [{"start": 12.0, "end": 13.0, "text": "い"}]
    result = protect_words_from_silences(silences, words, margin=0.1)
    assert result == [{"start": 5.0, "end": 10.0}]


def test_protect_words_from_silences_merges_overlapping_words():
    """複数 word が重なる場合は merge してから 1 つの保護範囲として穴あけ。"""
    silences = [{"start": 0.0, "end": 30.0}]
    words = [
        {"start": 5.0, "end": 7.0, "text": "う"},
        {"start": 6.5, "end": 8.0, "text": "え"},
    ]
    result = protect_words_from_silences(silences, words, margin=0.1)
    # word が 5.0-8.0 にまとまり、 margin 込みで 4.9-8.1 が保護される
    assert len(result) == 2
    assert abs(result[0]["end"] - 4.9) < 1e-9
    assert abs(result[1]["start"] - 8.1) < 1e-9


def test_protect_words_from_silences_empty_words():
    """words が空の場合は元の silences を返す。"""
    silences = [{"start": 0.0, "end": 5.0}]
    result = protect_words_from_silences(silences, [], margin=0.1)
    assert result == [{"start": 0.0, "end": 5.0}]


# === build_orig_to_cut2_mapping / remap_words_with_mapping (simplify-subtitle-to-1stage-remap) ===

def test_build_mapping_without_cut2_voices():
    """施策F 未発動: cut2_voices=None で voice_segments のみで mapping。"""
    voice_segments = [
        {"start": 5.0, "end": 8.0},   # 元時刻 5-8 → cut.mp4 0-3
        {"start": 12.0, "end": 15.0}, # 元時刻 12-15 → cut.mp4 3-6
    ]
    mappings = build_orig_to_cut2_mapping(voice_segments, None)
    assert len(mappings) == 2
    assert mappings[0] == {"orig_start": 5.0, "orig_end": 8.0, "cut2_start": 0.0}
    assert mappings[1] == {"orig_start": 12.0, "orig_end": 15.0, "cut2_start": 3.0}


def test_build_mapping_with_cut2_voices_simple():
    """施策F 発動: cut2_voices で更に削除された範囲を合成。"""
    voice_segments = [{"start": 0.0, "end": 10.0}]   # 元時刻 0-10 → cut.mp4 0-10
    cut2_voices = [
        {"start": 0.0, "end": 3.0},   # cut.mp4 0-3 → cut2 0-3
        {"start": 5.0, "end": 8.0},   # cut.mp4 5-8 → cut2 3-6
    ]
    mappings = build_orig_to_cut2_mapping(voice_segments, cut2_voices)
    # 元時刻 0-3 → cut2 0-3、 元時刻 5-8 → cut2 3-6
    assert len(mappings) == 2
    assert mappings[0] == {"orig_start": 0.0, "orig_end": 3.0, "cut2_start": 0.0}
    assert mappings[1] == {"orig_start": 5.0, "orig_end": 8.0, "cut2_start": 3.0}


def test_remap_words_with_mapping_standard():
    """word.start が mapping 範囲内: cut2_start + (w.start - orig_start) に変換。"""
    mappings = [{"orig_start": 5.0, "orig_end": 8.0, "cut2_start": 0.0}]
    words = [
        {"start": 5.5, "end": 5.8, "text": "あ", "is_word_start": True},
        {"start": 6.0, "end": 6.3, "text": "い"},
    ]
    out = remap_words_with_mapping(words, mappings)
    assert len(out) == 2
    assert abs(out[0]["start"] - 0.5) < 1e-9
    assert abs(out[0]["end"] - 0.8) < 1e-9
    assert out[0]["is_word_start"] is True
    assert abs(out[1]["start"] - 1.0) < 1e-9


def test_remap_words_with_mapping_clamps_end():
    """word.end が orig_end を超える場合は clamp する (削除区間に半分かかる word)。"""
    mappings = [{"orig_start": 5.0, "orig_end": 8.0, "cut2_start": 0.0}]
    words = [{"start": 7.5, "end": 9.0, "text": "う"}]  # end が範囲外
    out = remap_words_with_mapping(words, mappings)
    assert len(out) == 1
    assert abs(out[0]["start"] - 2.5) < 1e-9
    # end は orig_end=8.0 で clamp → cut2 内では 3.0
    assert abs(out[0]["end"] - 3.0) < 1e-9


def test_remap_words_with_mapping_skips_words_outside():
    """word.start が全 mapping の範囲外なら結果に含まれない (削除区間内の word)。"""
    mappings = [{"orig_start": 5.0, "orig_end": 8.0, "cut2_start": 0.0}]
    words = [{"start": 10.0, "end": 10.5, "text": "削除"}]
    out = remap_words_with_mapping(words, mappings)
    assert out == []
