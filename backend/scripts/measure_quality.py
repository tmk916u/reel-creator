#!/usr/bin/env python3
"""業務量産品質ライン (14項目) の機械測定スクリプト。

使い方:
    python backend/scripts/measure_quality.py <job_id>
    python backend/scripts/measure_quality.py /app/tmp/<job_id>

出力:
    <job_dir>/quality_report.json - 機械測定結果
    <job_dir>/quality_report.md   - 目視チェックリスト + 機械測定サマリ

仕様: openspec/specs/quality-line/spec.md
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

TRAILING_PARTICLES = set("はがをにでとのもへやかな")
DIALOGUE_RE = re.compile(
    r"^Dialogue:\s*\d+,([\d:.]+),([\d:.]+),[^,]*,[^,]*,\d+,\d+,\d+,[^,]*,(.*)$"
)
ASS_TAG_RE = re.compile(r"\{[^}]*\}")

# 業務量産品質ライン 合格しきい値
VIDEO_DURATION_RANGE = (60.0, 120.0)
TIMING_DIFF_MAX = 0.5
PARTICLE_TRAIL_MAX_RATIO = 0.10
SUBTITLE_CHARS_RANGE = (8, 14)
SUBTITLE_CHARS_TARGET_RATIO = 0.70
PROCESSING_TIME_MAX = 600.0


def ffprobe_duration(path: Path) -> float:
    """ffprobe で動画の duration (秒) を返す。"""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nokey=1", str(path)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return 0.0
    try:
        return float(result.stdout.strip())
    except (TypeError, ValueError):
        return 0.0


def parse_ass_dialogues(ass_path: Path) -> list[dict[str, Any]]:
    """ASS から Dialogue 行を抽出。"""
    if not ass_path.exists():
        return []
    dialogues: list[dict[str, Any]] = []
    for line in ass_path.read_text(encoding="utf-8").splitlines():
        m = DIALOGUE_RE.match(line)
        if not m:
            continue
        start, end, text = m.group(1), m.group(2), m.group(3)
        clean_text = ASS_TAG_RE.sub("", text).strip()
        dialogues.append({
            "start": _parse_ass_time(start),
            "end": _parse_ass_time(end),
            "text": clean_text,
        })
    return dialogues


def _parse_ass_time(s: str) -> float:
    """ASS の H:MM:SS.cs を秒に。"""
    try:
        parts = s.split(":")
        if len(parts) == 3:
            h, m, sec = parts
            return int(h) * 3600 + int(m) * 60 + float(sec)
        return float(s)
    except (ValueError, IndexError):
        return 0.0


def measure_4_duration(out_path: Path) -> dict[str, Any]:
    """項目#4 動画長 (60-120秒)。"""
    dur = ffprobe_duration(out_path)
    lo, hi = VIDEO_DURATION_RANGE
    return {
        "item": 4,
        "name": "出力動画長 60-120 秒",
        "value": round(dur, 2),
        "range": [lo, hi],
        "pass": lo <= dur <= hi,
    }


def measure_6_timing_sync(dialogues: list[dict], words: list[dict]) -> dict[str, Any]:
    """項目#6 字幕タイミング同期 (差 < 0.5秒)。

    各 Dialogue の開始時刻と、 同じ時刻帯にある word.start を比較。
    """
    if not dialogues or not words:
        return {"item": 6, "name": "字幕タイミング同期", "pass": False, "reason": "no data"}

    bad = 0
    samples = []
    for d in dialogues[:30]:
        # d.start に最も近い word を探す
        closest = min(words, key=lambda w: abs(w["start"] - d["start"]))
        diff = abs(closest["start"] - d["start"])
        samples.append({"d_start": d["start"], "w_start": closest["start"], "diff": round(diff, 3)})
        if diff > TIMING_DIFF_MAX:
            bad += 1
    return {
        "item": 6,
        "name": "字幕タイミング同期 (差 < 0.5秒)",
        "bad_count": bad,
        "samples": samples[:5],
        "pass": bad == 0,
    }


