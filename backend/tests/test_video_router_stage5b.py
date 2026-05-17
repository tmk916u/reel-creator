from contextlib import ExitStack
from unittest.mock import patch

from app.models.schemas import ProcessRequest
from app.routers import video as video_module


def _setup_job(tmp_path, monkeypatch):
    job_id = "test-stage5b"
    job_dir = tmp_path / job_id
    job_dir.mkdir()
    (job_dir / "input.mp4").write_bytes(b"fake")
    monkeypatch.setattr(video_module, "TMP_DIR", tmp_path)
    video_module.job_store[job_id] = {
        "status": "processing",
        "stage": "init",
        "progress": 0,
        "message": "",
    }
    return job_id


def _enter_common_mocks(st):
    st.enter_context(patch.object(video_module, "extract_audio"))
    st.enter_context(patch.object(video_module, "detect_silence_silero", return_value=[]))
    st.enter_context(patch.object(video_module, "detect_silence", return_value=[]))
    st.enter_context(patch.object(video_module, "cut_and_concat"))
    st.enter_context(patch.object(
        video_module, "summarize_with_mishearings", return_value=("ctx", {}),
    ))
    st.enter_context(patch.object(
        video_module, "correct_transcript_segments",
        side_effect=lambda txt, video_context="": txt,
    ))
    st.enter_context(patch.object(video_module, "extract_keywords", return_value=[]))
    st.enter_context(patch.object(video_module, "apply_pipeline_combined"))
    st.enter_context(patch.object(
        video_module, "snap_silences_to_word_boundaries",
        side_effect=lambda s, w: s,
    ))
    st.enter_context(patch.object(video_module, "detect_filler_ranges", return_value=[]))
    st.enter_context(patch.object(video_module, "detect_tempo_ranges", return_value=[]))
    st.enter_context(patch.object(video_module, "detect_redundant_speech", return_value=[]))
    st.enter_context(patch.object(video_module, "detect_word_gaps", return_value=[]))
    st.enter_context(patch.object(video_module, "detect_restatements", return_value=[]))
    st.enter_context(patch.object(video_module, "merge_ranges", side_effect=lambda x: x))
    st.enter_context(patch.object(video_module, "load_corrections", return_value={}))
    st.enter_context(patch.object(video_module, "load_fillers", return_value=set()))
    st.enter_context(patch.object(
        video_module, "apply_corrections_to_words", side_effect=lambda w, c: w,
    ))
    st.enter_context(patch.object(
        video_module, "apply_corrections_to_text", side_effect=lambda t, c: t,
    ))
    st.enter_context(patch.object(video_module, "generate_hook", return_value=""))
    st.enter_context(patch.object(video_module, "select_bgm_style", return_value=""))
    st.enter_context(patch.object(video_module, "detect_topics", return_value=[]))


def test_stage5b_calls_third_transcribe_when_oversized_2nd_detected(tmp_path, monkeypatch):
    """施策F が発動して cut2.mp4 が生成されると、 字幕用に 3段目 transcribe(cut2_audio.wav)を呼ぶ。"""
    job_id = _setup_job(tmp_path, monkeypatch)

    word_for_jump = [
        {"start": 0.5, "end": 0.6, "text": "w1", "is_word_start": True},
    ]

    with ExitStack() as st:
        _enter_common_mocks(st)
        m_trans = st.enter_context(patch.object(video_module, "transcribe_with_words"))
        m_oversized = st.enter_context(patch.object(video_module, "detect_oversized_words"))
        st.enter_context(patch.object(
            video_module, "get_video_duration",
            side_effect=[10.0, 8.0, 8.0, 8.0, 6.0],
        ))
        st.enter_context(patch.object(
            video_module, "compute_voice_segments",
            side_effect=[
                [{"start": 0.0, "end": 10.0}],
                [{"start": 0.0, "end": 6.0}],
            ],
        ))
        m_trans.side_effect = [
            (word_for_jump, []),
            (word_for_jump, []),
            (word_for_jump, []),
        ]
        m_oversized.side_effect = [
            [],
            [{"start": 2.0, "end": 5.0}],
        ]

        settings = ProcessRequest(
            enable_subtitles=True,
            enable_jump_cut=True,
            enable_buzz_mode=False,
        )
        video_module._run_processing(job_id, settings)

    assert m_trans.call_count == 3
    third_call_audio = m_trans.call_args_list[2][0][0]
    assert third_call_audio.endswith("cut2_audio.wav")


