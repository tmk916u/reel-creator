# backend/app/routers/video.py
#
# 動画処理パイプラインのステージ構成:
#   Stage 1 : 音声抽出 (extract_audio → audio.wav)
#   Stage 2 : 無音検出 (Silero VAD + ffmpeg silencedetect 補強)
#   Stage 3 : 1段目 transcribe(元動画 audio) + 施策A-E(filler/tempo/restate/redundant/word_gap/oversized)
#             末尾で protect_words_from_silences(ASR 認識範囲を silences から穴あけ)
#             + snap_silences_to_word_boundaries(silence の境界を word 境界に揃える)
#   Stage 4 : cut_and_concat → cut.mp4
#   Stage 5a: 2段目 transcribe(cut.mp4 audio) → 施策F(2段目 oversized) + 施策G(1+2段目 OR 無発話)→ cut2.mp4
#   Stage 5b: 字幕用 words 生成 (1段目 ASR + 1段 remap)
#             voice_segments と cut2_voices を合成した mapping で
#             1段目 words を直接 cut2 内時刻に変換 → words_to_segments → ASS/SRT
#             ※3段目 transcribe は廃止 (短い context で subword 断片化のため)
#             ※施策F 未発動時は cut2_voices=None で voice_segments のみ使う
#   Stage 6 : バズモード演出パラメータ準備(HOOK / CTA / topics / BGM / SFX)
#   Stage 7 : apply_pipeline_combined で 1パス焼き込み → output.mp4
#
# 字幕用 words は cut2(または cut)内時刻空間だけで構成され、
# `_filter_words_by_segments` による多段 remap を経由しない。
# 1+2段目 ASR は動画カット判定(施策F/G)に専念し、 字幕生成は 3段目で独立に取り直す。
import logging
import uuid
import shutil
import asyncio
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from app.models.schemas import (
    UploadResponse, ProcessRequest, ProcessResponse, ProgressEvent,
    JobStatus, JobResult, FontSize, SubtitlePosition, SubtitleColor,
    TranscribeRequest, TranscribeResponse, TranscriptSegment,
    CaptionsResponse, WriteCaptionsRequest, BuzzScoreResponse, BuzzScoreDetail,
)
from app.services.ffmpeg import (
    get_video_duration, extract_audio, detect_silence, cut_and_concat, burn_subtitles,
    overlay_hook_text, overlay_cta_text, overlay_topic_numbers, mix_bgm, mix_sfx_at_cuts,
    apply_pipeline_combined, resolve_lut_path, extract_grade_preview,
)
from app.services.reframe import compute_reframe_windows, probe_dimensions
from app.services.analyze import analyze_video
from app.services.qc import evaluate_qc
from app.services.silence import (
    compute_voice_segments,
    protect_words_from_silences,
    build_orig_to_cut2_mapping,
    remap_words_with_mapping,
)
from app.services.subtitle import (
    transcribe_audio, transcribe_with_words, segments_to_srt, segments_to_ass,
    words_to_segments, apply_keyword_highlight, detect_suspicious_segments,
)
from app.services.asr import clamp_oversized_word_ends
from app.config import CTA_TEXT
from app.services.jump_cut import (
    detect_filler_ranges, detect_tempo_ranges, detect_redundant_speech,
    detect_word_gaps, detect_oversized_words, load_fillers, merge_ranges,
    load_corrections, apply_corrections_to_words, apply_corrections_to_text,
)
from app.services.llm import (
    detect_restatements, correct_transcript_segments, extract_keywords, generate_hook,
    detect_topics, select_bgm_style, generate_captions, predict_buzz_score,
    summarize_video_context, summarize_with_mishearings,
    detect_coherence_violations, _coherence_enabled, _coherence_dry_run,
)
from app.services.vad import detect_silence_silero, snap_silences_to_word_boundaries

router = APIRouter(prefix="/api", tags=["video"])

TMP_DIR = Path("/app/tmp")
MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1GB
MAX_DURATION = 300  # 5 minutes
ALLOWED_TYPES = {"video/mp4", "video/quicktime", "video/webm"}

job_store: dict[str, dict] = {}


def _font_size_to_px(size: FontSize) -> int:
    return {"small": 16, "medium": 22, "large": 30}[size.value]


def _filter_words_by_segments(words: list[dict], segments: list[dict]) -> list[dict]:
    """元時刻の words を、voice_segments を結合したカット後動画の累積時刻に変換する。

    word の **開始点 (start) が voice_segment 内にある** word を採用し、
    word.end が segment 末尾を越える場合は segment_end でクランプする。
    こうすることで、施策F (2段目 oversized カット) で word の中央部だけ
    削除されたケース(例: 「整」word の duration 1.76秒のうち中央を削除)
    でも word の text を字幕に残せる。

    元実装は「完全包含」だったため、oversized word が削除されると
    word.text ごと失われ、字幕の冒頭文字が消える事象が発生していた。
    """
    if not words or not segments:
        return []
    remapped: list[dict] = []
    offset = 0.0
    for seg in segments:
        seg_start, seg_end = seg["start"], seg["end"]
        for w in words:
            if seg_start <= w["start"] < seg_end:
                w_end_clamped = min(w["end"], seg_end)
                # 最低 0.05 秒は表示時間を確保(0 秒 word を防ぐ)
                if w_end_clamped <= w["start"]:
                    w_end_clamped = min(w["start"] + 0.05, seg_end)
                new_w = {
                    "start": offset + (w["start"] - seg_start),
                    "end": offset + (w_end_clamped - seg_start),
                    "text": w["text"],
                }
                if "is_word_start" in w:
                    new_w["is_word_start"] = w["is_word_start"]
                remapped.append(new_w)
        offset += seg_end - seg_start
    return remapped


def _remap_edited_segments(segments: list, voice_segments: list[dict]) -> list[dict]:
    """編集済み字幕の元タイムスタンプを、カット後動画のタイムスタンプに変換する。

    segments: list of {start, end, text} or pydantic EditedSegment
    voice_segments: 有音区間（カット対象外）
    """
    if not voice_segments:
        return []

    # 元時刻 → カット後時刻のマッピングテーブル
    cumulative = []  # (orig_start, orig_end, cut_offset)
    offset = 0.0
    for vs in voice_segments:
        cumulative.append((vs["start"], vs["end"], offset))
        offset += vs["end"] - vs["start"]
    total_cut_dur = offset

    def map_time(t: float) -> float:
        """元時刻 t をカット後時刻に変換。カット範囲内は最寄りの境界に丸める。"""
        for orig_s, orig_e, cut_off in cumulative:
            if orig_s <= t <= orig_e:
                return cut_off + (t - orig_s)
        # カット範囲内 → 次の有音区間の先頭 or 直前の終端
        if t < cumulative[0][0]:
            return 0.0
        for i, (orig_s, orig_e, cut_off) in enumerate(cumulative):
            if t < orig_s:
                return cut_off  # 次の voice segment の開始
        return total_cut_dur

    remapped: list[dict] = []
    for seg in segments:
        s_start = float(seg.start) if hasattr(seg, "start") else float(seg["start"])
        s_end = float(seg.end) if hasattr(seg, "end") else float(seg["end"])
        s_text = seg.text if hasattr(seg, "text") else seg["text"]
        new_start = map_time(s_start)
        new_end = map_time(s_end)
        if new_end > new_start + 0.05:
            remapped.append({
                "start": new_start,
                "end": new_end,
                "text": s_text,
                "words": [],
            })
    return remapped


