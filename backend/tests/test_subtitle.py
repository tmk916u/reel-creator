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
    """is_word_start=False の subword 連続は、次の word_start で flush される。

    短いセグメントの統合を抑制するため、 2 セグメントの間に 3 秒以上のギャップを置く。
    """
    words = [
        # 「今日はとても」(6文字、1単語扱い)
        {"start": 0.0, "end": 0.2, "text": "今日", "is_word_start": True},
        {"start": 0.2, "end": 0.4, "text": "は", "is_word_start": False},
        {"start": 0.4, "end": 0.6, "text": "と", "is_word_start": False},
        {"start": 0.6, "end": 0.8, "text": "ても", "is_word_start": False},
        # 「暑い」(2文字)
        {"start": 0.8, "end": 1.0, "text": "暑", "is_word_start": True},
        {"start": 1.0, "end": 1.2, "text": "い", "is_word_start": False},
        # 「夏が」(2文字)— 3 秒以上のギャップで統合を抑制
        {"start": 4.5, "end": 5.0, "text": "夏が", "is_word_start": True},
        # 「好きです」(4文字)
        {"start": 5.0, "end": 7.0, "text": "好きです", "is_word_start": True},
    ]
    segments = words_to_segments(words, max_chars=8, lead_time=0, tail_time=0)
    # 単語の真ん中で切れず、「暑い」までで 8 文字に到達 → 次の word_start "夏が" で flush
    assert segments[0]["text"] == "今日はとても暑い"
    assert segments[1]["text"] == "夏が好きです"


def test_words_to_segments_keeps_particle_with_next_word():
    """末尾が格助詞 (は/が/を/に/で/と/の/も) なら不自然な切れを避けて持ち越す"""
    # max_chars=8 でも「ボディが」(4文字、末尾「が」)の直後では flush しない
    words = [
        {"start": 0.0, "end": 0.5, "text": "ボディ", "is_word_start": True},
        {"start": 0.5, "end": 0.7, "text": "が", "is_word_start": False},
        {"start": 0.7, "end": 1.2, "text": "メイク", "is_word_start": True},  # 通常なら 7→10で超過 flush
        {"start": 1.2, "end": 3.0, "text": "重要なんですよ", "is_word_start": True},
    ]
    segments = words_to_segments(words, max_chars=8, lead_time=0, tail_time=0)
    # 「ボディが」直後で切れず、「ボディがメイク」まで持ち越し、その後で flush
    # 末尾「ク」(非助詞)+「重要」(is_word_start, 超過)で初めて切れる
    assert any("ボディがメイク" in seg["text"] for seg in segments), \
        f"助詞直後で flush された: {[s['text'] for s in segments]}"


def test_words_to_segments_hard_limit_when_no_word_start():
    """is_word_start=False の subword が連続して word_start が来ない場合、
    絶対上限 max_chars*1.5 で強制 flush される（暴走防止）"""
    # is_word_start=False ばかりだが、テキストは変化させる（dedup の影響を避ける）
    chars = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよ"
    words = [
        {"start": 0.5 * i, "end": 0.5 * (i + 1), "text": chars[i], "is_word_start": False}
        for i in range(len(chars))
    ]
    segments = words_to_segments(words, max_chars=8, lead_time=0, tail_time=0)
    # 単語境界が一向に来なくても、絶対上限で複数セグメントに分かれる
    assert len(segments) >= 2, "暴走: 1セグメントに全文が結合されている"
    # 各セグメントの文字数は hard_limit(=12) を大きく超えない
    for seg in segments:
        assert len(seg["text"]) <= 14, f"暴走: {len(seg['text'])}文字"


def test_words_to_segments_no_is_word_start_uses_default_true():
    """is_word_start 未指定は True 扱い（WhisperX/faster-whisper の word は単語単位）"""
    words = [
        {"start": 0.0, "end": 1.0, "text": "今日はとても"},
        {"start": 1.0, "end": 2.0, "text": "暑い"},
        # 3 秒以上のギャップで _merge_short_segments による統合を抑制
        {"start": 5.5, "end": 8.0, "text": "夏ですよね"},
    ]
    segments = words_to_segments(words, max_chars=8, lead_time=0, tail_time=0)
    # "暑い"までで 8 文字ちょうど。"夏ですよね" 追加で 13 文字超過 → flush
    assert segments[0]["text"] == "今日はとても暑い"
    assert segments[1]["text"] == "夏ですよね"


