# kuukan SNS自動化ワークフロー

> 最終更新: 2026/02/28  
> 対象: TikTok / Instagram（一木アカウント・お店アカウント）

---

## 概要

kuukanのSNS運用を2つの自動化パイプラインで効率化する。

| | 自動化① | 自動化② |
|---|---|---|
| **内容** | リサーチ → コンテンツカレンダー生成 | 動画編集 → 自動投稿 |
| **トリガー** | 毎週土曜22:00（自動） | 動画完成後（手動） |
| **工数** | ほぼゼロ | 撮影のみ |
| **ステータス** | 🔨 実装中 | 📅 実装予定 |

---

## 自動化①：リサーチ → コンテンツカレンダー生成

### ワークフロー

```
【毎週土曜 22:00 自動起動】

Google Apps Script（無料）
  ↓ スケジュールトリガーで起動
Claude API / Sonnet（有料・月100円以下）
  ↓ kuukan-content-planner Skillを実行
  │
  ├─ Web検索でTikTok/IGトレンドリサーチ
  ├─ kuukanブランド × トレンドでテーマ選定（週3本）
  ├─ 一木アカウント用：フック・台本・カット構成・キャプション・ハッシュタグ生成
  └─ お店アカウント用：画像コンセプト・キャプション・ハッシュタグ生成
  ↓
Google Sheets（無料）
  ↓ コンテンツカレンダーに自動書き込み
LINE Notify（無料）
  └─ 「今週のコンテンツが生成されました」＋スプシURLを通知
```

### Google Sheetsカラム定義

| カラム | 内容 | 例 |
|---|---|---|
| 投稿日 | YYYY/MM/DD | 2026/03/03 |
| アカウント | 一木 / お店 | 一木 |
| プラットフォーム | IG+TikTok / IG | IG+TikTok |
| テーマ | 投稿メインテーマ（20字以内） | 首こりの本当の原因 |
| フック | 冒頭3秒の一言（動画のみ） | 首こりが治らない人、ほぼ全員同じ間違いしてます |
| 台本/内容概要 | 台本全文 or 画像コンセプト | （全文） |
| IGキャプション | Instagram用（200字以内） | 首の痛みの根本は… |
| TikTokキャプション | TikTok用（短め・フック重視） | 首こり持ちは見て |
| ハッシュタグ | スペース区切り | #禅 #整体 #自律神経 |
| ステータス | 進捗管理 | 企画済み |
| 備考 | カット構成・画像指示など | カット1: 正面カメラ 5秒… |

### ステータス定義

```
企画済み → 撮影待ち → 編集中 → 投稿待ち → 投稿済み
```

---

## 自動化②：動画編集 → 自動投稿（実装予定）

### ワークフロー

```
【撮影完了後・手動トリガー】

reel-creator（自作Webアプリ・無料・自己ホスト）
  ↓ localhost:3000 にアクセスして動画アップロード
  ├─ 無音部分の自動削除（FFmpeg）
  └─ AI字幕の自動生成（faster-whisper・日本語対応）
  ↓ 処理済み動画をダウンロード
Google Apps Script（無料）
  ↓ ★追加実装予定
  └─ Google Sheetsから該当投稿のキャプション・ハッシュタグを自動取得
  ↓
  ├─ Instagram Graph API（無料）→ Reels投稿
  └─ TikTok Content Posting API（無料）→ 動画投稿
  ↓
Google Apps Script（無料）
  ↓ スプシのステータスを「投稿待ち」→「投稿済み」に自動更新
LINE Notify（無料）
  └─ 「投稿が完了しました」通知
```

---

## コスト一覧

| ツール | 役割 | 費用 |
|---|---|---|
| Google Apps Script | 自動スケジュール実行・スプシ書き込み・ステータス更新 | **無料** |
| Google Sheets | コンテンツカレンダー管理 | **無料** |
| Claude API（Sonnet） | リサーチ・コンテンツ生成 | **月100円以下** |
| LINE Notify | 完了通知 | **無料** |
| reel-creator | 動画編集（無音削除・字幕） | **無料**（自己ホスト） |
| Instagram Graph API | IG自動投稿 | **無料** |
| TikTok Content Posting API | TikTok自動投稿 | **無料** |

**月額合計：約100円以下**

---

## 2アカウント構成

| アカウント | ID | メインコンテンツ | 投稿先 |
|---|---|---|---|
| お店 | @kuukan_zc | 画像（サロンの世界観・情報） | Instagram |
| 一木（代表） | @ichiki_kuukan | 動画リール（専門知識・人柄） | Instagram / TikTok |

---

## 実装ロードマップ

```
Phase 1（今すぐ）
  ✅ kuukan-content-planner Skill作成
  🔨 Google Apps Script でスケジュール実行
  🔨 Google Sheetsへの自動書き込み
  🔨 LINE Notify通知

Phase 2（Phase 1完成後）
  📅 reel-creatorにIG/TikTok投稿機能を追加
  📅 スプシからキャプションを自動取得して投稿
  📅 ステータス自動更新

Phase 3（将来）
  📅 インサイト（いいね・再生数）をスプシに自動集計
  📅 バズったコンテンツの傾向分析を自動レポート化
```

---

## 関連ファイル

- `docs/skill-design.md` - kuukan-content-planner Skillの設計詳細
- `docs/api-setup.md` - Instagram / TikTok APIのセットアップ手順（Phase 2時に作成）
- `kuukan-content-planner/SKILL.md` - Skill本体（別リポジトリに配置予定）
