# Reel Creator - デザインドキュメント

**作成日:** 2026-02-25
**ステータス:** 承認済み

## 概要

TikTok/Instagramリール配信用の動画を簡単に作成するWebアプリケーション。
動画をアップロードするだけで、無音部分を自動削除し、オプションでAI字幕を付与して出力する。

## 要件

| 項目 | 内容 |
|------|------|
| 種類 | シンプルな1ページ動画加工ツール |
| 入力 | 縦型動画（9:16）、最大3分、MP4/MOV/WebM |
| コア機能 | 無音部分の自動削除 |
| オプション | AI字幕自動生成（Whisper） |
| 出力 | TikTok/IGリール用MP4 |
| デプロイ | ローカル（認証なし、後から追加可能な構成） |

## アーキテクチャ

### 構成: モノリス（Next.js + FastAPI + Docker Compose）

```
reel-creator/
├── frontend/                # Next.js 14 (App Router)
│   ├── app/
│   │   ├── page.tsx         # メイン画面（1ページ完結）
│   │   └── layout.tsx
│   ├── components/
│   │   ├── VideoUploader.tsx    # ドラッグ&ドロップアップロード
│   │   ├── VideoPreview.tsx     # プレビュー再生
│   │   ├── ProcessingPanel.tsx  # 処理オプション設定
│   │   └── DownloadPanel.tsx    # 完成動画ダウンロード
│   └── Dockerfile
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPIエントリポイント
│   │   ├── routers/
│   │   │   └── video.py     # 動画処理APIエンドポイント
│   │   ├── services/
│   │   │   ├── silence.py   # 無音検出・削除ロジック
│   │   │   ├── subtitle.py  # Whisper字幕生成
│   │   │   └── ffmpeg.py    # FFmpegラッパー
│   │   └── models/
│   │       └── schemas.py   # Pydanticスキーマ
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

### 技術選定

| ライブラリ | 用途 | 理由 |
|-----------|------|------|
| Next.js 14 | フロントエンド | Reactベース、App Router |
| FastAPI | APIサーバー | 非同期対応、SSEサポート、型安全 |
| FFmpeg | 音声抽出・無音検出・カット・字幕焼き込み | 動画処理のデファクトスタンダード |
| faster-whisper | 音声→テキスト | OpenAI Whisperの高速版、CPUでも実用的 |
| python-multipart | ファイルアップロード | FastAPIのファイル受信に必要 |
| Docker Compose | 環境管理 | FFmpeg/Whisperの依存関係を管理 |

## 画面フロー（4ステップウィザード）

### Step 1: アップロード
- ドラッグ&ドロップ or ファイル選択
- 対応形式: MP4, MOV, WebM
- 最大ファイルサイズ: 500MB
- アップロード後、動画のプレビュー表示

### Step 2: 設定
- 無音削除の閾値: スライダー（デフォルト: -30dB）
- 無音の最小長: 何秒以上の無音を削除するか（デフォルト: 0.5秒）
- 字幕ON/OFF: トグルスイッチ
- 字幕ONの場合:
  - フォントサイズ（小/中/大）
  - 字幕の位置（下部/中央）
  - 文字色（白/黄色）

### Step 3: 処理中
- プログレスバーで進捗表示
- 処理ステージ表示:「音声解析中...」→「無音区間削除中...」→「字幕生成中...」→「動画結合中...」
- SSE（Server-Sent Events）でリアルタイム進捗

### Step 4: 完了
- 処理済み動画のプレビュー再生
- 処理結果サマリー（元の長さ → 処理後の長さ、削除された無音の合計）
- ダウンロードボタン（MP4）
- 「もう1本作る」ボタンでStep 1に戻る

## バックエンド処理パイプライン

```
入力動画 (MP4/MOV)
    │
    ▼
1. 音声抽出 (FFmpeg → WAV)
    │
    ▼
2. 無音区間検出 (FFmpeg silencedetect)
    │
    ▼
3. 有音区間の算出 (無音リスト反転 → カット点リスト)
    │
    ▼
4. 動画カット＆結合 (FFmpeg concat)
    │
    ▼
5. [字幕ON時] Whisper文字起こし (faster-whisper → SRT)
    │
    ▼
6. [字幕ON時] 字幕焼き込み (FFmpeg subtitles フィルタ)
    │
    ▼
完成動画 (MP4)
```

## APIエンドポイント

| メソッド | パス | 説明 |
|---------|------|------|
| POST | /api/upload | 動画アップロード → job_id 返却 |
| POST | /api/process/{job_id} | 処理開始（設定パラメータ付き） |
| GET | /api/progress/{job_id} | SSEで進捗をストリーム配信 |
| GET | /api/download/{job_id} | 完成動画ダウンロード |

## エラーハンドリング

| シナリオ | 対応 |
|---------|------|
| 非対応フォーマット | フロントでMIMEチェック + バックエンドでFFprobe検証 |
| ファイルサイズ超過 | フロントで即座にブロック |
| 動画が3分超過 | FFprobeで長さチェック → エラー返却 |
| 動画全体が無音 | 「有音区間が見つかりませんでした」と通知 |
| 動画に無音がほぼない | そのまま処理続行 |
| Whisper失敗 | 字幕なしで動画を返却、エラー通知 |
| サーバーエラー | ジョブをfailed状態にし、一時ファイルをクリーンアップ |

## ファイル管理

```
backend/tmp/{job_id}/
  input.mp4        # アップロード原本
  audio.wav         # 抽出音声
  segments/         # カットした各セグメント
  output.mp4        # 完成動画
  subtitles.srt     # 字幕ファイル
```

- ジョブ完了から1時間後に自動削除（バックグラウンドタスク）

## テスト方針

- バックエンド: pytest で主要ロジック（無音検出パース、有音区間算出、API正常/異常系）
- フロントエンド: 手動確認メイン（ローカル用途のため最小限）
