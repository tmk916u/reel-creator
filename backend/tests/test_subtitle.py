# backend/tests/test_subtitle.py
from app.services.subtitle import segments_to_srt, words_to_segments


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
