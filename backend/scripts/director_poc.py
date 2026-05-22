#!/usr/bin/env python3
"""LLM Director PoC.

既存ジョブの transcript を読み、 LLM に「リール用に残す clips」 を返させる。
出力 clips を ffmpeg で切り貼りして PoC output 動画を生成する。

OpenSpec: llm-director-editor Phase 0

使い方:
    docker exec reel-creator-backend-1 python /app/scripts/director_poc.py <job_id>
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

TMP_DIR = Path("/app/tmp")

DIRECTOR_SYSTEM_PROMPT = """\
あなたは TikTok/Instagram Reels の動画編集 AI ディレクターです。
整体院の話者が話す動画 transcript を読み、 50〜80 秒の縦動画リールに
再構成してください。

**重要なルール**:
- 動画の時系列を入れ替えてはいけない (input transcript の出現順を維持)
- 合計尺は **最低 50 秒、 目標 60 秒以上**
- 元 transcript から「残すべき区間」 を選び、 順番はそのまま

削除すべき発話:
- 言い直し、 噛み、 フィラー (「えー」「あの」)
- 同じ内容の繰り返し (冒頭で「お客様が悩まれている」 を 2 回言っている等は 1 回だけ残す)
- 結論につながらない雑談
- 長い間 (3 秒以上の無発話)

残すべき発話:
- 結論・主張 (「一番大事なのは○○」)
- 理由・根拠 ・具体例
- 締めくくり・行動喚起

返り値は **必ず JSON** で、 transcript 内の時刻範囲を指定すること。
範囲外の時刻や、 transcript にない発話を含めてはいけない。

出力 JSON 形式:
{
  "clips": [
    {
      "start": <float, transcript 内の開始時刻 (秒)>,
      "end": <float, transcript 内の終了時刻 (秒, start より大)>,
      "role": "intro" | "main" | "supplement" | "cta",
      "text": "<該当区間の発話の要約>"
    },
    ...
  ],
  "summary": "全体の構成意図を 1 文で"
}

