from app.services.qc import evaluate_qc


def _base(**over):
    m = {
        "original_duration": 60.0,
        "processed_duration": 45.0,
        "width": 1080,
        "height": 1920,
        "subtitles_enabled": False,
        "segment_count": 0,
        "suspicious_count": 0,
    }
    m.update(over)
    return m


def _codes(issues):
    return {i["code"] for i in issues}


def test_clean_output_no_issues():
    assert evaluate_qc(_base()) == []


def test_tiny_output_warns():
    issues = evaluate_qc(_base(original_duration=171.0, processed_duration=2.7))
    assert "tiny_output" in _codes(issues)
    assert issues[0]["severity"] == "warn"


def test_tiny_output_takes_priority_over_heavy_trim():
    # 2.7s は tiny_output のみ（heavy_trim と二重計上しない）
    issues = evaluate_qc(_base(original_duration=171.0, processed_duration=2.7))
    assert "heavy_trim" not in _codes(issues)


def test_heavy_trim_warns():
    issues = evaluate_qc(_base(original_duration=100.0, processed_duration=15.0))
    assert "heavy_trim" in _codes(issues)


def test_moderate_trim_ok():
    # 100s -> 40s は許容（0.2 以上）
    assert evaluate_qc(_base(original_duration=100.0, processed_duration=40.0)) == []


def test_short_original_not_flagged_as_heavy_trim():
    # 元が短い動画(<20s)は比率チェック対象外
    issues = evaluate_qc(_base(original_duration=10.0, processed_duration=4.0))
    assert "heavy_trim" not in _codes(issues)


def test_not_vertical_warns():
    issues = evaluate_qc(_base(width=1920, height=1080))
    assert "not_vertical" in _codes(issues)


def test_vertical_ok():
    assert _codes(evaluate_qc(_base(width=1080, height=1920))) == set()


def test_square_flagged_not_vertical():
    issues = evaluate_qc(_base(width=1080, height=1080))
    assert "not_vertical" in _codes(issues)


def test_missing_dimensions_skips_aspect_check():
    issues = evaluate_qc(_base(width=None, height=None))
    assert "not_vertical" not in _codes(issues)


def test_caption_hallucination_warns():
    issues = evaluate_qc(
        _base(subtitles_enabled=True, segment_count=10, suspicious_count=5)
    )
    assert "caption_hallucination" in _codes(issues)


def test_caption_low_suspicion_ok():
    issues = evaluate_qc(
        _base(subtitles_enabled=True, segment_count=10, suspicious_count=2)
    )
    assert "caption_hallucination" not in _codes(issues)


def test_no_captions_info():
    issues = evaluate_qc(
        _base(subtitles_enabled=True, segment_count=0, suspicious_count=0)
    )
    assert "no_captions" in _codes(issues)
    assert issues[0]["severity"] == "info"


def test_warns_sorted_before_info():
    issues = evaluate_qc(
        _base(
            width=1920, height=1080,  # warn: not_vertical
            subtitles_enabled=True, segment_count=0,  # info: no_captions
        )
    )
    severities = [i["severity"] for i in issues]
    assert severities == sorted(severities, key=lambda s: 0 if s == "warn" else 1)
    assert severities[0] == "warn"
