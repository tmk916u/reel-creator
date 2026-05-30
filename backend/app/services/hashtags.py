"""ハッシュタグの正規化（要件定義書 §9 / design D9）。

- 各媒体最大 5 個
- スペース区切り・改行区切り・カンマ区切りを受け付ける
- 空白除去 / 先頭 `#` を 1 つに補完 / 重複除去
- 6 個以上はエラー
"""
import re

MAX_HASHTAGS = 5

_SPLIT_RE = re.compile(r"[\s,、，]+")


def normalize_hashtags(raw: str | None) -> str:
    """生入力を正規化して `#a #b` 形式の文字列にして返す。

    6 個を超える場合は ValueError を送出する。
    """
    if not raw or not raw.strip():
        return ""

    seen: set[str] = set()
    tags: list[str] = []
    for token in _SPLIT_RE.split(raw.strip()):
        body = token.lstrip("#").strip()
        if not body:
            continue
        tag = f"#{body}"
        if tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)

    if len(tags) > MAX_HASHTAGS:
        raise ValueError(f"ハッシュタグは最大{MAX_HASHTAGS}個までです（{len(tags)}個指定されました）")

    return " ".join(tags)
