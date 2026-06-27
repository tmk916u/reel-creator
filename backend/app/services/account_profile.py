"""アカウント文脈プロファイル（account-context-profile）のサービス層。

build_caption_system_prompt はプロファイル辞書から AI キャプション生成用の
システムプロンプトを組み立てる純粋関数（I/O なし）でユニットテスト可能。
get_or_create_active は単一プロファイルを取得 or 作成する。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.db_models import AccountProfile

# プロファイル未設定時のフォールバック領域（従来のハードコード値）
_DEFAULT_NICHE = "整体院 / ヘルスケア領域"

_FIELDS = ("niche", "target_audience", "tone", "goals", "hashtags", "ng_words", "notes")


def build_caption_system_prompt(profile: dict | None) -> str:
    """プロファイルから AI キャプション生成のシステムプロンプトを組み立てる（純粋関数）。

    profile が None / 空なら従来のデフォルト領域にフォールバックする。
    """
    p = profile or {}
    niche = (p.get("niche") or "").strip() or _DEFAULT_NICHE

    lines = [
        "あなたは TikTok / Instagram Reels / YouTube Shorts 向けの SNS 運用アシスタントです。",
        f"{niche} のリール動画の音声書き起こしを読み、各媒体に最適化された",
        "キャプション・タイトル・説明文・ハッシュタグ・カバー文字案を生成してください。",
    ]

    ctx: list[str] = []
    target = (p.get("target_audience") or "").strip()
    tone = (p.get("tone") or "").strip()
    goals = (p.get("goals") or "").strip()
    hashtags = (p.get("hashtags") or "").strip()
    ng_words = (p.get("ng_words") or "").strip()
    notes = (p.get("notes") or "").strip()

    if target:
        ctx.append(f"- ターゲット視聴者: {target}")
    if tone:
        ctx.append(f"- トーン/語り口: {tone}")
    if goals:
        ctx.append(f"- 運用目的: {goals}")
    if hashtags:
        ctx.append(f"- 定番ハッシュタグ（優先的に活用）: {hashtags}")
    if ng_words:
        ctx.append(f"- 避ける語/表現（使用禁止）: {ng_words}")
    if notes:
        ctx.append(f"- 補足: {notes}")

    if ctx:
        lines.append("")
        lines.append("【アカウント文脈】このアカウントの性質に合わせて生成してください。")
        lines.extend(ctx)

    lines.extend([
        "",
        "スタイル指針:",
        "- instagram_caption: 親近感のあるトーン、適度に絵文字、ハッシュタグは含めない、200 文字以内",
        "- youtube_title: クリック率を意識した訴求、70 文字以内",
        "- youtube_description: SEO を意識、結論→詳細→CTA の構造、500 文字以内、末尾にハッシュタグを並べる",
        "- hashtags: 5 個、`#` 付き、各媒体共通で使えるもの",
        "- cover_text_candidates: 3 案、各 7〜12 文字以内、強い訴求、リール冒頭の大きな文字を想定",
        "",
        "応答は必ず以下の JSON オブジェクトのみで返してください。前後にテキストを付けないでください。",
        "",
        "{",
        '  "instagram_caption": "...",',
        '  "youtube_title": "...",',
        '  "youtube_description": "...",',
        '  "hashtags": ["#xxx", "#yyy", "#zzz", "#aaa", "#bbb"],',
        '  "cover_text_candidates": ["案1", "案2", "案3"]',
        "}",
    ])
    return "\n".join(lines)


def profile_to_dict(profile: AccountProfile) -> dict:
    """ORM モデルをプロンプト組立用の辞書に変換する。"""
    return {f: getattr(profile, f) for f in _FIELDS}


def get_or_create_active(db: Session) -> AccountProfile:
    """アクティブな単一プロファイルを取得。無ければ空で作成する。"""
    profile = db.scalars(
        select(AccountProfile).where(AccountProfile.is_active.is_(True)).limit(1)
    ).first()
    if profile is None:
        profile = AccountProfile(is_active=True)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile
