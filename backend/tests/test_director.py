"""LLM Director tests.

OpenSpec: llm-director-editor
"""
from unittest.mock import patch

from app.services import director


# === _validate_clips ===

def test_validate_clips_filters_invalid_range():
    raw = [
        {"start": 5.0, "end": 10.0, "role": "intro", "text": "ok"},
        {"start": 10.0, "end": 5.0, "role": "main", "text": "end < start"},
        {"start": -1.0, "end": 5.0, "role": "main", "text": "negative start"},
        {"start": 5.0, "end": 999.0, "role": "main", "text": "out of duration"},
    ]
    out = director._validate_clips(raw, duration=100.0)
    assert len(out) == 1
    assert out[0]["start"] == 5.0


def test_validate_clips_filters_invalid_role():
    raw = [
        {"start": 0.0, "end": 5.0, "role": "intro"},
        {"start": 5.0, "end": 10.0, "role": "bogus"},
    ]
    out = director._validate_clips(raw, duration=100.0)
    assert len(out) == 1
    assert out[0]["role"] == "intro"


def test_validate_clips_sorts_and_renumbers():
    raw = [
        {"start": 20.0, "end": 25.0, "role": "cta", "order": 3},
        {"start": 5.0, "end": 10.0, "role": "intro", "order": 1},
        {"start": 12.0, "end": 18.0, "role": "main", "order": 2},
    ]
    out = director._validate_clips(raw, duration=100.0)
    assert [c["order"] for c in out] == [1, 2, 3]
    assert [c["start"] for c in out] == [5.0, 12.0, 20.0]


def test_validate_clips_clamps_end_to_duration():
    raw = [{"start": 95.0, "end": 100.4, "role": "cta"}]  # end は duration+0.5 内、 clamp 動作
    out = director._validate_clips(raw, duration=100.0)
    assert len(out) == 1
    assert out[0]["end"] == 100.0


# === snap_clips_to_words ===

def test_snap_clips_to_words_snaps_to_word_boundaries():
    clips = [{"start": 5.3, "end": 12.7, "role": "intro", "order": 1, "text": ""}]
    words = [
        {"start": 5.0, "end": 5.4, "text": "a"},
        {"start": 6.0, "end": 6.5, "text": "b"},
        {"start": 12.5, "end": 13.0, "text": "c"},
    ]
    out = director.snap_clips_to_words(clips, words)
    assert len(out) == 1
    # snapped_start = max(word.start <= 5.3) = 5.0
    # snapped_end = min(word.end >= 12.7) = 13.0
    assert out[0]["start"] == 5.0
    assert out[0]["end"] == 13.0


def test_snap_clips_to_words_no_words_returns_as_is():
    clips = [{"start": 5.0, "end": 10.0, "role": "intro", "order": 1, "text": ""}]
    out = director.snap_clips_to_words(clips, [])
    assert out == clips


def test_snap_clips_to_words_drops_collapsed():
    """word boundary snap で start >= end になったら破棄"""
    clips = [{"start": 5.0, "end": 5.05, "role": "intro", "order": 1, "text": ""}]
    words = [{"start": 5.0, "end": 5.04, "text": "a"}]
    out = director.snap_clips_to_words(clips, words)
    assert out == []


# === clips_to_voice_segments ===

def test_clips_to_voice_segments_simple_no_silence():
    clips = [
        {"start": 5.0, "end": 10.0, "role": "intro", "order": 1, "text": ""},
        {"start": 20.0, "end": 25.0, "role": "cta", "order": 2, "text": ""},
    ]
    voices = director.clips_to_voice_segments(clips, silences=[])
    assert voices == [
        {"start": 5.0, "end": 10.0},
        {"start": 20.0, "end": 25.0},
    ]


def test_clips_to_voice_segments_subtracts_silences():
    """clip 内に silence があれば、 silence 前後を別 voice として分割"""
    clips = [{"start": 0.0, "end": 10.0, "role": "intro", "order": 1, "text": ""}]
    silences = [{"start": 3.0, "end": 5.0}]
    voices = director.clips_to_voice_segments(clips, silences)
    assert voices == [
        {"start": 0.0, "end": 3.0},
        {"start": 5.0, "end": 10.0},
    ]


def test_clips_to_voice_segments_ignores_out_of_range_silences():
    clips = [{"start": 5.0, "end": 10.0, "role": "intro", "order": 1, "text": ""}]
    silences = [{"start": 0.0, "end": 3.0}, {"start": 20.0, "end": 25.0}]
    voices = director.clips_to_voice_segments(clips, silences)
    assert voices == [{"start": 5.0, "end": 10.0}]


def test_clips_to_voice_segments_empty_clips():
    assert director.clips_to_voice_segments([], silences=[{"start": 0.0, "end": 1.0}]) == []


# === design_story (LLM mocked) ===

def test_design_story_returns_clips_on_success():
    fake_response = '{"clips": [{"start": 0.0, "end": 30.0, "role": "intro"}, {"start": 30.0, "end": 60.0, "role": "main"}], "summary": "test"}'
    segments = [{"start": 0.0, "end": 60.0, "text": "hello world"}]
    with patch.object(director, "_call_llm", return_value=fake_response):
        clips = director.design_story(segments, duration=60.0)
    assert len(clips) == 2
    assert clips[0]["role"] == "intro"


