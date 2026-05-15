# 引き継ぎノート（2026-05-15 更新）

## このセッションでの主な変更

### コミット済み
- `5f3633a` feat: ReazonSpeech統合・3段ASRフォールバック(ReazonSpeech→WhisperX→faster-whisper)
- `e33c8b4` refactor: 単語境界スナップ・意訳モード・重複話検出強化・空白削減パラメータ調整
- `e8cc654` perf: ffmpeg多重再エンコードを1パスに統合・Whisperモデルキャッシュ・AIキャプション/バズスコア機能追加
- `6e2e400` feat: バズ最大化機能を追加（モーション字幕・キーワード強調・冒頭フック・CTA・数字オーバーレイ・BGM）

### 5f3633a のポイント
- `backend/app/services/asr.py` を新規追加 — ASR 層を独立化し、3段フォールバック
  （ReazonSpeech NeMo → WhisperX → faster-whisper）。
- 環境変数 `ASR_BACKEND` で個別バックエンド強制可（`auto`/`reazonspeech`/`whisperx`/`faster-whisper`）。
- ReazonSpeech `Subword`（単一点 timestamp）から既存 `(words, segments)` 形式へ変換。
  隣接 subword の差で duration を推定、末尾は `segment.end_seconds`、BPE 境界マーカー `▁`(U+2581) を除去。
- `subtitle.py` は字幕整形専用に整理、`transcribe_with_words` は `asr.py` から re-export
  （video.py 等の呼び出し側は無変更）。
- Dockerfile に `git` 追加（git+https インストール対応）。
- docker-compose.yml に `hf-cache` ボリュームと `HF_HOME` 環境変数を追加し、
  HuggingFace モデル DL を永続化（NeMo モデル ~2GB）。
- pydantic を `2.10.5` → `>=2.10.6,<3.0.0` に緩和（`nv-one-logger-core` 要件）。
- `tests/test_asr.py` 新規 12 件（subword→word 変換 5件・フォールバック 6件・再 export 1件）。
- Docker 内 pytest で **76/76 PASSED**（既存 64 + 新規 12）を確認。

## 現在の状態

- バックエンド起動中（`docker compose up backend` で稼働）。
- ASR は `ASR_BACKEND` 未設定 → `auto` モードで ReazonSpeech が **第一優先**。
- 初回リクエスト時に HuggingFace から NeMo モデル（~2GB）を DL → `hf-cache` ボリュームに永続化。
- WhisperX/faster-whisper はフォールバックとして温存。
- 既存の dedup / merge / snap / 辞書補正は **まだ残している**（ReazonSpeech の生品質を実動画で
  確認してから整理判断）。

## 次セッションでやること

### 🎯 Goal: 実動画で ReazonSpeech の品質検証 → 不要後処理の整理

1. **精度比較**
   - 同一動画で `ASR_BACKEND=reazonspeech` / `=whisperx` / `=faster-whisper` を切り替えて出力比較。
   - 評価軸: 誤認識率（特に専門用語・固有名詞）、句読点配置、字幕タイミング。
   - ログで所要時間も記録（バックエンドログに `ReazonSpeech: %d segments, ...` を出力済み）。

2. **後処理の整理判断**（ReazonSpeech の品質が十分なら）
   - `subtitle.py` の `_dedupe_adjacent_overlaps` — Whisper チャンク境界対策、ReazonSpeech では不要なはず。
   - `subtitle.py` の `_merge_short_segments` — 文の途中で短くぶつ切るケース、ReazonSpeech の挙動次第。
   - `vad.py` の `snap_silences_to_word_boundaries` — 単語境界が正確になれば不要。
   - `llm.py` の `_CORRECTION_SYSTEM_PROMPT` 系 — 精度上がれば LLM 校正の閾値を緩める / オフにできる可能性。
   - `data/jp_corrections.txt` — 個別誤認識パターンが減るなら辞書も縮小可能。

3. **(オプション) Subword 単位以上の粒度**
   - 現状は ReazonSpeech の subword をそのまま word 扱い。読みやすさ次第では「単語クラスタリング」
     （BPE 境界マーカー `▁` の出現位置で分割）を実装する余地あり。

4. **(オプション) GPU 対応**
   - 現状 `device="cpu"` 固定。Mac の MPS や CUDA が使える環境なら `load_model(device=...)` を
     環境変数で切替可能にする。

### Docker 起動 / テスト方法

```bash
# 全テスト（76件）
docker compose run --rm --no-deps -e PYTHONPATH=. backend \
  bash -c "pip install --quiet pytest && pytest tests/ -v"

# バックエンド起動（実動画検証用）
docker compose up backend

# バックエンドだけ強制バックエンド指定
ASR_BACKEND=reazonspeech docker compose up backend
ASR_BACKEND=whisperx       docker compose up backend
ASR_BACKEND=faster-whisper docker compose up backend
```

## 差別化軸（変わらず）

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
      asr.py              # 🆕 3段ASRフォールバック (ReazonSpeech/WhisperX/faster-whisper)
      ffmpeg.py           # cut_and_concat, apply_pipeline_combined, mix_bgm 等
      subtitle.py         # 字幕整形 (words_to_segments, segments_to_ass) ※ASR は asr.py へ移動
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
HANDOVER.md を読んで、実動画で ReazonSpeech / WhisperX / faster-whisper の
品質比較から始めて。docker compose up backend で起動済み。
ASR_BACKEND を切り替えながら同じ動画を投入し、誤認識・タイミング・処理時間を
比較してログに残して。問題なければ dedup / merge / snap の後処理を整理。
```