注意:
- clips は time-sorted (start が小さい順) で並んでいなければならない
- 順序入れ替えなし
- clips の合計尺 (Σ end-start) は 50〜80 秒
- 50 秒未満なら追加で残すべき発話を含めて伸ばすこと
"""


def load_transcript(job_id: str) -> tuple[list[dict], list[dict], float]:
    """transcript.json と diagnostics.json から segments + words + duration を取得"""
    job_dir = TMP_DIR / job_id
    tr = json.loads((job_dir / "transcript.json").read_text(encoding="utf-8"))
    segments = tr.get("segments") or []
    words = tr.get("words") or []
    # duration は diagnostics.json から取得 (なければ ffprobe)
    diag_path = job_dir / "diagnostics.json"
    if diag_path.exists():
        duration = json.loads(diag_path.read_text())["input_duration"]
    else:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(job_dir / "input.mp4")],
            capture_output=True, text=True,
        )
        duration = float(r.stdout.strip())
    return segments, words, duration


def format_transcript_for_prompt(segments: list[dict]) -> str:
    """segment list を LLM 入力用に整形"""
    lines = []
    for i, s in enumerate(segments, 1):
        lines.append(f"{i}. [{s['start']:.2f}-{s['end']:.2f}] {s['text']}")
    return "\n".join(lines)


def call_director_llm(transcript_text: str, duration: float) -> dict:
    """LLM に director プロンプトを投げて clips dict を取得"""
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()

    user_prompt = (
        f"動画の総尺: {duration:.1f} 秒\n"
        f"目標尺: 40〜80 秒のリール\n\n"
        f"以下が transcript です (segment 単位、 時刻付き):\n\n"
        f"{transcript_text}\n\n"
        f"上記から、 リール構造に従って残すべき clips を JSON で返してください。"
    )

    if provider == "openai":
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            temperature=0,
            messages=[
                {"role": "system", "content": DIRECTOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = resp.choices[0].message.content or "{}"
    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            temperature=0,
            system=DIRECTOR_SYSTEM_PROMPT + "\n\n応答は JSON オブジェクトのみで返してください。",
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = ""
        for block in resp.content:
            if hasattr(block, "text"):
                raw += block.text
    else:
        raise RuntimeError(f"Unknown LLM_PROVIDER: {provider}")

    # JSON 抽出
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    return json.loads(raw)


def validate_clips(clips: list[dict], duration: float) -> list[dict]:
    """範囲外や不正な clip を破棄"""
    valid = []
    for c in clips:
        try:
            start = float(c["start"])
            end = float(c["end"])
            role = c.get("role")
            order = int(c.get("order", 0))
        except (KeyError, ValueError, TypeError) as e:
            print(f"[WARN] clip 破棄 (parse error: {e}): {c}", file=sys.stderr)
            continue
        if start < 0 or end > duration + 0.5 or start >= end:
            print(f"[WARN] clip 破棄 (range): start={start} end={end} dur={duration}", file=sys.stderr)
            continue
        if role not in ("intro", "main", "supplement", "cta", "hook", "reason", "example"):
            print(f"[WARN] clip 破棄 (role): {role}", file=sys.stderr)
            continue
        valid.append({"start": start, "end": end, "role": role, "order": order,
                      "text": c.get("text", "")})
    # 時系列順を強制 (LLM が順序入れ替えを返してきても、 ここで sort して時系列順に)
    valid.sort(key=lambda c: c["start"])
    # order を 1-indexed で振り直す
    for i, c in enumerate(valid, 1):
        c["order"] = i
    return valid


def cut_video(job_id: str, clips: list[dict], output_name: str = "director_output.mp4") -> Path:
    """clips を order 順に並べて ffmpeg で切り貼り"""
    job_dir = TMP_DIR / job_id
    input_mp4 = job_dir / "input.mp4"
    out_path = job_dir / output_name
    ordered = sorted(clips, key=lambda c: c["order"])

    # 各 clip を別ファイルに切り出してから concat
    tmp_dir = job_dir / "_director_clips"
    tmp_dir.mkdir(exist_ok=True)
    clip_files = []
    for i, c in enumerate(ordered):
        clip_path = tmp_dir / f"clip_{i:03d}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(c["start"]), "-to", str(c["end"]),
            "-i", str(input_mp4),
            "-c:v", "libx264", "-c:a", "aac", "-preset", "fast",
            str(clip_path),
        ], check=True)
        clip_files.append(clip_path)

    # concat
    concat_list = tmp_dir / "concat.txt"
    concat_list.write_text("\n".join(f"file '{p}'" for p in clip_files), encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(out_path),
    ], check=True)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM Director PoC")
    parser.add_argument("job_id", help="既存ジョブ ID")
    parser.add_argument("--cut", action="store_true", help="ffmpeg で切り貼り動画も生成")
    args = parser.parse_args()

    segments, _words, duration = load_transcript(args.job_id)
    if not segments:
        print(f"ERROR: job {args.job_id} に segments がない")
        return 1

    print(f"=== Input ===")
    print(f"job: {args.job_id}")
    print(f"duration: {duration:.2f}s, segments: {len(segments)}")

    transcript_text = format_transcript_for_prompt(segments)
    t0 = time.time()
    result = call_director_llm(transcript_text, duration)
    elapsed = time.time() - t0
    print(f"\n=== LLM response (elapsed {elapsed:.1f}s) ===")
    print(f"summary: {result.get('summary', '(none)')}")

    raw_clips = result.get("clips") or []
    print(f"raw clips: {len(raw_clips)}")
    clips = validate_clips(raw_clips, duration)
    print(f"valid clips: {len(clips)}")

    print("\n=== Clips (order 順) ===")
    total = 0.0
    for c in sorted(clips, key=lambda x: x["order"]):
        dur = c["end"] - c["start"]
        total += dur
        print(f"  #{c['order']} [{c['role']:7s}] {c['start']:6.2f}-{c['end']:6.2f} ({dur:5.2f}s): {c['text'][:50]}")
    print(f"\ntotal output duration: {total:.2f}s")

    if args.cut and clips:
        print("\n=== Cutting video ===")
        out_path = cut_video(args.job_id, clips)
        print(f"output: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
