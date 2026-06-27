from app.services.subtitle import segments_to_ass


def _seg(words, text="テスト"):
    return [{"start": words[0]["start"], "end": words[-1]["end"], "text": text, "words": words}]


WORDS = [
    {"start": 1.0, "end": 1.3, "text": "今日"},
    {"start": 1.3, "end": 1.6, "text": "は"},
    {"start": 2.0, "end": 2.4, "text": "大事"},
]


def test_karaoke_has_kf_no_motion():
    ass = segments_to_ass(_seg(WORDS), motion_style="karaoke")
    assert "\\kf" in ass
    assert "\\t(" not in ass
    assert "\\fad(" not in ass


def test_none_has_no_kf_no_motion():
    ass = segments_to_ass(_seg(WORDS), motion_style="none")
    assert "\\kf" not in ass
    assert "\\t(" not in ass
    # テキストは描画される
    assert "今日" in ass and "大事" in ass


def test_fade_has_line_fade_and_kf():
    ass = segments_to_ass(_seg(WORDS), motion_style="fade")
    assert "\\fad(" in ass
    assert "\\kf" in ass
    assert "\\t(" not in ass  # fade は語スケール演出を持たない


def test_pop_has_scale_transform_with_ms_offsets():
    ass = segments_to_ass(_seg(WORDS), motion_style="pop")
    assert "\\kf" in ass
    assert "\\t(" in ass
    assert "\\fscx113" in ass  # POP_SCALE
    # 行頭の語は off_ms=0、3語目は start 2.0 - 1.0 = 1.0s = 1000ms 始まり
    assert "\\t(0," in ass
    assert "\\t(1000," in ass


def test_pop_resets_scale_per_word():
    # 各語は \fscx100\fscy100 で baseline をリセットしてから pop する（bleed 防止）
    ass = segments_to_ass(_seg(WORDS), motion_style="pop")
    assert "\\fscx100\\fscy100" in ass


def test_unknown_motion_falls_back_to_karaoke():
    ass = segments_to_ass(_seg(WORDS), motion_style="sparkle")
    assert "\\kf" in ass
    assert "\\t(" not in ass


def test_keyword_color_combined_with_motion():
    ass = segments_to_ass(_seg(WORDS), keywords=["大事"], motion_style="pop")
    # キーワードは色タグ + pop スケールの両方を持つ
    assert "\\c" in ass
    assert "\\t(" in ass
    assert "大事" in ass


def test_empty_words_seg_skipped():
    # words が無い seg はスキップ（phantom 字幕防止、既存挙動を motion でも維持）
    segs = [{"start": 0.0, "end": 2.0, "text": "言い直しで全部消えた", "words": []}]
    ass = segments_to_ass(segs, motion_style="pop")
    assert "Dialogue:" not in ass
