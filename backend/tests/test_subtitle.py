# backend/tests/test_subtitle.py
from app.services.subtitle import segments_to_srt


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