def measure_7_particle_trail(dialogues: list[dict]) -> dict[str, Any]:
    """項目#7 助詞直後で切れる Dialogue が 10% 以下か。"""
    if not dialogues:
        return {"item": 7, "name": "助詞直後flush", "pass": False, "reason": "no dialogues"}

    bad: list[str] = []
    for d in dialogues:
        text = d["text"].strip().rstrip("、。!?！?")
        if text and text[-1] in TRAILING_PARTICLES:
            bad.append(d["text"])
    ratio = len(bad) / len(dialogues)
    return {
        "item": 7,
        "name": "助詞直後で切れる Dialogue < 10%",
        "total": len(dialogues),
        "bad_count": len(bad),
        "ratio": round(ratio, 3),
        "examples": bad[:5],
        "pass": ratio <= PARTICLE_TRAIL_MAX_RATIO,
    }


def measure_8_subtitle_length(dialogues: list[dict]) -> dict[str, Any]:
    """項目#8 字幕文字数 8-14 が 70% 以上。"""
    if not dialogues:
        return {"item": 8, "name": "字幕文字数", "pass": False, "reason": "no dialogues"}
    lo, hi = SUBTITLE_CHARS_RANGE
    in_range = sum(1 for d in dialogues if lo <= len(d["text"]) <= hi)
    ratio = in_range / len(dialogues)
    lengths = [len(d["text"]) for d in dialogues]
    return {
        "item": 8,
        "name": f"字幕文字数 {lo}-{hi} 文字が {int(SUBTITLE_CHARS_TARGET_RATIO * 100)}% 以上",
        "total": len(dialogues),
        "in_range": in_range,
        "ratio": round(ratio, 3),
        "min_len": min(lengths) if lengths else 0,
        "max_len": max(lengths) if lengths else 0,
        "avg_len": round(sum(lengths) / len(lengths), 1) if lengths else 0,
        "pass": ratio >= SUBTITLE_CHARS_TARGET_RATIO,
    }


def measure_11_cta_tofu(cta_path: Path) -> dict[str, Any]:
    """項目#11 CTA テキストの絵文字豆腐 (フォント非対応文字) 検出。

    Noto Sans CJK JP の主要範囲: ASCII, ひらがな, カタカナ, CJK統合漢字, JIS記号
    """
    if not cta_path.exists():
        return {"item": 11, "name": "CTA 豆腐", "pass": False, "reason": "no cta.txt"}

    text = cta_path.read_text(encoding="utf-8").strip()
    suspicious: list[str] = []
    for ch in text:
        code = ord(ch)
        # 絵文字レンジ (Noto Sans CJK JP 非対応の主要範囲)
        if (
            0x1F300 <= code <= 0x1F9FF or  # emoji
            0x2600 <= code <= 0x27BF or    # misc symbols & dingbats (含む 👇 系の前段)
            0x1F600 <= code <= 0x1F64F or  # emoticons
            code == 0x1F447                # 👇 finger
        ):
            suspicious.append(f"U+{code:04X}({ch})")
    return {
        "item": 11,
        "name": "CTA に絵文字豆腐リスクなし",
        "text": text,
        "suspicious_chars": suspicious,
        "pass": len(suspicious) == 0,
    }


def measure_14_processing_time(job_dir: Path) -> dict[str, Any]:
    """項目#14 処理時間 (input.mp4 と output.mp4 のファイル mtime 差)。

    厳密ではないが、 ベースラインの参考値として使う。
    """
    input_p = job_dir / "input.mp4"
    output_p = job_dir / "output.mp4"
    if not input_p.exists() or not output_p.exists():
        return {"item": 14, "name": "処理時間", "pass": False, "reason": "no files"}
    diff = output_p.stat().st_mtime - input_p.stat().st_mtime
    return {
        "item": 14,
        "name": f"処理時間 < {int(PROCESSING_TIME_MAX)} 秒",
        "value": round(diff, 1),
        "pass": diff <= PROCESSING_TIME_MAX,
    }


def measure_machine(job_dir: Path) -> dict[str, Any]:
    """機械測定可能な項目をまとめて算出。"""
    output = job_dir / "output.mp4"
    ass = job_dir / "subtitles.ass"
    transcript = job_dir / "transcript.json"
    cta = job_dir / "cta.txt"

    dialogues = parse_ass_dialogues(ass)
    words: list[dict] = []
    if transcript.exists():
        try:
            data = json.loads(transcript.read_text(encoding="utf-8"))
            words = data.get("words", [])
        except json.JSONDecodeError:
            pass

    return {
        "job_dir": str(job_dir),
        "measurements": [
            measure_4_duration(output),
            measure_6_timing_sync(dialogues, words),
            measure_7_particle_trail(dialogues),
            measure_8_subtitle_length(dialogues),
            measure_11_cta_tofu(cta),
            measure_14_processing_time(job_dir),
        ],
    }


