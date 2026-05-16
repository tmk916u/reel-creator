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


def detect_oversized_words(
    words: list[dict],
    max_word_duration: float = 1.0,
    keep_head: float = 0.2,
    keep_tail: float = 0.2,
) -> list[dict]:
    """word.end - word.start が異常に長い word の中央部を削除候補にする。

    ReazonSpeech NeMo の subword は単一点 timestamp で、次の subword までの
    範囲を duration として推定する仕組み。発話の間に長い沈黙(意図的な
    ポーズや言い淀み)があると、前の subword の推定 duration が異常に
    長くなり、word.end が実発話より大幅に後ろにズレる。

    例: 「きて」(36.94-37.18) → 「首」(37.18-41.42, 4.24秒!) の場合、
    「首」word の中に約4秒の無音が埋もれている。これを keep_head/keep_tail
    だけ残して中央を削除する。

    Args:
        words: word-level transcript [{"start", "end", "text", ...}]
        max_word_duration: この秒数を超える word を対象に
        keep_head: 削除区間の前に残す秒数(word 開始から)
        keep_tail: 削除区間の後に残す秒数(word 終端まで)

    Returns:
        削除区間リスト
    """
    ranges: list[dict] = []
    for w in words:
        dur = w["end"] - w["start"]
        if dur > max_word_duration:
            cut_start = w["start"] + keep_head
            cut_end = w["end"] - keep_tail
            if cut_end > cut_start + 0.05:
                ranges.append({"start": cut_start, "end": cut_end})
    return ranges


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
        gap = nxt["start"] - cur["end"]
        if gap > max_gap:
            cut_start = cur["end"] + target_gap
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
