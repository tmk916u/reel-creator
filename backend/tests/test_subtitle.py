# backend/tests/test_subtitle.py
from app.services.subtitle import (
    segments_to_srt, words_to_segments, segments_to_ass,
    _ass_time, _ass_color, apply_keyword_highlight,
)


def test_segments_to_srt():
    """Whisperセグメントを正しいSRT形式に変換する"""
    segments = [
        {"start": 0.0, "end": 2.5, "text": "こんにちは"},
        {"start": 3.0, "end": 5.0, "text": "ありがとう"},
    ]
    result = segments_to_srt(segments)
    assert "1\n00:00:00,000 --> 00:00:02,500\nこんにちは" in result
    assert "2\n00:00:03,000 --> 00:00:05,000\nありがとう" in result


def test_segments_to_srt_empty():
    """空のセグメントリストでは空文字列を返す"""
    result = segments_to_srt([])
    assert result == ""


def test_words_to_segments_punctuation_split():
    """句読点で分割する"""
    words = [
        {"start": 0.0, "end": 0.4, "text": "今日"},
        {"start": 0.4, "end": 0.8, "text": "は"},
        {"start": 0.8, "end": 1.2, "text": "雨。"},
        {"start": 1.3, "end": 1.7, "text": "明日"},
        {"start": 1.7, "end": 2.1, "text": "は"},
        {"start": 2.1, "end": 2.5, "text": "晴れ。"},
    ]
    segments = words_to_segments(words)
    assert len(segments) == 2
    assert segments[0]["text"] == "今日は雨。"
    assert segments[0]["start"] == 0.0
    assert segments[0]["end"] == 1.2
    assert segments[1]["text"] == "明日は晴れ。"


def test_words_to_segments_gap_split():
    """長い無音で分割する"""
    words = [
        {"start": 0.0, "end": 0.5, "text": "あ"},
        {"start": 0.5, "end": 1.0, "text": "い"},
        {"start": 2.0, "end": 2.5, "text": "う"},  # 1秒のギャップ
    ]
    segments = words_to_segments(words, max_gap=0.6)
    assert len(segments) == 2
    assert segments[0]["text"] == "あい"
    assert segments[1]["text"] == "う"


def test_words_to_segments_empty():
    """空の単語リストは空セグメントを返す"""
    assert words_to_segments([]) == []


def test_words_to_segments_keeps_word_data():
    """セグメントに word データが含まれる"""
    words = [
        {"start": 0.0, "end": 0.4, "text": "今日"},
        {"start": 0.4, "end": 0.8, "text": "は雨。"},
    ]
    segments = words_to_segments(words)
    assert "words" in segments[0]
    assert len(segments[0]["words"]) == 2
    assert segments[0]["words"][0]["text"] == "今日"


def test_ass_time_formatting():
    assert _ass_time(0) == "0:00:00.00"
    assert _ass_time(1.5) == "0:00:01.50"
    assert _ass_time(65.25) == "0:01:05.25"
    assert _ass_time(3725.0) == "1:02:05.00"


def test_ass_color_conversion():
    assert _ass_color("#FFFFFF") == "&H00FFFFFF&"
    assert _ass_color("#FFD700") == "&H0000D7FF&"
    assert _ass_color("#000000") == "&H00000000&"


def test_segments_to_ass_generates_karaoke():
    """ASS出力にカラオケタグが含まれる"""
    segments = [
        {
            "start": 0.0, "end": 1.5, "text": "今日は雨",
            "words": [
                {"start": 0.0, "end": 0.5, "text": "今日"},
                {"start": 0.5, "end": 1.0, "text": "は"},
                {"start": 1.0, "end": 1.5, "text": "雨"},
            ],
        },
    ]
    ass = segments_to_ass(segments)
    assert "[Script Info]" in ass
    assert "[V4+ Styles]" in ass
    assert "[Events]" in ass
    assert "\\kf" in ass  # karaoke fill tag
    assert "Dialogue: 0,0:00:00.00,0:00:01.50" in ass


def test_segments_to_ass_keyword_color():
    """キーワード単語に色オーバーライドが入る"""
    segments = [
        {
            "start": 0.0, "end": 0.5, "text": "血流",
            "words": [{"start": 0.0, "end": 0.5, "text": "血流"}],
        },
    ]
    ass = segments_to_ass(segments, keywords=["血流"])
    assert "&H0000D7FF&" in ass  # gold color in ASS format
    assert "血流" in ass


def test_segments_to_ass_no_words_skipped():
    """words が無いセグメントはスキップされる"""
    segments = [{"start": 0.0, "end": 1.0, "text": "テスト"}]
    ass = segments_to_ass(segments)
    assert "Dialogue:" not in ass


def test_apply_keyword_highlight_wraps_words():
    text = "血流と筋肉は大事"
    result = apply_keyword_highlight(text, ["血流", "筋肉"])
    assert '<font color="#FFD700">血流</font>' in result
    assert '<font color="#FFD700">筋肉</font>' in result


def test_apply_keyword_highlight_no_keywords():
    assert apply_keyword_highlight("テスト", []) == "テスト"
