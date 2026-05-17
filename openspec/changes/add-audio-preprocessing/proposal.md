## Why

スマホ自撮り動画は環境音 + 音量バラつき + 子音不明瞭で ReazonSpeech の認識精度を下げる。 ffmpeg で音声前処理を入れれば認識精度を +5-10% 向上させられる。

業務量産品質ライン #5 (字幕の誤認識) の根本対策。 「事への」 「悪い要」 等の subword 断片化は音声品質が一因。

## What Changes

- `backend/app/services/ffmpeg.py` の `extract_audio` を強化:
  - `afftdn` (FFT-based denoise) で背景ノイズを除去
  - `loudnorm` (EBU R128) で音量を -16 LUFS に正規化
  - 既存の `-ar 16000 -ac 1` (16kHz mono) 出力は維持
- BREAKING: なし(audio.wav の特性が変わるが API 不変)
- 処理時間: +3-8 秒/動画 (5 分動画想定)

## Capabilities

### Modified Capabilities
- `quality-line`: 項目#5 の精度を ASR レベルで向上

## Impact

- **Backend**: ffmpeg.py の extract_audio (約 10 行)
- **テスト**: 既存テストの ffmpeg コマンド構築検証を更新
- **業務量産**: 動画 1 本あたり +3-8 秒、 14 本/週 で +1-2 分の overhead で誤認識減
