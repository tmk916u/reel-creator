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
        gap = nxt["start"] - cur["end"]
        if gap > max_pause:
            cut_start = cur["end"] + target_pause
            cut_end = nxt["start"]
            if cut_end > cut_start + 0.01:
                ranges.append({"start": cut_start, "end": cut_end})
    return ranges


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
