# backend/app/routers/video.py
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
    apply_pipeline_combined,
)
from app.services.silence import compute_voice_segments
from app.services.subtitle import (
    transcribe_audio, transcribe_with_words, segments_to_srt, segments_to_ass,
    words_to_segments, apply_keyword_highlight,
)
from app.services.jump_cut import (
    detect_filler_ranges, detect_tempo_ranges, detect_redundant_speech,
    detect_word_gaps, load_fillers, merge_ranges,
    load_corrections, apply_corrections_to_words, apply_corrections_to_text,
)
from app.services.llm import (
    detect_restatements, correct_transcript_segments, extract_keywords, generate_hook,
    detect_topics, select_bgm_style, generate_captions, predict_buzz_score,
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
    """元時刻の words から、voice_segments に**完全に含まれる** word だけ残し、
    カット後動画の累積時刻に変換する。

    境界を跨ぐ word は除外（中途半端な時刻で字幕の表示時間が 0.09 秒のような
    異常値になるのを防ぐ）。is_word_start などの補助メタデータは保持する。
    """
    if not words or not segments:
        return []
    remapped: list[dict] = []
    offset = 0.0
    for seg in segments:
        seg_start, seg_end = seg["start"], seg["end"]
        for w in words:
            if w["start"] >= seg_start and w["end"] <= seg_end:
                new_w = {
                    "start": offset + (w["start"] - seg_start),
                    "end": offset + (w["end"] - seg_start),
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

    words, _segs = transcribe_with_words(
        audio_path, initial_prompt=settings.transcript_prompt or None,
    )

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

    return TranscribeResponse(
        job_id=job_id,
        segments=[
            TranscriptSegment(
                start=round(s["start"], 3),
                end=round(s["end"], 3),
                text=s["text"],
            )
            for s in sub_segments
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
                words, pre_cut_segments = transcribe_with_words(
                    audio_path,
                    initial_prompt=settings.transcript_prompt or None,
                )

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
            extra_cuts = merge_ranges(
                filler_cuts + tempo_cuts + restatement_cuts + redundant_cuts + word_gap_cuts
            )

        # 単語境界スナップ: silence と extra_cuts が単語の中で切らないよう補正
        if words:
            silences = snap_silences_to_word_boundaries(silences, words)
            if extra_cuts:
                extra_cuts = snap_silences_to_word_boundaries(extra_cuts, words)

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

        # Stage 4: Cut & concat
        job.update({"stage": "cut_concat", "progress": 55, "message": "不要区間を削除中..."})
        cut_output = str(job_dir / "cut.mp4")
        cut_and_concat(input_path, voice_segments, cut_output)

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
                words_cut, segs_cut = transcribe_with_words(
                    cut_audio,
                    initial_prompt=settings.transcript_prompt or None,
                )
                if corrections and words_cut:
                    words_cut = apply_corrections_to_words(words_cut, corrections)
                if words_cut:
                    sub_segments = words_to_segments(
                        words_cut, max_chars=settings.subtitle_max_chars,
                    )
                else:
                    sub_segments = segs_cut

            if not edited_provided:
                # 辞書置換 → LLM校正（編集済みなら適用しない）
                for seg in sub_segments:
                    seg["text"] = apply_corrections_to_text(seg["text"], corrections)

                texts = [s["text"] for s in sub_segments]
                corrected_texts = correct_transcript_segments(texts)
                for seg, new_text in zip(sub_segments, corrected_texts):
                    seg["text"] = new_text

            # キーワードハイライト（常時ON）— LLM でキーワード抽出
            full_text = " ".join(s["text"] for s in sub_segments)
            # キーワードは1動画あたり3-4語に絞ると視覚ノイズが減って読みやすい
            keywords = extract_keywords(full_text, max_keywords=4)

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
                (job_dir / "transcript.json").write_text(
                    _json.dumps(
                        {"segments": _clean_segs, "words": words},
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass

        # Stage 6: バズモード — トピック・フック・CTA・BGM・効果音 のパラメータ準備
        if settings.enable_buzz_mode:
            # 効果音タイムスタンプ
            sfx_p = Path("/app/app/data/sfx/cut.mp3")
            if sfx_p.exists() and len(voice_segments) >= 2:
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
                topics_raw = detect_topics(texts_for_topics)
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
            hook_text_str = generate_hook(hook_source_text) if hook_source_text else None
            if not hook_text_str:
                jump_cut_notes.append("フック生成をスキップしました（LLM未設定または失敗）")

            # CTA
            cta_text_str = "👇 保存して見返してね"

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

        # Stage 7: 全演出を1パスで適用
        needs_combined = any([
            subtitle_file_str, topics_for_overlay, hook_text_str, cta_text_str,
            bgm_path_str, sfx_path_str,
        ])
        output_path = job_dir / "output.mp4"
        if needs_combined:
            job.update({"stage": "render", "progress": 90, "message": "演出を統合適用中..."})
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
                )
                final_output = str(output_path)
            except Exception as e:
                jump_cut_notes.append(f"統合パス失敗: {e}")
                # フォールバック: 何もせずカット結果を使う
                shutil.copy2(cut_output, str(output_path))
                final_output = str(output_path)
        else:
            if str(output_path) != cut_output:
                shutil.copy2(cut_output, str(output_path))
            final_output = str(output_path)

        silence_removed = original_duration - processed_duration
        final_message = "処理が完了しました"
        if jump_cut_notes:
            final_message += "（" + " / ".join(jump_cut_notes) + "）"

        job.update({
            "status": JobStatus.COMPLETED,
            "stage": "done",
            "progress": 100,
            "message": final_message,
            "original_duration": round(original_duration, 2),
            "processed_duration": round(processed_duration, 2),
            "silence_removed": round(silence_removed, 2),
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
