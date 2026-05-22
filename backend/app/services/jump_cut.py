# backend/app/services/jump_cut.py
from pathlib import Path

_PUNCTUATION = "、。！？!?."


def load_corrections(path: str | Path | None = None) -> dict[str, str]:
    """同音異義語の置換辞書をロードする。

    Args:
        path: 辞書ファイルのパス。None の場合は backend/app/data/jp_corrections.txt を使用。

    Returns:
        {誤認識: 正解} の dict。ファイルが見つからない場合は空 dict。
    """
    if path is None:
        path = Path(__file__).resolve().parent.parent / "data" / "jp_corrections.txt"
    path = Path(path)

    if not path.exists():
        return {}

    corrections: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "→" in line:
            wrong, right = line.split("→", 1)
            wrong, right = wrong.strip(), right.strip()
            if wrong and right:
                corrections[wrong] = right
    return corrections


def apply_corrections_to_text(text: str, corrections: dict[str, str]) -> str:
    """文字列に対して置換辞書を適用する。"""
    if not corrections:
        return text
    for wrong, right in corrections.items():
        text = text.replace(wrong, right)
    return text


def apply_corrections_to_words(words: list[dict], corrections: dict[str, str]) -> list[dict]:
    """単語リストの text に対して置換辞書を適用する（タイムスタンプは保持）。"""
    if not corrections:
        return words
    return [
        {**w, "text": apply_corrections_to_text(w["text"], corrections)}
        for w in words
    ]


def load_fillers(path: str | Path | None = None) -> set[str]:
    """日本語フィラー辞書をロードする。

    Args:
        path: 辞書ファイルのパス。None の場合は backend/app/data/jp_fillers.txt を使用。

    Returns:
        フィラーワードのセット。ファイルが見つからない場合は空セット。
    """
    if path is None:
        path = Path(__file__).resolve().parent.parent / "data" / "jp_fillers.txt"
    path = Path(path)

    if not path.exists():
        return set()

    words: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.add(line)
    return words


def _normalize(text: str) -> str:
    """フィラー判定用に単語の前後空白と句読点を除去する。"""
    return text.strip().strip(_PUNCTUATION + "　 ")


def detect_filler_ranges(words: list[dict], fillers: set[str]) -> list[dict]:
    """フィラーワードに該当する単語の時間範囲を抽出する。

    Args:
        words: [{"start": float, "end": float, "text": str}, ...]
        fillers: フィラーワードのセット

    Returns:
        [{"start": float, "end": float}, ...] 削除区間リスト
    """
    if not fillers:
        return []

    ranges: list[dict] = []
    for w in words:
        if _normalize(w["text"]) in fillers:
            ranges.append({"start": w["start"], "end": w["end"]})
    return ranges


def detect_tempo_ranges(
    words: list[dict],
    max_pause: float = 0.6,
    target_pause: float = 0.3,
) -> list[dict]:
    """文末の長い間を target_pause まで短縮するための削除区間を作る。

    Args:
        words: word-level transcript
        max_pause: この秒数を超える間を短縮対象とする
        target_pause: 短縮後の残す間（秒）

    Returns:
        削除区間リスト
    """
    ranges: list[dict] = []
    for i in range(len(words) - 1):
        cur = words[i]
        nxt = words[i + 1]
        cur_text = cur["text"].strip()
        if not cur_text or cur_text[-1] not in _PUNCTUATION:
            continue
        # clamp 前の range を使う (clamp された word の後ろは tempo gap と見なさない)
        cur_end_for_gap = cur.get("_orig_end", cur["end"])
        gap = nxt["start"] - cur_end_for_gap
        if gap > max_pause:
            cut_start = cur_end_for_gap + target_pause
            cut_end = nxt["start"]
            if cut_end > cut_start + 0.01:
                ranges.append({"start": cut_start, "end": cut_end})
    return ranges


def detect_oversized_words(
    words: list[dict],
    vad_silences: list[dict],
    max_word_duration: float = 1.0,
    min_cut_length: float = 0.3,
    margin: float = 0.1,
) -> list[dict]:
    """word.end - word.start が異常に長い word の中で、 VAD が「無音」と判定した
    部分だけを削除候補にする。

    ReazonSpeech NeMo の subword は単一点 timestamp で、次の subword までの
    範囲を duration として推定する仕組み。発話の間に長い沈黙(意図的な
    ポーズや言い淀み)があると、前の subword の推定 duration が異常に
    長くなり、word.end が実発話より大幅に後ろにズレる。

    例: 「お」word が 33.06-45.14 (12.08秒) と推定された場合、 word 内には
    「お客様が悩まれているダイエット」という実発話 + 無音が混在している。
    word の中央を一律に削除すると実発話まで切れるため、 silero VAD で
    「無音」と判定された区間だけを削除候補にする。

    Args:
        words: word-level transcript [{"start", "end", "text", ...}]
        vad_silences: silero VAD で検出した無音区間 [{"start", "end"}, ...]
        max_word_duration: この秒数を超える word を対象に (短い word は対象外)
        min_cut_length: word 内 silence がこの秒数未満なら削除しない
        margin: 削除区間の両端に発話保護マージン (秒)

    Returns:
        削除区間リスト
    """
    ranges: list[dict] = []
    for w in words:
        dur = w["end"] - w["start"]
        if dur <= max_word_duration:
            continue
        for s in vad_silences:
            overlap_start = max(s["start"], w["start"]) + margin
            overlap_end = min(s["end"], w["end"]) - margin
            if overlap_end - overlap_start >= min_cut_length:
                ranges.append({"start": overlap_start, "end": overlap_end})
    return merge_ranges(ranges)