def test_design_story_empty_segments_returns_empty():
    assert director.design_story([], duration=60.0) == []


def test_design_story_llm_error_returns_empty():
    segments = [{"start": 0.0, "end": 60.0, "text": "x"}]
    with patch.object(director, "_call_llm", side_effect=RuntimeError("LLM failed")):
        assert director.design_story(segments, duration=60.0) == []


def test_design_story_json_error_returns_empty():
    segments = [{"start": 0.0, "end": 60.0, "text": "x"}]
    with patch.object(director, "_call_llm", return_value="not json"):
        assert director.design_story(segments, duration=60.0) == []


def test_design_story_total_duration_too_small_returns_empty():
    """合計尺が下限 - 5 秒より小さければフォールバック"""
    fake_response = '{"clips": [{"start": 0, "end": 10, "role": "intro"}]}'  # 10s, min=50
    segments = [{"start": 0, "end": 60, "text": "x"}]
    with patch.object(director, "_call_llm", return_value=fake_response):
        clips = director.design_story(segments, duration=60.0, target_duration_min=50.0)
    assert clips == []


def test_design_story_total_duration_in_range():
    fake_response = '{"clips": [{"start": 0, "end": 55, "role": "main"}]}'
    segments = [{"start": 0, "end": 60, "text": "x"}]
    with patch.object(director, "_call_llm", return_value=fake_response):
        clips = director.design_story(segments, duration=60.0, target_duration_min=50.0, target_duration_max=80.0)
    assert len(clips) == 1
    assert clips[0]["end"] == 55.0


def test_design_story_extracts_code_fenced_json():
    """LLM が code fence で JSON を返してもパースできる"""
    fake_response = '```json\n{"clips": [{"start": 0, "end": 55, "role": "main"}]}\n```'
    segments = [{"start": 0, "end": 60, "text": "x"}]
    with patch.object(director, "_call_llm", return_value=fake_response):
        clips = director.design_story(segments, duration=60.0, target_duration_min=50.0)
    assert len(clips) == 1


# === _text_similarity ===

def test_text_similarity_identical():
    assert director._text_similarity("お客様が悩まれている", "お客様が悩まれている") == 1.0


def test_text_similarity_substring_short():
    # 1-2 文字は substring 一致
    assert director._text_similarity("お", "お客様") == 1.0
    assert director._text_similarity("ねこ", "わんこ") == 0.0


def test_text_similarity_partial_match():
    # ほぼ同じ
    sim = director._text_similarity(
        "お客様が悩まれているダイエットの食事への",
        "お客様が悩まれているダイエットの食事の話",
    )
    assert sim >= 0.6


def test_text_similarity_different():
    sim = director._text_similarity("結論から言うと一番大事なのはメンタル", "ぜひそこを突き詰めてみてください")
    assert sim < 0.3


def test_text_similarity_ignores_punctuation():
    # 句読点・空白の差は無視
    a = "お客様が、悩まれている。"
    b = "お客様が悩まれている"
    assert director._text_similarity(a, b) == 1.0


# === _dedupe_clips ===

def test_dedupe_clips_removes_adjacent_duplicates():
    """連続する重複 clip は後発を破棄"""
    clips: list[director.Clip] = [
        {"start": 0.0, "end": 7.0, "role": "intro", "order": 1,
         "text": "お客様が悩まれているダイエットの食事への"},
        {"start": 7.0, "end": 15.0, "role": "intro", "order": 2,
         "text": "お客様が悩まれているダイエットの食事の話"},  # 重複
        {"start": 16.0, "end": 30.0, "role": "main", "order": 3,
         "text": "結論から言うと一番大事なのはメンタル"},  # 別話題
    ]
    out = director._dedupe_clips(clips, similarity_threshold=0.6, max_time_gap=30.0)
    assert len(out) == 2
    assert out[0]["text"].startswith("お客様")
    assert out[1]["text"].startswith("結論")


def test_dedupe_clips_keeps_distant_duplicates():
    """time gap が max_time_gap を超える重複は別話題として残す"""
    clips: list[director.Clip] = [
        {"start": 0.0, "end": 5.0, "role": "intro", "order": 1, "text": "メンタルが大事"},
        {"start": 50.0, "end": 55.0, "role": "cta", "order": 2, "text": "メンタルが大事"},
    ]
    out = director._dedupe_clips(clips, similarity_threshold=0.6, max_time_gap=30.0)
    # time gap 45s > 30s なので両方残る
    assert len(out) == 2


def test_dedupe_clips_renumbers_order():
    """重複除去後 order を 1 から振り直す"""
    clips: list[director.Clip] = [
        {"start": 0.0, "end": 5.0, "role": "intro", "order": 1, "text": "abc"},
        {"start": 5.0, "end": 10.0, "role": "intro", "order": 2, "text": "abcd"},  # 重複
        {"start": 10.0, "end": 20.0, "role": "main", "order": 3, "text": "different"},
    ]
    out = director._dedupe_clips(clips)
    assert [c["order"] for c in out] == [1, 2]


def test_dedupe_clips_empty_or_single():
    assert director._dedupe_clips([]) == []
    single: list[director.Clip] = [
        {"start": 0.0, "end": 5.0, "role": "intro", "order": 1, "text": "x"},
    ]
    assert len(director._dedupe_clips(single)) == 1