def test_stage5b_falls_back_to_second_transcribe_when_no_oversized_2nd(tmp_path, monkeypatch):
    """施策F が発動しない (oversized_2nd 空) と、 字幕用は 2段目 words_cut にフォールバックして 3段目 transcribe は呼ばない。"""
    job_id = _setup_job(tmp_path, monkeypatch)

    words_safe = [
        {"start": 0.5, "end": 0.6, "text": "w1", "is_word_start": True},
        {"start": 7.4, "end": 7.5, "text": "w2", "is_word_start": True},
    ]

    with ExitStack() as st:
        _enter_common_mocks(st)
        m_trans = st.enter_context(patch.object(video_module, "transcribe_with_words"))
        m_oversized = st.enter_context(patch.object(video_module, "detect_oversized_words"))
        st.enter_context(patch.object(
            video_module, "get_video_duration",
            side_effect=[10.0, 8.0, 8.0],
        ))
        st.enter_context(patch.object(
            video_module, "compute_voice_segments",
            return_value=[{"start": 0.0, "end": 10.0}],
        ))
        m_trans.side_effect = [
            (words_safe, []),
            (words_safe, []),
        ]
        m_oversized.side_effect = [[], []]

        settings = ProcessRequest(
            enable_subtitles=True,
            enable_jump_cut=True,
            enable_buzz_mode=False,
        )
        video_module._run_processing(job_id, settings)

    assert m_trans.call_count == 2
    audios = [c[0][0] for c in m_trans.call_args_list]
    assert all(not a.endswith("cut2_audio.wav") for a in audios)


def test_hybrid_prepend_when_third_stage_misses_leading():
    """3段目 first_word.start が動画長 × 0.05(最低 2 秒)を超えると、 1段目補完を prepend する。"""
    from app.routers.video import _hybrid_prepend_leading_words

    third = [{"start": 30.0, "end": 30.3, "text": "目"}]
    first_in_target = [
        {"start": 5.0, "end": 5.3, "text": "客"},
        {"start": 5.4, "end": 5.7, "text": "様"},
    ]
    out, prepended = _hybrid_prepend_leading_words(
        third_words=third,
        first_stage_words_in_target=first_in_target,
        target_duration=100.0,
    )
    assert prepended == 2
    assert out[0]["text"] == "客"
    assert out[1]["text"] == "様"
    assert out[2]["text"] == "目"


def test_hybrid_no_prepend_when_third_stage_recognizes_leading():
    """3段目 first_word.start が閾値以下なら、 補完しない。"""
    from app.routers.video import _hybrid_prepend_leading_words

    third = [{"start": 0.5, "end": 0.8, "text": "客"}]
    first_in_target = [{"start": 0.2, "end": 0.4, "text": "お"}]
    out, prepended = _hybrid_prepend_leading_words(
        third_words=third,
        first_stage_words_in_target=first_in_target,
        target_duration=100.0,
    )
    assert prepended == 0
    assert out == third


def test_hybrid_prepend_respects_margin_and_sorts():
    """補完範囲は first_3rd_start - margin より前まで、 prepend 後は start で sort。"""
    from app.routers.video import _hybrid_prepend_leading_words

    third = [{"start": 30.0, "end": 30.3, "text": "目"}]
    # margin=0.1 で cutoff=29.9。 word.end 29.95 はギリギリ補完対象外
    first_in_target = [
        {"start": 5.4, "end": 5.7, "text": "様"},
        {"start": 5.0, "end": 5.3, "text": "客"},  # 順序が逆でも sort される
        {"start": 29.5, "end": 29.95, "text": "後"},  # end が cutoff 29.9 を越えるので除外
    ]
    out, prepended = _hybrid_prepend_leading_words(
        third_words=third,
        first_stage_words_in_target=first_in_target,
        target_duration=100.0,
    )
    assert prepended == 2
    assert out[0]["text"] == "客"
    assert out[1]["text"] == "様"
    assert out[2]["text"] == "目"