def test_words_to_segments_does_not_flush_on_touten():
    """「、」 では flush しない (短い断片を量産する原因のため)。"""
    words = [
        {"start": 0.0, "end": 0.3, "text": "ただ、", "is_word_start": True},
        {"start": 0.3, "end": 0.6, "text": "それは", "is_word_start": True},
        {"start": 0.6, "end": 1.0, "text": "悪い", "is_word_start": True},
        {"start": 1.0, "end": 1.4, "text": "ことでは", "is_word_start": True},
        {"start": 1.4, "end": 1.8, "text": "ありません。", "is_word_start": True},
    ]
    segments = words_to_segments(words, max_chars=20, lead_time=0, tail_time=0)
    # 「、」 で flush せず、 句点「。」 で 1 つの Dialogue になる
    assert len(segments) == 1
    assert segments[0]["text"] == "ただ、それは悪いことではありません。"


def test_words_to_segments_holds_connective_particle_te():
    """接続助詞「て」 末尾でも flush 抑制 (max_chars 超過時は次の word まで持ち越し)。"""
    words = [
        # 「あって」(3文字、末尾「て」)。 max_chars=4 を超えるが「て」 抑制で flush しない
        {"start": 0.0, "end": 0.3, "text": "あ", "is_word_start": True},
        {"start": 0.3, "end": 0.6, "text": "って", "is_word_start": False},
        # 次の word 「次へ」 (2 文字)、 is_word_start=True、 over_chars だが「て」抑制で flush しない
        {"start": 0.6, "end": 1.0, "text": "次", "is_word_start": True},
        {"start": 1.0, "end": 1.4, "text": "へ", "is_word_start": False},
    ]
    segments = words_to_segments(words, max_chars=4, lead_time=0, tail_time=0)
    # 「て」抑制で「あって次へ」 が 1 セグメントになる(hard_limit 6 までは持ち越し可)
    assert len(segments) == 1
    assert segments[0]["text"] == "あって次へ"


# === subtitle-meaning-chunking (Phase 1, 2, 3) ===

def test_normalize_repeated_chars_compresses_pair():
    """同一文字 2 連続 → 1 文字に圧縮 (ASR ノイズ正規化)"""
    from app.services.subtitle import _normalize_repeated_chars
    assert _normalize_repeated_chars("ほほとんど") == "ほとんど"
    assert _normalize_repeated_chars("めめんたる") == "めんたる"


def test_normalize_repeated_chars_keeps_triple():
    """同一文字 3 連続以上は意図的な強調として保持"""
    from app.services.subtitle import _normalize_repeated_chars
    assert _normalize_repeated_chars("あああ") == "あああ"
    assert _normalize_repeated_chars("うううん") == "うううん"


def test_normalize_repeated_chars_handles_empty_and_single():
    from app.services.subtitle import _normalize_repeated_chars
    assert _normalize_repeated_chars("") == ""
    assert _normalize_repeated_chars("あ") == "あ"


def test_words_to_segments_clamped_word_is_isolated():
    """clamp 済み word (_orig_end あり) は前後と結合せず単独 dialogue になる"""
    words = [
        {"start": 0.0, "end": 0.5, "text": "結論"},
        # clamp 済み word: text 「お」 だけだが実発話は長い
        {"start": 1.0, "end": 1.12, "text": "お", "_orig_end": 13.0},
        {"start": 14.0, "end": 14.5, "text": "次の話"},
    ]
    segments = words_to_segments(words, lead_time=0, tail_time=0)
    # 3 個の独立 dialogue: 結論 / お / 次の話
    texts = [s["text"] for s in segments]
    assert "お" in texts, f"clamp word が独立 dialogue になっていない: {texts}"


def test_words_to_segments_word_gap_boundary():
    """word 間 gap ≥ max_gap (デフォルト 0.4) で flush"""
    words = [
        {"start": 0.0, "end": 0.5, "text": "今日は"},
        {"start": 0.5, "end": 1.0, "text": "雨です"},  # gap 0
        {"start": 1.5, "end": 2.0, "text": "明日は"},  # gap 0.5 ≥ 0.4 → flush
        {"start": 2.0, "end": 2.5, "text": "晴れです"},
    ]
    segments = words_to_segments(words, max_gap=0.4, max_chars=100, lead_time=0, tail_time=0)
    assert len(segments) == 2
    assert segments[0]["text"] == "今日は雨です"
    assert segments[1]["text"] == "明日は晴れです"