def visual_checklist_template(job_dir: Path) -> str:
    """目視判定が必要な項目のチェックリスト Markdown を返す。"""
    return f"""# 業務量産品質ライン 目視チェック - {job_dir.name}

下記項目を **目視で** 確認し、 ☑ or ☒ を付ける。

## ストーリー・発話保護

- [ ] **#1 ストーリーの保全**
      期待値ドキュメント `*.expected.md` の「動画の主張」と整合する内容が出力字幕にある
- [ ] **#2 冒頭・末尾の発話保護**
      期待値ドキュメントの「残るべき発話キーワード」がすべて出力字幕に出現
- [ ] **#3 無駄な余白の除去**
      フィラー(えーっと/あの/まあ等)が 80% 以上削除されている

## 字幕品質

- [ ] **#5 字幕の誤認識**
      期待値ドキュメントの「想定誤認識パターン」以外の誤認識が 1 件以下

## テロップ品質

- [ ] **#9 HOOK の的確さ**
      `{job_dir.name}/hook.txt` が動画の核心を表現している(言葉遊びで空振りしていない)
- [ ] **#10 テロップが被写体を隠さない**
      output.mp4 を再生して、 HOOK/CTA/トピックラベルが顔を覆ったり画面端からはみ出していない
- [ ] **#12 トピックラベル**
      `{job_dir.name}/topic_label_*.txt` が動画の構成を表現している

## 業務量産観点

- [ ] **#13 編集不要**
      skip_preview=true で処理した output.mp4 が編集なしで投稿可能なクオリティ

---

判定日: ____ / 判定者: ____

## メモ
<不合格項目の具体的な状況を記録>
"""


def render_markdown(machine: dict[str, Any], job_dir: Path) -> str:
    """機械測定結果 + 目視チェックリストを Markdown に。"""
    lines = [
        f"# 業務量産品質測定レポート - {job_dir.name}",
        "",
        "## 機械測定結果",
        "",
        "| 項目# | 名前 | 結果 | 詳細 |",
        "|------|------|------|------|",
    ]
    for m in machine["measurements"]:
        result = "✅" if m.get("pass") else "❌"
        detail_parts = []
        for k in ("value", "ratio", "bad_count", "in_range", "total", "text", "suspicious_chars"):
            if k in m and m[k] not in (None, "", []):
                detail_parts.append(f"{k}={m[k]}")
        detail = ", ".join(detail_parts) or "-"
        lines.append(f"| #{m['item']} | {m['name']} | {result} | {detail} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(visual_checklist_template(job_dir))
    return "\n".join(lines)


def resolve_job_dir(arg: str) -> Path:
    """引数を job_dir Path に解決。 job_id だけでも /app/tmp/<id> でも OK。"""
    p = Path(arg)
    if p.is_dir():
        return p
    # Try Docker container path / local backend tmp
    for prefix in ("/app/tmp", "backend/tmp"):
        candidate = Path(prefix) / arg
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"job_dir not found for: {arg}")


def main() -> int:
    parser = argparse.ArgumentParser(description="業務量産品質ライン測定スクリプト")
    parser.add_argument("job", help="job_id or job_dir path")
    parser.add_argument("--out-json", help="JSON 出力先 (default: <job_dir>/quality_report.json)")
    parser.add_argument("--out-md", help="Markdown 出力先 (default: <job_dir>/quality_report.md)")
    parser.add_argument("--print-only", action="store_true", help="ファイル書き込みせず標準出力のみ")
    args = parser.parse_args()

    try:
        job_dir = resolve_job_dir(args.job)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    machine = measure_machine(job_dir)
    md = render_markdown(machine, job_dir)

    if args.print_only:
        print(json.dumps(machine, ensure_ascii=False, indent=2))
        print()
        print(md)
        return 0

    out_json = Path(args.out_json) if args.out_json else (job_dir / "quality_report.json")
    out_md = Path(args.out_md) if args.out_md else (job_dir / "quality_report.md")
    out_json.write_text(json.dumps(machine, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(md, encoding="utf-8")
    print(f"Wrote: {out_json}")
    print(f"Wrote: {out_md}")

    # サマリを stderr に
    passed = sum(1 for m in machine["measurements"] if m.get("pass"))
    total = len(machine["measurements"])
    print(f"機械測定: {passed}/{total} 合格", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
