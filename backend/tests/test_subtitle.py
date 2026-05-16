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
    segments = words_to_segments(words, lead_time=0, tail_time=0)
    assert len(segments) == 2
    assert segments[0]["text"] == "今日は雨。"
    assert segments[0]["start"] == 0.0
    assert segments[0]["end"] == 1.2
    assert segments[1]["text"] == "明日は晴れ。"


def test_words_to_segments_gap_split():
    """長い無音で分割する（短いフラグメント統合が走らない長さで検証）"""
    words = [
        {"start": 0.0, "end": 0.3, "text": "あいうえお"},
        {"start": 0.3, "end": 0.6, "text": "かきくけこ"},
        {"start": 3.0, "end": 3.3, "text": "さしすせそ"},
        {"start": 3.3, "end": 3.6, "text": "たちつてと"},
    ]
    segments = words_to_segments(words, max_gap=0.6, lead_time=0, tail_time=0)
    assert len(segments) == 2
    assert segments[0]["text"] == "あいうえおかきくけこ"
    assert segments[1]["text"] == "さしすせそたちつてと"


def test_words_to_segments_lead_tail_padding():
    """lead_time / tail_time が字幕表示時間を拡張する"""
    words = [
        {"start": 1.0, "end": 1.5, "text": "あ。"},
        {"start": 3.0, "end": 3.5, "text": "い。"},
    ]
    segments = words_to_segments(words, lead_time=0.1, tail_time=0.2)
    # 1つ目: start 早めに、end 後ろに伸ばす（次の start-0.01 を超えない）
    assert segments[0]["start"] == 0.9
    assert segments[0]["end"] == 1.7
    # 2つ目: start 前倒し、最後なので end は単純に+0.2
    assert segments[1]["start"] == 2.9
    assert abs(segments[1]["end"] - 3.7) < 1e-9


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


def test_words_to_segments_respects_word_start_boundary():
    """is_word_start=False の subword 連続は、次の word_start で flush される"""
    words = [
        # 「今日はとても」(6文字、1単語扱い)
        {"start": 0.0, "end": 0.2, "text": "今日", "is_word_start": True},
        {"start": 0.2, "end": 0.4, "text": "は", "is_word_start": False},
        {"start": 0.4, "end": 0.6, "text": "と", "is_word_start": False},
        {"start": 0.6, "end": 0.8, "text": "ても", "is_word_start": False},
        # 「暑い」(2文字)
        {"start": 0.8, "end": 1.0, "text": "暑", "is_word_start": True},
        {"start": 1.0, "end": 1.2, "text": "い", "is_word_start": False},
        # 「夏が」(2文字)— ここで max_chars 超過 + is_word_start=True → flush
        {"start": 1.2, "end": 2.0, "text": "夏が", "is_word_start": True},
        # 「好きです」(4文字)
        {"start": 2.0, "end": 5.0, "text": "好きです", "is_word_start": True},
    ]
    segments = words_to_segments(words, max_chars=8, lead_time=0, tail_time=0)
    # 単語の真ん中で切れず、「暑い」までで 8 文字に到達 → 次の word_start "夏が" で flush
    assert segments[0]["text"] == "今日はとても暑い"
    assert segments[1]["text"] == "夏が好きです"


def test_words_to_segments_no_is_word_start_uses_default_true():
    """is_word_start 未指定は True 扱い（WhisperX/faster-whisper の word は単語単位）"""
    words = [
        {"start": 0.0, "end": 1.0, "text": "今日はとても"},
        {"start": 1.0, "end": 2.0, "text": "暑い"},
        {"start": 2.0, "end": 5.0, "text": "夏ですよね"},
    ]
    segments = words_to_segments(words, max_chars=8, lead_time=0, tail_time=0)
    # "暑い"までで 8 文字ちょうど。"夏ですよね" 追加で 13 文字超過 → flush
    assert segments[0]["text"] == "今日はとても暑い"
    assert segments[1]["text"] == "夏ですよね"
