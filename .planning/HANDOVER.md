# 引き継ぎノート（2026-05-15）

## このセッションでの主な変更

### コミット済み
- `e8cc654` perf: ffmpeg多重再エンコードを1パスに統合・Whisperモデルキャッシュ・AIキャプション/バズスコア機能追加
- `6e2e400` feat: バズ最大化機能を追加（モーション字幕・キーワード強調・冒頭フック・CTA・数字オーバーレイ・BGM）

### 未コミット（今セッション後半）
- **単語境界スナップ** (`snap_silences_to_word_boundaries` in vad.py) — 単語の中でカットしないよう補正
- **字幕の意訳モード** — LLM プロンプトを保守的→積極的に書き換え（`_CORRECTION_SYSTEM_PROMPT`）
- **重複話の検出強化** — `_SYSTEM_PROMPT` を更新（同じ話の二回目を検出）
- **空白削減パラメータ調整:**
  - `min_silence_duration`: 0.5 → 0.3
  - `padding`: 0.08 → 0.04
  - `tempo_max_pause`: 0.8 → 0.6
  - `audio_fade`: 0.04 → 0.08
- **dedup/merge強化** — words_to_segments の post-processing で重複削除と短セグメント統合
- **transcribe filter** — 字幕プレビューで cut される region のワードを除外
- **transcript.json 永続化** — `/api/captions`, `/api/buzz-score` が再起動後も使えるように
- **UI/UX polish** — グラデーション・スピナー・点滅 CTA・進捗時間予測

## 現在の状態

- バックエンドは動作中（faster-whisper-medium にフォールバック）
- **WhisperX が起動失敗中** — `typing.Any` は対応済み、まだ他の safe_globals エラーで失敗の可能性
- ReazonSpeech は未統合

## 次セッションでやること（決定済み）

### 🎯 Goal: ReazonSpeech 統合

**理由:** Whisper の日本語精度の限界に対処してきた「dedup / merge / snap / 辞書」の後処理ループから卒業する。日本語特化の OSS ASR を使えば根本解決。

**実装計画:**

1. **依存追加** — `reazonspeech` をrequirements.txt に
   - 主要パッケージ: `reazonspeech-nemo-asr` or `reazonspeech-espnet-asr`
   - 公式: https://research.reazon.jp/projects/ReazonSpeech/
   - GitHub: https://github.com/reazon-research/ReazonSpeech

2. **アダプタ作成** — `app/services/asr.py`
   - 既存の `transcribe_with_words(audio_path, initial_prompt, model_size)` と同じインターフェース
   - 返り値: `(words: list[dict], segments: list[dict])` (`{start, end, text}` 形式)
   - 3段階フォールバック: ReazonSpeech → WhisperX → faster-whisper

3. **subtitle.py を改修**
   - `_transcribe_with_reazonspeech()` を追加
   - 既存の `transcribe_with_words` の優先順序を変更

4. **テスト**
   - 実動画で精度比較
   - ログで時間計測
   - 既存 49 テストが通ることを確認

5. **不要な後処理を整理（オプション、効果確認後）**
   - dedup / merge / snap が ReazonSpeech で不要になれば、コードを削除して簡潔化

**工数:** 半日〜1日

## 差別化軸（決定済み）

**日本語特化 AI リール生成ツール**

- ターゲット: 日本語ネイティブクリエイター
- 競合: Submagic (英語ファースト)
- 武器: ReazonSpeech + 日本語特化辞書 + LLM 校正

## アプリの現状サマリー（コードベース）

```
backend/
  app/
    config.py             # パラメータ集中管理（環境変数オーバーライド可）
    main.py               # FastAPI エントリ
    models/schemas.py     # Pydantic スキーマ
    routers/
      video.py            # /api/upload, /transcribe, /process, /captions, /buzz-score 等
      publish.py          # SNS 自動投稿（Instagram/TikTok）
    services/
      ffmpeg.py           # cut_and_concat, apply_pipeline_combined, mix_bgm 等
      subtitle.py         # transcribe_with_words, words_to_segments, segments_to_ass
      silence.py          # compute_voice_segments
      vad.py              # detect_silence_silero, snap_silences_to_word_boundaries
      jump_cut.py         # detect_filler_ranges, detect_tempo_ranges, merge_ranges
      llm.py              # LLM 関連: correct/keywords/hook/topics/captions/buzz_score
      google_sheets.py    # シート連携
      instagram.py, tiktok.py # SNS 投稿
    data/
      jp_corrections.txt  # 誤認識置換辞書
      jp_fillers.txt      # フィラー辞書
      bgm/                # BGM ファイル配置先（未配置）
      sfx/                # 効果音配置先（未配置）

frontend/
  app/page.tsx            # 5ステップウィザード（upload→settings→preview→processing→done）
  components/
    VideoUploader.tsx     # ドラッグ&ドロップアップロード
    ProcessingPanel.tsx   # プリセット + 詳細設定
    TranscriptEditor.tsx  # 字幕プレビュー＆編集
    ProgressView.tsx      # 進捗 + 残り時間予測
    DownloadPanel.tsx     # 完了画面 + バズスコア + キャプション生成
  lib/api.ts              # API クライアント
```

## 次セッション開始時の最初のプロンプト案

```
HANDOVER.md を読んで、ReazonSpeech の統合作業を始めて。
公式ドキュメントを WebFetch で確認して、依存と実装計画を立ててから着手して。
既存のテスト 49 件は全部通ること。
```
