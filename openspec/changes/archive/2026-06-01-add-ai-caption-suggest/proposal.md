## Why

`social-publishing`（Phase 1〜4）で予約投稿の基盤は完成したが、**毎回キャプション・タイトル・説明文・ハッシュタグを手書きする**のは運用負担が大きい。1 日 1 動画ペースでも累積する。

要件定義書 §12 で言及されていた「AI キャプション生成」は当初 Non-Goal だったが、Phase 1〜4 が動いた今、次に取り組む価値が最も高い。理由:

1. **既存資産で安く実現できる**: ASR は `services/asr.py`（ReazonSpeech、ローカル実行・無料）、LLM は `services/llm.py`（Anthropic Claude、編集機能で稼働中）が揃っている
2. **コスト試算**: 1 動画 $0.01〜0.03 / 月 ~$1 以下（Anthropic）
3. **UX 効果が大きい**: 動画の音声から「テーマに沿ったキャプション」が自動で出てくると、運用がほぼワンクリックになる
4. **サムネ案も同時に出せる**: カバー文字（短いキャッチコピー 1〜3 案）も生成可能。TikTok/Edits で動画にテキスト合成する現状ワークフローと併用しやすい

## What Changes

`social-publishing` に AI キャプション生成機能を追加する。動画アップロード後の `/post/new` 画面で「✨ AI でキャプション生成」ボタンを押すと、書き起こし → LLM 要約 → フォーム各欄にサジェスト、というフロー。

### Backend
- `app/services/captions_ai.py`（新規）:
  - 動画ファイルから音声抽出 → ReazonSpeech で書き起こし
  - 書き起こし + テーマ（任意）を Anthropic Claude に渡して構造化 JSON で生成
  - 出力: `instagram_caption / youtube_title / youtube_description / hashtags / cover_text_candidates`
- `app/routers/posts.py` に追加:
  - `POST /api/posts/{video_id}/suggest` → `CaptionSuggestionResponse`
- `app/models/schemas.py` に `CaptionSuggestionResponse` 追加

### Frontend
- `/post/new` ページに「**✨ AI でキャプション生成**」ボタン（動画アップロード後に表示）
- 押下 → ローディング（書き起こし + LLM で 10〜60 秒）→ サジェスト結果を IG キャプション / YT タイトル / YT 説明文 / ハッシュタグ 各欄に流し込む
- 「**カバー文字案**」セクションを新設、3 案を表示（コピペ用、TikTok/Edits で使う）
- ユーザーは自由に編集可能。再生成ボタンで何度でも生成可

### Out of Scope（将来別 change）
- サムネ画像の自動生成（フレーム抽出 + カバー文字オーバーレイ合成）
- IG Reels の `thumb_offset` 自動選択（「いい瞬間」検出）
- バズスコア再計算 / テンプレート機能

- BREAKING: なし（既存 `social-publishing` capability に ADDED Requirements として追加するのみ）

## Capabilities

### Modified Capabilities
- `social-publishing`: 動画アップロード後の AI キャプション生成（ADDED Requirements）

## Impact

- **Backend**:
  - 新規 `services/captions_ai.py`（~100 行）
  - `routers/posts.py` に 1 エンドポイント追加
  - `models/schemas.py` に 1 レスポンス型追加
  - 既存 `services/asr.py` / `services/llm.py` を流用（変更なし）
- **Frontend**:
  - `/post/new` に AI ボタン + サジェスト UI 追加（~100 行 TSX）
  - `lib/api.ts` に `suggestCaptions` 追加
- **テスト**: LLM mock + ASR mock で単体テスト 5〜8 件追加
- **処理時間**: 60 秒前後（書き起こし + LLM）。ローディング UI で吸収
- **LLM コスト**: 1 動画 $0.01〜0.03（書き起こし 5000 tokens + 出力 500 tokens 程度）
- **既存挙動**: 影響なし（新エンドポイント追加・既存フローは温存）