def detect_word_gaps(
    words: list[dict],
    max_gap: float = 0.25,
    target_gap: float = 0.10,
) -> list[dict]:
    """word 間のギャップ（無音・鼻啜り音・息継ぎ・考える間など、言葉でない区間）
    を target_gap まで圧縮する削除区間を返す。

    detect_tempo_ranges との違い:
    - 句読点不問。あらゆる word-word 境界が対象。
    - 鼻啜り音や息継ぎ（VAD が弱い人声として検出してしまう音）も、
      ReazonSpeech が text 化しなかった隙間として削除される。

    注意: clamp_oversized_word_ends で短縮された word は `_orig_end` を持つ。
    clamp 前の範囲 [end, _orig_end) は「ASR が認識し損なった発話の可能性が高い」
    区間なので、 ここを word_gap として削除すると本物の発話まで消える。
    gap 計算は `_orig_end` を優先して使う (clamp 後の人工的な隙間を除外)。

    Args:
        words: word-level transcript [{"start", "end", "text", ...}]
        max_gap: この秒数を超える gap を圧縮対象とする
        target_gap: 圧縮後に残す gap（秒）

    Returns:
        削除区間リスト
    """
    ranges: list[dict] = []
    for i in range(len(words) - 1):
        cur = words[i]
        nxt = words[i + 1]
        # clamp 前の range を使う (clamp された word の後ろは gap と見なさない)
        cur_end_for_gap = cur.get("_orig_end", cur["end"])
        gap = nxt["start"] - cur_end_for_gap
        if gap > max_gap:
            cut_start = cur_end_for_gap + target_gap
            cut_end = nxt["start"]
            if cut_end > cut_start + 0.01:
                ranges.append({"start": cut_start, "end": cut_end})
    return ranges


def detect_redundant_speech(
    words: list[dict],
    window_words: int = 10,
    similarity_threshold: float = 0.6,
    min_gap_seconds: float = 3.0,
) -> list[dict]:
    """連続する word チャンク同士のテキスト類似度を見て、繰り返しの 2 回目を
    削除候補にする（LLM の detect_restatements が見逃した重複の機械的補強）。

    話者が同じ内容を別言葉で 2 回話す（例: まとめ部分の再説明）パターンを
    SequenceMatcher.ratio() で検出する。LLM ベースの判定は再現性が低いため、
    機械的なバックアップとして併用する。

    Args:
        words: word-level transcript
        window_words: 比較するチャンクの word 数
        similarity_threshold: 0.0-1.0。この値以上で繰り返しとみなす
        min_gap_seconds: 2 つのチャンクの最小時間ギャップ。直近の言い直しは
            LLM の detect_restatements 側で扱うため、こちらは離れた繰り返し
            （まとめパートなど）に絞る

    Returns:
        削除区間リスト [{"start", "end"}]（後段のチャンクを削除）
    """
    if len(words) < window_words * 2:
        return []

    from difflib import SequenceMatcher

    step = max(1, window_words // 2)
    chunks: list[dict] = []
    for i in range(0, len(words) - window_words + 1, step):
        cw = words[i : i + window_words]
        chunks.append({
            "start": cw[0]["start"],
            "end": cw[-1]["end"],
            "text": "".join(w["text"] for w in cw),
        })

    cuts: list[dict] = []
    consumed: set[int] = set()
    for i, a in enumerate(chunks):
        if i in consumed:
            continue
        for j in range(i + 1, len(chunks)):
            if j in consumed:
                continue
            b = chunks[j]
            if b["start"] < a["end"] + min_gap_seconds:
                continue  # 近すぎる(LLM 担当)
            sim = SequenceMatcher(None, a["text"], b["text"]).ratio()
            if sim >= similarity_threshold:
                cuts.append({"start": b["start"], "end": b["end"]})
                consumed.add(j)
    return cuts


def merge_ranges(ranges: list[dict], join_threshold: float = 0.05) -> list[dict]:
    """重複・隣接する削除区間を統合する。

    Args:
        ranges: 削除区間リスト
        join_threshold: この秒数以下のギャップは連結する

    Returns:
        マージ済み削除区間リスト（start 昇順）
    """
    if not ranges:
        return []

    sorted_ranges = sorted(ranges, key=lambda r: r["start"])
    merged: list[dict] = [dict(sorted_ranges[0])]

    for r in sorted_ranges[1:]:
        last = merged[-1]
        if r["start"] <= last["end"] + join_threshold:
            last["end"] = max(last["end"], r["end"])
        else:
            merged.append(dict(r))

    return [{"start": round(r["start"], 3), "end": round(r["end"], 3)} for r in merged]
