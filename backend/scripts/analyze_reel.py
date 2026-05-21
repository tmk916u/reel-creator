#!/usr/bin/env python3
"""reel 分析スクリプト。

使い方（コンテナ内で）:
    docker exec reel-creator-backend-1 python /app/scripts/analyze_reel.py <job_id>

または job_id 省略で /app/tmp/ の最新ジョブを自動選択:
    docker exec reel-creator-backend-1 python /app/scripts/analyze_reel.py

出力:
    JSON で {durations, loudness, output_segments, gaps, coherence, subtitle, summary}

設計意図:
- 「測ってから直す」サイクルの高速化（手作業 5-10 分 → 30 秒）
- 本適用後のコヒーレンスパス削除箇所を、coherence_applied.json 経由で確認
- 出力 reel の無音ギャップ（≥2秒）を自動検出し、構造的バグを可視化
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


TMP_DIR = Path("/app/tmp")
GAP_THRESHOLD_SEC = 2.0  # ≥ この秒数の無音ギャップを問題として記録


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def get_duration(path: Path) -> float | None:
    if not path.exists():
        return None
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    try:
        return round(float(r.stdout.strip()), 2)
    except ValueError:
        return None


def get_loudness(path: Path) -> dict | None:
    if not path.exists():
        return None
    r = _run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
        "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=summary",
        "-f", "null", "-",
    ])
    out = r.stderr
    integrated = re.search(r"Input Integrated:\s*(-?[\d.]+)\s*LUFS", out)
    true_peak = re.search(r"Input True Peak:\s*(-?[\d.]+)\s*dBTP", out)
    lra = re.search(r"Input LRA:\s*(-?[\d.]+)\s*LU", out)
    if not integrated:
        return None
    return {
        "integrated_lufs": float(integrated.group(1)),
        "true_peak_dbtp": float(true_peak.group(1)) if true_peak else None,
        "lra_lu": float(lra.group(1)) if lra else None,
    }


def reasr_output(path: Path) -> list[dict]:
    if not path.exists():
        return []
    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(
        str(path), language="ja", word_timestamps=False, vad_filter=False,
    )
    return [
        {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
        for s in segs
    ]


def detect_gaps(segments: list[dict], output_duration: float) -> list[dict]:
    """連続セグメント間の無音ギャップを検出する。"""
    if not segments:
        return []
    gaps: list[dict] = []
    # 冒頭ギャップ
    if segments[0]["start"] >= GAP_THRESHOLD_SEC:
        gaps.append({
            "kind": "leading",
            "start": 0.0, "end": segments[0]["start"],
            "duration": round(segments[0]["start"], 2),
        })
    # セグメント間
    for i in range(len(segments) - 1):
        gap_start = segments[i]["end"]
        gap_end = segments[i + 1]["start"]
        gap_dur = gap_end - gap_start
        if gap_dur >= GAP_THRESHOLD_SEC:
            gaps.append({
                "kind": "between",
                "start": round(gap_start, 2),
                "end": round(gap_end, 2),
                "duration": round(gap_dur, 2),
                "after_text": segments[i]["text"][:40],
                "before_text": segments[i + 1]["text"][:40],
            })
    # 末尾ギャップ
    if output_duration and segments[-1]["end"] + GAP_THRESHOLD_SEC <= output_duration:
        gaps.append({
            "kind": "trailing",
            "start": segments[-1]["end"], "end": output_duration,
            "duration": round(output_duration - segments[-1]["end"], 2),
        })
    return gaps


def read_coherence(job_dir: Path) -> dict | None:
    """dryrun / applied のどちらかが存在すれば読む。 両方あれば applied 優先。"""
    applied = job_dir / "coherence_applied.json"
    dryrun = job_dir / "coherence_dryrun.json"
    target = applied if applied.exists() else dryrun if dryrun.exists() else None
    if target is None:
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        data["__source"] = target.name
        return data
    except Exception:
        return None


def read_subtitle_summary(job_dir: Path) -> dict | None:
    ass = job_dir / "subtitles.ass"
    if not ass.exists():
        return None
    text = ass.read_text(encoding="utf-8", errors="ignore")
    dialogues = [l for l in text.splitlines() if l.startswith("Dialogue:")]
    samples = []
    for d in dialogues[:5]:
        parts = d.split(",", 9)
        if len(parts) >= 10:
            samples.append({"start": parts[1].strip(), "end": parts[2].strip(), "text": parts[9].strip()})
    return {"dialogue_count": len(dialogues), "samples": samples}


def find_latest_job() -> str | None:
    if not TMP_DIR.exists():
        return None
    jobs = sorted(
        [p for p in TMP_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return jobs[0].name if jobs else None


def analyze(job_id: str) -> dict:
    job_dir = TMP_DIR / job_id
    if not job_dir.exists():
        return {"error": f"job_dir not found: {job_dir}"}

    durations = {
        "input": get_duration(job_dir / "input.mp4"),
        "cut": get_duration(job_dir / "cut.mp4"),
        "cut2": get_duration(job_dir / "cut2.mp4"),
        "output": get_duration(job_dir / "output.mp4"),
    }
    loudness = get_loudness(job_dir / "output.mp4")
    coherence = read_coherence(job_dir)
    subtitle = read_subtitle_summary(job_dir)

    output_segs = reasr_output(job_dir / "output.mp4")
    gaps = detect_gaps(output_segs, durations.get("output") or 0.0)

    speech_seconds = sum((s["end"] - s["start"]) for s in output_segs)
    total_gap_seconds = sum(g["duration"] for g in gaps)
    out_dur = durations.get("output") or 0.0
    silent_ratio = (total_gap_seconds / out_dur) if out_dur else 0.0

    return {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "durations": durations,
        "loudness": loudness,
        "coherence": coherence,
        "subtitle": subtitle,
        "output_segments": output_segs,
        "gaps": gaps,
        "summary": {
            "output_duration_sec": out_dur,
            "speech_seconds": round(speech_seconds, 2),
            "total_gap_seconds": round(total_gap_seconds, 2),
            "silent_ratio": round(silent_ratio, 3),
            "gap_count": len(gaps),
            "verdict_signals": _verdict_signals(out_dur, speech_seconds, gaps, loudness),
        },
    }


def _verdict_signals(out_dur: float, speech: float, gaps: list[dict], loudness: dict | None) -> list[str]:
    """ヒト判定の事前指標を出す（あくまで目安、最終判断はユーザー）。"""
    sigs: list[str] = []
    if loudness:
        if loudness["integrated_lufs"] > -10.0:
            sigs.append("loudness:too_loud")
        elif loudness["integrated_lufs"] < -20.0:
            sigs.append("loudness:too_quiet")
        else:
            sigs.append("loudness:ok")
    if gaps:
        long_gaps = [g for g in gaps if g["duration"] >= 4.0]
        if long_gaps:
            sigs.append(f"gaps:critical({len(long_gaps)}件 4秒超)")
        elif len(gaps) >= 3:
            sigs.append(f"gaps:many({len(gaps)}件)")
        else:
            sigs.append(f"gaps:{len(gaps)}件")
    if out_dur and speech / out_dur < 0.6:
        sigs.append(f"silent_ratio:high({100*(1-speech/out_dur):.0f}%無音)")
    return sigs


def main() -> int:
    parser = argparse.ArgumentParser(description="reel 分析スクリプト")
    parser.add_argument("job_id", nargs="?", help="ジョブID（省略時は最新を自動選択）")
    args = parser.parse_args()

    job_id = args.job_id or find_latest_job()
    if not job_id:
        print(json.dumps({"error": "no job found"}, ensure_ascii=False))
        return 1

    result = analyze(job_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
