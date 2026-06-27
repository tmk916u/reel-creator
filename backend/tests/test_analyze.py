from app.services.analyze import recommend_settings


def test_talk_profile_high_speech():
    r = recommend_settings(0.7, 1080, 1920, 60.0)
    assert r["profile"] == "talk"
    assert r["settings"]["enable_jump_cut"] is True
    assert r["settings"]["enable_subtitles"] is True
    assert r["settings"]["color_grade"] == "cinematic"


def test_visual_profile_low_speech_keeps_full_length():
    r = recommend_settings(0.1, 1080, 1920, 171.0)
    assert r["profile"] == "visual"
    # 全長キープ: 無音削除を実質オフ、字幕オフ(誤字幕回避)
    assert r["settings"]["enable_subtitles"] is False
    assert r["settings"]["enable_jump_cut"] is False
    assert r["settings"]["min_silence_duration"] >= 100
    assert r["settings"]["color_grade"] == "cinematic"


def test_mixed_profile_middle_speech():
    r = recommend_settings(0.3, 1080, 1920, 90.0)
    assert r["profile"] == "mixed"
    assert r["settings"]["enable_subtitles"] is True
    assert r["settings"]["subtitle_motion"] == "fade"


def test_landscape_enables_reframe():
    r = recommend_settings(0.7, 1920, 1080, 60.0)  # 横
    assert r["orientation"] == "landscape"
    assert r["settings"]["enable_auto_reframe"] is True


def test_vertical_disables_reframe():
    r = recommend_settings(0.7, 720, 1280, 60.0)  # 縦(9:16)
    assert r["orientation"] == "vertical"
    assert r["settings"]["enable_auto_reframe"] is False


def test_square_treated_as_landscape_for_reframe():
    r = recommend_settings(0.7, 1080, 1080, 60.0)  # 正方形は横扱い(crop余地あり)
    assert r["settings"]["enable_auto_reframe"] is True


def test_reason_includes_percentage():
    r = recommend_settings(0.62, 1080, 1920, 60.0)
    assert "62%" in r["reason"]
    assert r["speech_ratio"] == 0.62


def test_boundary_45_percent_is_talk():
    assert recommend_settings(0.45, 1080, 1920, 60.0)["profile"] == "talk"


def test_boundary_18_percent_is_visual():
    assert recommend_settings(0.18, 1080, 1920, 60.0)["profile"] == "visual"