@router.post("/upload", response_model=UploadResponse)
async def upload_video(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}")

    job_id = str(uuid.uuid4())
    job_dir = TMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    input_path = job_dir / "input.mp4"
    file_size = 0
    with open(input_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            file_size += len(chunk)
            if file_size > MAX_FILE_SIZE:
                shutil.rmtree(job_dir)
                raise HTTPException(400, "File too large (max 1GB)")
            f.write(chunk)

    try:
        duration = get_video_duration(str(input_path))
    except RuntimeError:
        shutil.rmtree(job_dir)
        raise HTTPException(400, "Invalid video file")

    if duration > MAX_DURATION:
        shutil.rmtree(job_dir)
        raise HTTPException(400, f"Video too long ({duration:.1f}s, max {MAX_DURATION}s)")

    return UploadResponse(
        job_id=job_id,
        filename=file.filename or "video.mp4",
        duration=round(duration, 2),
        file_size=file_size,
    )


@router.post("/analyze/{job_id}")
def analyze_job(job_id: str):
    """おまかせ: 入力動画を解析し、種類に応じた推奨設定を返す。

    発話量(Silero VAD)と向き(横/縦)から profile(talk/visual/mixed)を判定し、
    ProcessRequest の推奨上書きを {label, reason, settings, ...} で返す。
    フロントはこれを設定に適用してから /process を呼ぶ。
    """
    job_dir = TMP_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(404, "Job not found")
    input_path = str(job_dir / "input.mp4")
    audio_path = str(job_dir / "audio.wav")
    if not Path(audio_path).exists():
        extract_audio(input_path, audio_path)
    return analyze_video(input_path, audio_path)


@router.post("/transcribe/{job_id}", response_model=TranscribeResponse)
async def transcribe_preview(job_id: str, settings: TranscribeRequest):
    """字幕プレビュー用エンドポイント。

    Whisper + 辞書置換 + LLM校正のみ実行し、編集可能なセグメントを返す。
    結果は job_store にキャッシュされ、後段の /process で再利用される。
    """
    job_dir = TMP_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(404, "Job not found")

    input_path = str(job_dir / "input.mp4")
    audio_path = str(job_dir / "audio.wav")

    if not Path(audio_path).exists():
        extract_audio(input_path, audio_path)

    words, _segs, asr_backend = transcribe_with_words(
        audio_path, initial_prompt=settings.transcript_prompt or None,
    )
    # clamp は ReazonSpeech の subword 単一点 timestamp 由来の異常長 word 専用。
    # WhisperX/faster-whisper は真の word.end を返すため clamp すると逆に短縮しすぎる。
    if asr_backend == "reazonspeech":
        words = clamp_oversized_word_ends(words)

    corrections = load_corrections()
    if corrections:
        words = apply_corrections_to_words(words, corrections)

    # 最終動画でカットされる区間のワードを除外し、単語境界でカットされるよう補正
    try:
        total_duration = get_video_duration(input_path)
        silences = detect_silence_silero(audio_path, min_silence_duration=0.5)
        if silences is None:
            silences = detect_silence(audio_path, -30.0, 0.5)
        # 単語の途中で切らないようにスナップ
        silences = snap_silences_to_word_boundaries(silences, words)
        voice_segs = compute_voice_segments(silences, total_duration)
        # 各 voice segment に**完全に**含まれるワードだけ残す（元時刻のまま）
        kept_words: list[dict] = []
        for w in words:
            for vs in voice_segs:
                if w["start"] >= vs["start"] and w["end"] <= vs["end"]:
                    kept_words.append(w)
                    break
        if kept_words:
            words = kept_words
    except Exception:
        pass

    sub_segments = words_to_segments(words)

    for seg in sub_segments:
        seg["text"] = apply_corrections_to_text(seg["text"], corrections)

    texts = [s["text"] for s in sub_segments]
    corrected_texts = correct_transcript_segments(texts)
    for seg, new_text in zip(sub_segments, corrected_texts):
        seg["text"] = new_text

    job_store[job_id] = {
        **(job_store.get(job_id) or {}),
        "transcript_words": words,
        "transcript_segments": sub_segments,
        "transcript_prompt": settings.transcript_prompt,
    }

    # ファイルにも永続化（バックエンド再起動後も /api/captions, /api/buzz-score で使えるように）
    try:
        import json as _json
        (job_dir / "transcript.json").write_text(
            _json.dumps(
                {
                    "words": words,
                    "segments": sub_segments,
                    "prompt": settings.transcript_prompt,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass

    suspicious_flags = detect_suspicious_segments(sub_segments)

    return TranscribeResponse(
        job_id=job_id,
        segments=[
            TranscriptSegment(
                start=round(s["start"], 3),
                end=round(s["end"], 3),
                text=s["text"],
                suspicious=suspicious_flags[i] if i < len(suspicious_flags) else False,
            )
            for i, s in enumerate(sub_segments)
        ],
    )


def _run_processing(job_id: str, settings: ProcessRequest):
    """Run video processing in background"""
    job = job_store[job_id]
    job_dir = TMP_DIR / job_id
    input_path = str(job_dir / "input.mp4")

    try:
        # Stage 1: Audio extraction
        job.update({"stage": "audio_extract", "progress": 10, "message": "音声を抽出中..."})
        audio_path = str(job_dir / "audio.wav")
        extract_audio(input_path, audio_path)

        # Stage 2: Silence detection (Silero VAD 優先、失敗時 ffmpeg にフォールバック)
        job.update({"stage": "silence_detect", "progress": 25, "message": "無音区間を解析中..."})
        silences = detect_silence_silero(
            audio_path,
            min_silence_duration=settings.min_silence_duration,
        )
        if silences is None:
            silences = detect_silence(
                audio_path, settings.silence_threshold, settings.min_silence_duration,
            )
        # 微小無音検出: word 内部に埋もれる「整骨院の前のちょっとした間」のような
        # 0.1〜0.2 秒の無音を ffmpeg silencedetect で別途検出して union する
        if settings.micro_silence_min_duration > 0:
            micro = detect_silence(
                audio_path,
                threshold=settings.silence_threshold,
                min_duration=settings.micro_silence_min_duration,
            )
            if micro:
                before = len(silences)
                silences = merge_ranges(silences + micro)
                logger.info(
                    "micro silence: +%d 件追加 (min=%.2fs), union後 %d → %d",
                    len(micro), settings.micro_silence_min_duration, before, len(silences),
                )
        original_duration = get_video_duration(input_path)

        # Stage 2.5 / 3: AI Jump Cut（有効時）
        words: list[dict] = []
        pre_cut_segments: list[dict] = []
        extra_cuts: list[dict] = []
        oversized_cuts: list[dict] = []
        jump_cut_notes: list[str] = []

        cached = job_store.get(job_id) or {}
        cached_words = cached.get("transcript_words") or []

        if settings.enable_jump_cut:
            if cached_words:
                # プレビュー段階で生成済みの transcript を再利用
                words = cached_words
                pre_cut_segments = cached.get("transcript_segments") or []
            else:
                job.update({
                    "stage": "transcribe_for_cut",
                    "progress": 30,
                    "message": "AIで音声を解析中...",
                })
                words, pre_cut_segments, asr_backend = transcribe_with_words(
                    audio_path,
                    initial_prompt=settings.transcript_prompt or None,
                )
                # subword timestamp 推定で word.end が次の word.start に押し出される
                # 現象 (「お」 word が 5-21秒) は ReazonSpeech 固有。WhisperX/faster-whisper
                # では発生しないため、ReazonSpeech のときのみクランプする。
                if asr_backend == "reazonspeech":
                    words = clamp_oversized_word_ends(words)

                # 同音異義語の辞書置換（タイムスタンプは保持）
                corrections = load_corrections()
                if corrections:
                    words = apply_corrections_to_words(words, corrections)

            job.update({
                "stage": "jump_cut",
                "progress": 40,
                "message": "AIで不要な間を検出中...",
            })
            fillers = load_fillers()
            filler_cuts = detect_filler_ranges(words, fillers)
            tempo_cuts = detect_tempo_ranges(
                words,
                max_pause=settings.tempo_max_pause,
                target_pause=settings.tempo_target_pause,
            )
            restatement_cuts = detect_restatements(words)
            if not restatement_cuts and words:
                jump_cut_notes.append("言い直し検出はスキップしました（LLM未設定または失敗）")
            # LLM 検出を機械的な類似度ベース重複検出で補強（離れた箇所での同じ話の繰り返し対策）
            redundant_cuts = detect_redundant_speech(words)
            if redundant_cuts:
                jump_cut_notes.append(f"重複発話 {len(redundant_cuts)} 区間を検出（機械的補強）")
            # word 間ギャップ削除（鼻啜り音・息継ぎ・考える間など、句読点不問の圧縮）
            word_gap_cuts = detect_word_gaps(
                words,
                max_gap=settings.word_gap_max,
                target_gap=settings.word_gap_target,
            )
            if word_gap_cuts:
                jump_cut_notes.append(f"発話間ギャップ {len(word_gap_cuts)} 箇所を圧縮")
            # 異常に長い word の中央を削除（ReazonSpeech の subword timestamp 推定で
            # 発話間の沈黙が word に取り込まれる現象への対策）
            # 注意1: oversized_cuts は "word 内部の中央" を削除する性質なので、 単語境界
            # snap を通すと両端が word 端に弾かれて削除区間が反転 → 破棄される。
            # extra_cuts とは別バケットで保持し、 snap 後に merge する。
            # 注意2: 長い word の中央が「全部無音」とは限らない。 例えば「お」 word が
            # 12秒で推定された場合、 中に「お客様が悩まれているダイエット」のような
            # 実発話が含まれている。 silero VAD を渡して word 内の実無音区間のみを
            # 削除対象にする。
            oversized_cuts = detect_oversized_words(
                words, silences, max_word_duration=settings.max_word_duration,
            )
            if oversized_cuts:
                total_secs = sum(c["end"] - c["start"] for c in oversized_cuts)
                jump_cut_notes.append(
                    f"異常に長い word {len(oversized_cuts)} 箇所の沈黙を削除 ({total_secs:.1f}秒)"
                )
            extra_cuts = merge_ranges(
                filler_cuts + tempo_cuts + restatement_cuts + redundant_cuts
                + word_gap_cuts
            )

            # LLM コヒーレンスパス（既存検出後の生存 word 列を別観点で再検出）
            # OpenSpec: openspec/changes/llm-coherence-pass/
            if _coherence_enabled() and words:
                surviving = [
                    w for w in words
                    if not any(c["start"] <= w["start"] < c["end"] for c in extra_cuts)
                ]
                if surviving:
                    coh_result = detect_coherence_violations(surviving)
                    coh_deletions = list(coh_result["deletions"])

                    # 残存 word 50% ガード（チャンク単位の暴走ガードでは見えない総合的な
                    # 暴走を捕捉する）。コヒーレンス削除を仮適用して、生存 word のうち
                    # 何個が残るかをカウント。50% を切ったら丸ごと破棄。
                    rejected_overall = False
                    if coh_deletions:
                        remaining = [
                            w for w in surviving
                            if not any(d["start"] <= w["start"] < d["end"] for d in coh_deletions)
                        ]
                        if len(remaining) < 0.5 * len(surviving):
                            coh_result["guard_actions"].append(
                                f"overall: remaining {len(remaining)} / {len(surviving)} words < 50%, "
                                f"all coherence deletions rejected"
                            )
                            coh_deletions = []
                            rejected_overall = True

                    # 本適用・dry-run どちらでも JSON にダンプする（分析スクリプト用）
                    # ファイル名で区別: coherence_dryrun.json / coherence_applied.json
                    is_dryrun = _coherence_dry_run()
                    applied_now = (not is_dryrun) and bool(coh_deletions)
                    coherence_path = job_dir / (
                        "coherence_dryrun.json" if is_dryrun else "coherence_applied.json"
                    )
                    import json as _json
                    coherence_path.write_text(
                        _json.dumps({
                            "deletions": coh_result["deletions"],
                            "applied_deletions": coh_deletions if applied_now else [],
                            "summary": coh_result["summary"],
                            "chunks_total": coh_result["chunks_total"],
                            "chunks_failed": coh_result["chunks_failed"],
                            "guard_actions": coh_result["guard_actions"],
                            "applied": applied_now,
                            "rejected_by_overall_guard": rejected_overall,
                            "input_words": len(surviving),
                        }, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    if is_dryrun:
                        jump_cut_notes.append(
                            f"コヒーレンスパス (dry-run): 候補 {len(coh_result['deletions'])} 件 → {coherence_path.name}"
                        )
                    elif coh_deletions:
                        extra_cuts = merge_ranges(extra_cuts + coh_deletions)
                        total_secs = sum(d["end"] - d["start"] for d in coh_deletions)
                        jump_cut_notes.append(
                            f"コヒーレンスパス: {len(coh_deletions)} 区間 {total_secs:.1f}秒 を追加削除 → {coherence_path.name}"
                        )

        # ASR-aware silence 保護: 1段目 ASR が word を認識した範囲は silero VAD が
        # 「無音」と判断していても voice_segments に物理的に残す。 silero と ASR の
        # 判断が食い違う場合は ASR を優先(誤って発話を削除しないため)。
        # 例: silero silence 0.0-20.75、 ASR word 「客」 20.38-20.70
        #     → silence は 0.0-20.28 に短縮、 20.28 以降は voice_segments に保護
        if words:
            silences = protect_words_from_silences(silences, words)

        # 単語境界スナップ: silence と extra_cuts が単語の中で切らないよう補正
        # 注意1: silences と extra_cuts を独立に snap すると、 隣接区間が word 境界
        # 調整時に微小ギャップ（0.05-0.15s）で分割され、 後段の min_cut_length=0.15
        # フィルタで弾かれて output に「ゾンビ無音」として残る現象が起きる。
        # 一度マージしてから 1 回だけ snap → 再マージで隣接区間を統合する。
        # 注意2: oversized_cuts は word 内部の中央削除なので snap させない。 snap を
        # 通すと両端が word 端に弾かれて削除区間が反転して破棄される。 snap 後に
        # merge_ranges で統合することで、 word 内部の中央削除と word 境界 snap を
        # 両立させる。
        diag_silences_pre_snap = list(silences)
        diag_extra_cuts_pre_snap = list(extra_cuts)
        diag_oversized_cuts = list(oversized_cuts)
        diag_combined_after_snap: list[dict] = []
        if words:
            combined_cuts = merge_ranges(list(silences) + list(extra_cuts))
            combined_cuts = snap_silences_to_word_boundaries(combined_cuts, words)
            diag_combined_after_snap = list(combined_cuts)
            combined_cuts = merge_ranges(combined_cuts + list(oversized_cuts))
            # extra_cuts は空にして、 統合結果を silences として下流に渡す
            silences = combined_cuts
            extra_cuts = []

        # 診断 dump: stage 毎の削除候補を job_dir/diagnostics.json に保存する。
        # 後段で analyze_reel.py が読み、 各 stage の挙動を可視化できる。
        # 構造的バグの再現/特定が transcript.json と diagnostics.json の 2 ファイル
        # だけで完結する。
        try:
            _diag = {
                "input_duration": original_duration,
                "word_count": len(words),
                "stages": {
                    "silences_pre_snap": diag_silences_pre_snap,
                    "extra_cuts_pre_snap": diag_extra_cuts_pre_snap,
                    "oversized_cuts": diag_oversized_cuts,
                    "combined_after_snap_pre_oversized": diag_combined_after_snap,
                    "final_silences": list(silences),
                },
                "totals": {
                    "silences_sec": round(sum(c["end"]-c["start"] for c in diag_silences_pre_snap), 2),
                    "extra_cuts_sec": round(sum(c["end"]-c["start"] for c in diag_extra_cuts_pre_snap), 2),
                    "oversized_sec": round(sum(c["end"]-c["start"] for c in diag_oversized_cuts), 2),
                    "combined_after_snap_sec": round(sum(c["end"]-c["start"] for c in diag_combined_after_snap), 2),
                    "final_silences_sec": round(sum(c["end"]-c["start"] for c in silences), 2),
                },
                "jump_cut_notes": list(jump_cut_notes),
            }
            import json as _json
            (job_dir / "diagnostics.json").write_text(
                _json.dumps(_diag, ensure_ascii=False, indent=2), encoding="utf-8",
            )
        except Exception as e:
            logger.warning("diagnostics.json dump failed: %s", e)

        # editor_mode == "director" ブランチ: LLM がストーリーを設計して残す clips を返す
        # OpenSpec: llm-director-editor
        # clips ∩ ¬silences で voice_segments を構築 → 既存の cut_and_concat 以降を再利用
        # 失敗時 (LLM error, JSON 不正, 全 clip 破棄, 尺範囲外) は rule_based にフォールバック
        director_used = False
        if getattr(settings, "editor_mode", "rule_based") == "director":
            try:
                from app.services.director import (
                    design_story, snap_clips_to_words, clips_to_voice_segments,
                )
                director_segments = pre_cut_segments or []
                clips = design_story(
                    director_segments,
                    duration=original_duration,
                    video_context="",  # video_context はこの時点では未生成。 将来統合
                    target_duration_min=getattr(settings, "director_target_min", 50.0),
                    target_duration_max=getattr(settings, "director_target_max", 80.0),
                )
                if clips:
                    snapped = snap_clips_to_words(clips, words)
                    voice_segments = clips_to_voice_segments(snapped, silences)
                    director_used = True
                    jump_cut_notes.append(
                        f"LLM director: {len(snapped)} clips → {len(voice_segments)} voice segments"
                    )
                    logger.info(
                        "director mode: clips=%d, voice_segments=%d, total=%.1fs",
                        len(snapped), len(voice_segments),
                        sum(v["end"] - v["start"] for v in voice_segments),
                    )
                else:
                    jump_cut_notes.append("LLM director 失敗 → 標準モードにフォールバック")
                    job.update({"message": "AI 監督モード失敗のため標準モードで処理"})
            except Exception as e:
                logger.exception("director mode 例外、 フォールバック: %s", e)
                jump_cut_notes.append(f"LLM director 例外 ({e}) → 標準モードにフォールバック")

        if not director_used:
            voice_segments = compute_voice_segments(
                silences, original_duration,
                padding=settings.voice_padding,
                extra_cuts=extra_cuts,
                trim_leading=settings.trim_leading_silence,
            )

        if not voice_segments:
            job.update({
                "status": JobStatus.FAILED,
                "stage": "error",
                "progress": 100,
                "message": "有音区間が見つかりませんでした",
            })
            return

        # Stage 4: Cut & concat（オートリフレーム有効時は被写体追従 crop を計算）
        crop_windows = None
        if settings.enable_auto_reframe:
            job.update({"stage": "reframe", "progress": 52,
                        "message": "被写体を解析中（オートリフレーム）..."})
            try:
                crop_windows = compute_reframe_windows(
                    input_path, voice_segments,
                    sample_fps=settings.reframe_sample_fps,
                    smoothing=settings.reframe_smoothing,
                    padding=settings.reframe_padding,
                )
                if crop_windows:
                    n = sum(1 for w in crop_windows if w)
                    jump_cut_notes.append(f"オートリフレーム: {n}/{len(crop_windows)} 区間で被写体追従")
                else:
                    jump_cut_notes.append("オートリフレーム: 被写体検出なし → 通常処理")
            except Exception as e:
                jump_cut_notes.append(f"オートリフレーム失敗 → 通常処理 ({e})")
                crop_windows = None

        job.update({"stage": "cut_concat", "progress": 55, "message": "不要区間を削除中..."})
        cut_output = str(job_dir / "cut.mp4")
        cut_and_concat(input_path, voice_segments, cut_output, crop_windows=crop_windows)

        processed_duration = get_video_duration(cut_output)
        final_output = cut_output

        # ====== 演出パラメータ準備（後で1つの ffmpeg パスでまとめて適用） ======
        subtitle_file_str: str | None = None
        subtitle_force_style: str | None = None
        sub_segments: list[dict] = []
        topics_for_overlay: list[dict] | None = None
        hook_text_str: str | None = None
        cta_text_str: str | None = None
        bgm_path_str: str | None = None
        sfx_path_str: str | None = None
        sfx_timestamps_list: list[float] | None = None

        # Stage 5: Subtitles (optional) — ファイル生成のみ、焼き込みは後段で
        edited_provided = bool(settings.edited_segments)
        if settings.enable_subtitles:
            job.update({"stage": "transcribe", "progress": 75, "message": "字幕を生成中..."})
            srt_path = str(job_dir / "subtitles.srt")
            corrections = load_corrections()

            if edited_provided:
                # 互換パス: ユーザー編集字幕は元時刻 → カット後時刻に変換
                # （境界跨ぎで時刻がずれる可能性あり。編集なしを推奨）
                sub_segments = _remap_edited_segments(
                    settings.edited_segments, voice_segments,
                )
            else:
                # 標準パス: cut.mp4 を再 transcribe → words がはじめからカット後時刻
                # （元時刻からの変換が不要になり、字幕のズレが構造的に発生しない）
                job.update({
                    "stage": "transcribe",
                    "progress": 78,
                    "message": "カット後の字幕を生成中...",
                })
                cut_audio = str(job_dir / "cut_audio.wav")
                extract_audio(cut_output, cut_audio)
                words_cut, segs_cut, asr_backend_cut = transcribe_with_words(
                    cut_audio,
                    initial_prompt=settings.transcript_prompt or None,
                )
                if asr_backend_cut == "reazonspeech":
                    words_cut = clamp_oversized_word_ends(words_cut)
                if corrections and words_cut:
                    words_cut = apply_corrections_to_words(words_cut, corrections)

                cut2_generated = False
                cut2_voices_used: list[dict] | None = None

                # 施策F: 2 段目 oversized カット
                # cut.mp4 を再 transcribe すると、元 transcribe では現れなかった
                # 「長い word に埋もれる沈黙」が新たに見つかることがある。
                # これを再カットして cut2.mp4 を生成し、字幕も再マッピングする。
                if settings.enable_jump_cut and words_cut:
                    # cut_audio の VAD silence を取得し、 word 内の実無音区間のみを
                    # 削除対象にする (元 audio と同じ方針)
                    cut_silences = detect_silence_silero(
                        cut_audio, min_silence_duration=settings.min_silence_duration,
                    ) or []
                    oversized_2nd = detect_oversized_words(
                        words_cut, cut_silences,
                        max_word_duration=settings.max_word_duration,
                    )
                    # 施策G: ASR が word を一つも検出しなかった「冒頭・末尾の無発話」を削除
                    # VAD/silencedetect が拾えない呼吸音・環境音などが残るケースに対処
                    # 施策G(汎用版): 1段目+2段目の両方の ASR で「無発話」と合意した
                    # 範囲のみを削除候補とする。片方でも発話を認識していれば残す。
                    # ハードコード上限は廃止し、ASR 結果同士のクロスチェックで汎用化。
                    #
                    # 仕組み:
                    # - 1段目: 元動画 audio に対する transcribe = cached/再構築の words (元時刻)
                    # - 2段目: cut.mp4 audio に対する transcribe = words_cut (cut.mp4 内時刻)
                    # 1段目 words を voice_segments で cut.mp4 内時刻に remap して、
                    # 「両方の ASR が冒頭/末尾の発話を見つけられなかった範囲」だけ削除する。
                    cut_duration_pre = get_video_duration(cut_output)
                    leading_threshold = 1.0
                    trailing_threshold = 1.0
                    first_dur = words_cut[0]["end"] - words_cut[0]["start"]
                    last_dur = words_cut[-1]["end"] - words_cut[-1]["start"]
                    first_is_normal = first_dur <= settings.max_word_duration
                    last_is_normal = last_dur <= settings.max_word_duration

                    # 1段目 transcribe の words を cut.mp4 内時刻にマッピング
                    words_in_cut_1st: list[dict] = []
                    if words and voice_segments:
                        words_in_cut_1st = _filter_words_by_segments(words, voice_segments)

                    # 「両方の ASR が認識した最も早い/最も遅い発話」を採用
                    earliest_1st = words_in_cut_1st[0]["start"] if words_in_cut_1st else float("inf")
                    earliest_2nd = words_cut[0]["start"] if words_cut else float("inf")
                    combined_first = min(earliest_1st, earliest_2nd)
                    latest_1st = words_in_cut_1st[-1]["end"] if words_in_cut_1st else 0.0
                    latest_2nd = words_cut[-1]["end"] if words_cut else 0.0
                    combined_last = max(latest_1st, latest_2nd)

                    if first_is_normal and combined_first > leading_threshold and combined_first < float("inf"):
                        cut_end = max(0.0, combined_first - 0.2)
                        if cut_end > 0.05:
                            oversized_2nd.append({"start": 0.0, "end": cut_end})
                            logger.info(
                                "冒頭無発話: 0.0-%.2fs を削除候補に追加 "
                                "(1段目=%.2fs, 2段目=%.2fs の小さい方)",
                                cut_end, earliest_1st, earliest_2nd,
                            )
                    elif not first_is_normal:
                        logger.info(
                            "冒頭 word が oversized(%.2fs) → 施策G スキップ、施策F に委任",
                            first_dur,
                        )
                    if last_is_normal and combined_last < cut_duration_pre - trailing_threshold:
                        cut_start = combined_last + 0.2
                        if cut_duration_pre - cut_start > 0.05:
                            oversized_2nd.append({"start": cut_start, "end": cut_duration_pre})
                            logger.info(
                                "末尾無発話: %.2f-%.2fs を削除候補に追加 "
                                "(1段目=%.2fs, 2段目=%.2fs の大きい方)",
                                cut_start, cut_duration_pre, latest_1st, latest_2nd,
                            )
                    elif not last_is_normal:
                        logger.info(
                            "末尾 word が oversized(%.2fs) → 施策G スキップ、施策F に委任",
                            last_dur,
                        )
                    if oversized_2nd:
                        total = sum(c["end"] - c["start"] for c in oversized_2nd)
                        logger.info(
                            "2段目 oversized: %d 箇所 %.1fs を削除",
                            len(oversized_2nd), total,
                        )
                        cut_duration = get_video_duration(cut_output)
                        cut2_voices = compute_voice_segments(
                            silences=[],  # cut.mp4 にはもう silence は無いはず
                            total_duration=cut_duration,
                            padding=settings.voice_padding,
                            extra_cuts=oversized_2nd,
                        )
                        if cut2_voices:
                            cut2_output = str(job_dir / "cut2.mp4")
                            cut_and_concat(cut_output, cut2_voices, cut2_output)
                            cut_output = cut2_output
                            final_output = cut2_output
                            processed_duration = get_video_duration(cut2_output)
                            cut2_generated = True
                            cut2_voices_used = cut2_voices

                # Stage 5b: 字幕用 words の取得
                # 動画カット判定(施策F/G)に使った words / words_cut は字幕生成から切り離す。
                # 字幕用は cut2.mp4(または cut.mp4)を直接 transcribe して時刻空間を統一する。
                # 旧構成では 1段目 words を _filter_words_by_segments で 2段 remap していたが、
                # voice_segments の境界跨ぎで subword の語順が崩れる事象が確認された
                # (reel_d8d062dc:「様が悩まれているダイエットお客」)。 本実装で根治。
                subtitle_words: list[dict] = []
                # Stage 5b: 字幕用 words の生成 (1段目 ASR + 1 段 remap)
                # voice_segments と cut2_voices を合成した 1 段マッピングで
                # 1段目 words を直接 cut2 内時刻に変換する。 中間状態を経由しないので
                # 過去の 2 段 remap で発生していた subword 語順崩壊が原理的に発生しない。
                # 3 段目 transcribe (cut2.mp4) は短い context で subword 断片化する
                # 問題が観測されたため廃止 (job 0ca6b31b で「客 事への」 の断片化)。
                job.update({
                    "stage": "transcribe",
                    "progress": 80,
                    "message": "字幕を生成中...",
                })
                mappings = build_orig_to_cut2_mapping(
                    voice_segments, cut2_voices_used,
                )
                subtitle_words = remap_words_with_mapping(words, mappings)
                if corrections and subtitle_words:
                    subtitle_words = apply_corrections_to_words(subtitle_words, corrections)
                logger.info(
                    "字幕用 words: 1段目 ASR + 1段 remap (%d mappings → %d words, 施策F %s)",
                    len(mappings), len(subtitle_words),
                    "発動" if cut2_generated else "未発動",
                )

                if subtitle_words:
                    sub_segments = words_to_segments(
                        subtitle_words, max_chars=settings.subtitle_max_chars,
                    )
                else:
                    sub_segments = segs_cut

            # 動画の文脈サマリー + 動画固有の誤認識辞書を 1 回の LLM 呼出で生成
            # (案②: イタチごっこ対策の柱)
            pre_correction_text = " ".join(s["text"] for s in sub_segments)
            video_context, dynamic_corrections = summarize_with_mishearings(pre_correction_text)

            if not edited_provided:
                # 辞書置換: 動画固有(LLM抽出) + 静的(jp_corrections.txt) を union
                # 静的辞書を後勝ちにして、検証済みパターンを優先
                merged_corrections = {**dynamic_corrections, **corrections}
                for seg in sub_segments:
                    seg["text"] = apply_corrections_to_text(seg["text"], merged_corrections)

                texts = [s["text"] for s in sub_segments]
                corrected_texts = correct_transcript_segments(texts, video_context=video_context)
                for seg, new_text in zip(sub_segments, corrected_texts):
                    seg["text"] = new_text

            # キーワードハイライト（常時ON）— LLM でキーワード抽出
            full_text = " ".join(s["text"] for s in sub_segments)
            # キーワードは1動画あたり3-4語に絞ると視覚ノイズが減って読みやすい
            keywords = extract_keywords(full_text, max_keywords=4, video_context=video_context)

            # バズモード時は ASS でモーション字幕、それ以外は SRT
            has_word_data = any(s.get("words") for s in sub_segments)
            if settings.enable_buzz_mode and has_word_data and not edited_provided:
                ass_path = str(job_dir / "subtitles.ass")
                vw = vh = 1080
                try:
                    probe_out = subprocess.run(
                        ["ffprobe", "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=width,height",
                         "-of", "csv=p=0:s=,", input_path],
                        capture_output=True, text=True, check=True,
                    )
                    parts = probe_out.stdout.strip().split(",")
                    if len(parts) == 2:
                        vw, vh = int(parts[0]), int(parts[1])
                except Exception:
                    pass
                Path(ass_path).write_text(
                    segments_to_ass(
                        sub_segments,
                        font_size=_font_size_to_px(settings.font_size),
                        position=settings.subtitle_position.value,
                        primary_color="#FFFFFF",
                        karaoke_color="#FFFF66",
                        keywords=keywords,
                        keyword_color="#FFD700",
                        video_width=vw,
                        video_height=vh,
                        motion_style=settings.subtitle_motion,
                    ),
                    encoding="utf-8",
                )
                subtitle_file_str = ass_path
            else:
                if keywords:
                    for seg in sub_segments:
                        seg["text"] = apply_keyword_highlight(seg["text"], keywords)
                Path(srt_path).write_text(segments_to_srt(sub_segments), encoding="utf-8")
                subtitle_file_str = srt_path
                # SRT 経由なら force_style を構築
                _color_hex = "&H00FFFFFF" if settings.subtitle_color.value == "white" else "&H0000FFFF"
                _alignment = 2 if settings.subtitle_position.value == "bottom" else 5
                subtitle_force_style = (
                    f"FontSize={_font_size_to_px(settings.font_size)},"
                    f"PrimaryColour={_color_hex},"
                    f"OutlineColour=&H00000000,"
                    f"BackColour=&HC0000000,"
                    f"Alignment={_alignment},"
                    f"BorderStyle=3,Outline=3,Shadow=0,MarginV=40,Bold=1,"
                    f"FontName=Noto Sans CJK JP"
                )

            # 後段の /api/captions /api/buzz-score 用に transcript を永続化
            # words / segments 共に **字幕と同じ時刻空間** (cut2 or cut 内時刻) で揃える。
            # 旧実装は words に 1段目 transcribe(元時刻)を保存しており、 segments(cut2内時刻)と
            # 不整合が起き、 measure_quality の #6 同期判定が誤った bad_count を返していた。
            try:
                import json as _json
                import re as _re
                _clean_segs = [
                    {
                        "start": s["start"], "end": s["end"],
                        "text": _re.sub(r"<[^>]+>", "", s.get("text", "")),
                    }
                    for s in sub_segments
                ]
                persisted_words = subtitle_words if not edited_provided else []
                (job_dir / "transcript.json").write_text(
                    _json.dumps(
                        {"segments": _clean_segs, "words": persisted_words},
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass

        # Stage 6: バズモード — トピック・フック・CTA・BGM・効果音 のパラメータ準備
        if settings.enable_buzz_mode:
            # 効果音タイムスタンプ(enable_sfx ON かつファイル配置時のみ)
            sfx_p = Path("/app/app/data/sfx/cut.mp3")
            if settings.enable_sfx and sfx_p.exists() and len(voice_segments) >= 2:
                cum = 0.0
                cut_points: list[float] = []
                for i, vs in enumerate(voice_segments):
                    if i > 0:
                        cut_points.append(round(cum, 3))
                    cum += vs["end"] - vs["start"]
                filtered: list[float] = []
                for t in cut_points:
                    if not filtered or t - filtered[-1] >= 0.5:
                        filtered.append(t)
                    if len(filtered) >= 20:
                        break
                if filtered:
                    sfx_path_str = str(sfx_p)
                    sfx_timestamps_list = filtered

            # トピック番号
            if sub_segments and len(sub_segments) >= 4:
                job.update({"stage": "buzz_topics", "progress": 80, "message": "ポイントを抽出中..."})
                texts_for_topics = [s["text"] for s in sub_segments]
                topics_raw = detect_topics(texts_for_topics, video_context=video_context)
                tlist: list[dict] = []
                for i, t in enumerate(topics_raw):
                    seg_idx = t["start_seg"]
                    if seg_idx >= len(sub_segments):
                        continue
                    start_time = sub_segments[seg_idx]["start"]
                    if i + 1 < len(topics_raw):
                        next_seg = topics_raw[i + 1]["start_seg"]
                        end_time = sub_segments[min(next_seg, len(sub_segments) - 1)]["start"]
                    else:
                        end_time = sub_segments[-1]["end"]
                    tlist.append({
                        "index": t["index"],
                        "start": start_time,
                        "end": end_time,
                        "label": t["label"],
                    })
                if tlist:
                    topics_for_overlay = tlist

            # 冒頭フック
            job.update({"stage": "buzz_hook", "progress": 85, "message": "冒頭フックを生成中..."})
            hook_source_text = ""
            if sub_segments:
                hook_source_text = " ".join(s["text"] for s in sub_segments)
            elif words:
                hook_source_text = " ".join(w["text"] for w in words)
            hook_text_str = generate_hook(hook_source_text, video_context=video_context) if hook_source_text else None
            if not hook_text_str:
                jump_cut_notes.append("フック生成をスキップしました（LLM未設定または失敗）")

            # CTA (config から読み、絵文字豆腐を避けるため CJK 対応文字を使用)
            cta_text_str = CTA_TEXT

            # BGM
            bgm_source_text = hook_source_text or (
                " ".join(w["text"] for w in words[:200]) if words else ""
            )
            bgm_style = select_bgm_style(bgm_source_text) if bgm_source_text else ""
            if bgm_style:
                bgm_dir = Path("/app/app/data/bgm")
                for ext in (".mp3", ".m4a", ".wav"):
                    candidate = bgm_dir / f"{bgm_style}{ext}"
                    if candidate.exists():
                        bgm_path_str = str(candidate)
                        break
                if not bgm_path_str:
                    jump_cut_notes.append(f"BGMファイル未配置（{bgm_style}）")

        # Stage 7: 全演出 + 音量正規化を1パスで適用
        # 字幕・演出・BGM・SFX のどれも要求されない場合でも、loudnorm を必ず通す
        # ため apply_pipeline_combined を必ず呼ぶ（公開可能品質 -14 LUFS 担保）。
        output_path = job_dir / "output.mp4"
        job.update({"stage": "render", "progress": 90, "message": "演出と音量を統合適用中..."})
        color_grade_lut_str = resolve_lut_path(
            settings.color_grade.value, Path("/app/app/data/luts")
        )
        if settings.color_grade.value != "none" and color_grade_lut_str is None:
            jump_cut_notes.append(f"カラーグレードLUT未配置（{settings.color_grade.value}）")
        try:
            apply_pipeline_combined(
                cut_output, str(output_path), job_dir,
                subtitle_file=subtitle_file_str,
                subtitle_force_style=subtitle_force_style,
                topics=topics_for_overlay,
                hook_text=hook_text_str,
                cta_text=cta_text_str,
                bgm_path=bgm_path_str,
                sfx_path=sfx_path_str,
                sfx_timestamps_sec=sfx_timestamps_list,
                topic_style=settings.topic_style,
                color_grade_lut=color_grade_lut_str,
            )
            final_output = str(output_path)
        except Exception as e:
            # apply_pipeline_combined は字幕・演出・BGM・SFX・音量正規化 を1つの ffmpeg
            # コマンドにまとめるためモノリシックで、部分失敗を区別できない。
            # 字幕なし動画を「完了」として返すと公開可能品質の判定が破綻する
            # ため、ここではフォールバックせず失敗で扱う（cut.mp4 は job_dir に残る）。
            raise RuntimeError(f"演出統合に失敗しました（字幕/演出/BGM/SFX/音量 いずれか）: {e}") from e

        silence_removed = original_duration - processed_duration
        final_message = "処理が完了しました"
        if jump_cut_notes:
            final_message += "（" + " / ".join(jump_cut_notes) + "）"

        # 自動 QC: 投稿前に気づきたい問題を検出して警告を付与する
        try:
            out_dims = probe_dimensions(str(output_path)) or (None, None)
            qc_issues = evaluate_qc({
                "original_duration": original_duration,
                "processed_duration": processed_duration,
                "width": out_dims[0],
                "height": out_dims[1],
                "subtitles_enabled": bool(settings.enable_subtitles),
                "segment_count": len(sub_segments),
                "suspicious_count": sum(detect_suspicious_segments(sub_segments)),
            })
        except Exception:
            qc_issues = []

        job.update({
            "status": JobStatus.COMPLETED,
            "stage": "done",
            "progress": 100,
            "message": final_message,
            "original_duration": round(original_duration, 2),
            "processed_duration": round(processed_duration, 2),
            "silence_removed": round(silence_removed, 2),
            "qc_issues": qc_issues,
        })

    except Exception as e:
        job.update({
            "status": JobStatus.FAILED,
            "stage": "error",
            "progress": 100,
            "message": f"処理エラー: {str(e)}",
        })


@router.post("/process/{job_id}", response_model=ProcessResponse)
async def process_video(job_id: str, settings: ProcessRequest, background_tasks: BackgroundTasks):
    job_dir = TMP_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(404, "Job not found")

    # 重複起動防止: PROCESSING 状態なら新規起動しない
    existing = job_store.get(job_id)
    if existing and existing.get("status") == JobStatus.PROCESSING and existing.get("stage") not in (None, "", "init"):
        return ProcessResponse(job_id=job_id, status=JobStatus.PROCESSING)

    # transcript キャッシュは保持し、ジョブ状態だけリセット
    cached = job_store.get(job_id) or {}
    job_store[job_id] = {
        **{k: v for k, v in cached.items() if k.startswith("transcript_")},
        "status": JobStatus.PROCESSING,
        "stage": "init",
        "progress": 0,
        "message": "処理を開始します...",
    }

    background_tasks.add_task(_run_processing, job_id, settings)

    return ProcessResponse(job_id=job_id, status=JobStatus.PROCESSING)


@router.get("/progress/{job_id}")
async def progress_stream(job_id: str):
    async def event_generator():
        while True:
            job = job_store.get(job_id)
            if not job:
                yield {"data": '{"error": "Job not found"}'}
                break

            event = ProgressEvent(
                job_id=job_id,
                status=job["status"],
                stage=job.get("stage", ""),
                progress=job.get("progress", 0),
                message=job.get("message", ""),
            )
            yield {"data": event.model_dump_json()}

            if job["status"] in (JobStatus.COMPLETED, JobStatus.FAILED):
                break

            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@router.get("/result/{job_id}", response_model=JobResult)
async def get_result(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != JobStatus.COMPLETED:
        raise HTTPException(400, "Job not completed yet")

    return JobResult(
        job_id=job_id,
        status=job["status"],
        original_duration=job["original_duration"],
        processed_duration=job["processed_duration"],
        silence_removed=job["silence_removed"],
        qc_issues=job.get("qc_issues") or [],
    )


@router.get("/download/{job_id}")
async def download_video(job_id: str):
    output_path = TMP_DIR / job_id / "output.mp4"
    if not output_path.exists():
        raise HTTPException(404, "Output file not found")

    return FileResponse(
        str(output_path),
        media_type="video/mp4",
        filename=f"reel_{job_id[:8]}.mp4",
    )


_PREVIEW_GRADES = ("none", "minimal", "cinematic", "monochrome", "pop")


@router.get("/preview/{job_id}/grade/{grade}")
def preview_grade(job_id: str, grade: str):
    """入力動画の代表フレームに各カラーグレード(LUT)を適用したサムネイルを返す。

    テイスト選択前に、ユーザー自身の映像で色味を見比べるためのプレビュー。
    job_dir/preview_{grade}.jpg にキャッシュし、再リクエストは即返す。
    """
    if grade not in _PREVIEW_GRADES:
        raise HTTPException(404, f"未知のテイスト: {grade}")

    job_dir = TMP_DIR / job_id
    input_path = job_dir / "input.mp4"
    if not input_path.exists():
        raise HTTPException(404, "アップロード動画が見つかりません")

    cache_path = job_dir / f"preview_{grade}.jpg"
    if not cache_path.exists():
        try:
            duration = get_video_duration(str(input_path))
        except RuntimeError:
            duration = 0.0
        # 黒い導入フレームを避けるため尺の 40% 付近を代表フレームにする
        timestamp = min(max(duration * 0.4, 0.0), max(duration - 0.1, 0.0))
        lut_path = (
            None if grade == "none"
            else resolve_lut_path(grade, Path("/app/app/data/luts"))
        )
        try:
            extract_grade_preview(
                str(input_path), str(cache_path),
                lut_path=lut_path, timestamp=timestamp,
            )
        except RuntimeError as e:
            raise HTTPException(500, f"プレビュー生成に失敗しました: {e}")

    return FileResponse(str(cache_path), media_type="image/jpeg")


def _get_cached_transcript(job_id: str) -> str:
    """job_store または job_dir/transcript.json からキャッシュされた transcript テキストを取得する。"""
    cached = job_store.get(job_id) or {}
    segs = cached.get("transcript_segments") or []
    if segs:
        return " ".join(s.get("text", "") for s in segs)
    words = cached.get("transcript_words") or []
    if words:
        return " ".join(w.get("text", "") for w in words)

    # メモリに無い場合は disk から読み込み（再起動後の救済）
    try:
        import json as _json
        path = TMP_DIR / job_id / "transcript.json"
        if path.exists():
            data = _json.loads(path.read_text(encoding="utf-8"))
            disk_segs = data.get("segments") or []
            if disk_segs:
                return " ".join(s.get("text", "") for s in disk_segs)
            disk_words = data.get("words") or []
            if disk_words:
                return " ".join(w.get("text", "") for w in disk_words)
    except Exception:
        pass

    return ""


@router.post("/captions/{job_id}", response_model=CaptionsResponse)
async def generate_captions_endpoint(job_id: str):
    """動画の transcript から TikTok / Instagram 用のキャプション＆ハッシュタグを生成。"""
    text = _get_cached_transcript(job_id)
    if not text:
        raise HTTPException(404, "Transcript not found for this job")

    captions = generate_captions(text)
    if not captions["tiktok_caption"] and not captions["instagram_caption"]:
        raise HTTPException(503, "LLM caption generation failed (check LLM_PROVIDER)")

    return CaptionsResponse(
        job_id=job_id,
        tiktok_caption=captions["tiktok_caption"],
        instagram_caption=captions["instagram_caption"],
        hashtags=captions["hashtags"],
    )


@router.post("/captions/{job_id}/write-sheet")
async def write_captions_to_sheet_endpoint(job_id: str, payload: WriteCaptionsRequest):
    """生成済みキャプションを Google Sheets の指定行に書き込む。"""
    try:
        from app.services.google_sheets import write_captions_to_sheet
        write_captions_to_sheet(
            payload.sheet_row,
            payload.ig_caption,
            payload.tiktok_caption,
            payload.hashtags,
        )
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"Sheets write failed: {e}")
    return {"job_id": job_id, "sheet_row": payload.sheet_row, "ok": True}


@router.post("/buzz-score/{job_id}", response_model=BuzzScoreResponse)
async def buzz_score_endpoint(job_id: str):
    """動画の transcript からバズり予測スコアと改善案を返す。"""
    text = _get_cached_transcript(job_id)
    if not text:
        raise HTTPException(404, "Transcript not found for this job")

    result = predict_buzz_score(text)
    if result is None:
        raise HTTPException(503, "LLM buzz score prediction failed (check LLM_PROVIDER)")

    return BuzzScoreResponse(
        job_id=job_id,
        overall=result["overall"],
        scores=BuzzScoreDetail(**result["scores"]),
        strengths=result["strengths"],
        weaknesses=result["weaknesses"],
        suggestions=result["suggestions"],
    )