def test_words_to_segments_word_gap_uses_orig_end():
    """gap 計算は前 word の _orig_end を優先 (clamp で生まれた人工的な隙間を無視)"""
    words = [
        {"start": 0.0, "end": 0.5, "text": "結論"},
        # clamp 済み word
        {"start": 1.0, "end": 1.12, "text": "お", "_orig_end": 13.0},
        # 次 word: clamp word の _orig_end (13.0) からの gap は 0.5s
        {"start": 13.5, "end": 14.0, "text": "次"},
    ]
    segments = words_to_segments(words, max_gap=0.4, lead_time=0, tail_time=0)
    # 「お」 は clamp 済みで独立 dialogue → 次の「次」 とは別 dialogue になる
    texts = [s["text"] for s in segments]
    assert "お" in texts


def test_words_to_segments_normalizes_repeated_chars_at_entry():
    """words_to_segments 入口で重複文字が去重される"""
    words = [
        {"start": 0.0, "end": 1.0, "text": "ほほとんど。"},
    ]
    segments = words_to_segments(words, lead_time=0, tail_time=0)
    assert segments[0]["text"] == "ほとんど。"


def test_merge_orphan_chars_merges_single_char():
    """1 文字 dialogue は前段と統合される (前段が句点で終わらない場合)"""
    from app.services.subtitle import _merge_orphan_chars
    segments = [
        {"start": 0.0, "end": 1.0, "text": "結論から", "words": [
            {"start": 0.0, "end": 1.0, "text": "結論から"},
        ]},
        {"start": 1.0, "end": 1.2, "text": "の", "words": [
            {"start": 1.0, "end": 1.2, "text": "の"},
        ]},
    ]
    out = _merge_orphan_chars(segments, max_chars=24)
    assert len(out) == 1
    assert out[0]["text"] == "結論からの"


def test_merge_orphan_chars_preserves_clamped():
    """clamp 済み word を含む 1 文字 dialogue は隔離維持 (統合しない)"""
    from app.services.subtitle import _merge_orphan_chars
    segments = [
        {"start": 0.0, "end": 1.0, "text": "結論", "words": [
            {"start": 0.0, "end": 1.0, "text": "結論"},
        ]},
        {"start": 1.0, "end": 1.12, "text": "お", "words": [
            {"start": 1.0, "end": 1.12, "text": "お", "_orig_end": 13.0},
        ]},
    ]
    out = _merge_orphan_chars(segments, max_chars=24)
    assert len(out) == 2, f"clamp 済み word が統合された: {[s['text'] for s in out]}"


def test_merge_orphan_chars_respects_sentence_end():
    """前段が「。」 で終わっていれば 1 文字 dialogue でも統合しない"""
    from app.services.subtitle import _merge_orphan_chars
    segments = [
        {"start": 0.0, "end": 1.0, "text": "結論です。", "words": [
            {"start": 0.0, "end": 1.0, "text": "結論です。"},
        ]},
        {"start": 1.0, "end": 1.2, "text": "あ", "words": [
            {"start": 1.0, "end": 1.2, "text": "あ"},
        ]},
    ]
    out = _merge_orphan_chars(segments, max_chars=24)
    assert len(out) == 2


# === detect_suspicious_segments (add-mishearing-highlight-preview) ===

def test_detect_suspicious_subword_fragment():
    """5 文字以下で 助詞・記号比率が高い segment は suspicious=true。"""
    from app.services.subtitle import detect_suspicious_segments

    segs = [
        {"text": "客 事への 食"},  # 5 文字、 「 」+「、」 多めなので suspicious
        {"text": "結論から言うと一番大事なのは"},  # 長い、 不審じゃない
    ]
    flags = detect_suspicious_segments(segs)
    assert flags[0] is True
    assert flags[1] is False


def test_detect_suspicious_repeating_char():
    """同一文字 3 連続は suspicious=true。"""
    from app.services.subtitle import detect_suspicious_segments

    segs = [{"text": "あああです"}]
    flags = detect_suspicious_segments(segs)
    assert flags[0] is True


def test_detect_suspicious_starts_with_punctuation():
    """句点・記号で始まる segment は suspicious=true。"""
    from app.services.subtitle import detect_suspicious_segments

    segs = [{"text": "、それは違う"}]
    flags = detect_suspicious_segments(segs)
    assert flags[0] is True


def test_detect_suspicious_short_fragment():
    """1-2 文字で文末記号でない segment は suspicious=true。"""
    from app.services.subtitle import detect_suspicious_segments

    segs = [
        {"text": "客"},        # 1 文字、 文末記号でない → suspicious
        {"text": "あ。"},      # 文末記号で終わる → 不審ではない
    ]
    flags = detect_suspicious_segments(segs)
    assert flags[0] is True
    assert flags[1] is False
