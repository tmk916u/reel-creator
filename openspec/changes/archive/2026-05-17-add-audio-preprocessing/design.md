## Context

### 現状の extract_audio
`backend/app/services/ffmpeg.py` で動画から audio.wav を抽出する関数。 現状は単純に音声トラックを 16kHz mono PCM に変換するだけで、 ノイズ除去や音量正規化はなし。

### スマホ自撮り音声の典型的な問題
- 環境音 (エアコン、 外の車、 マイク自体のヒスノイズ)
- 音量バラつき (近くで話す部分は大きく、 離れる部分は小さい)
- 子音不明瞭 (「し / し」 「じ / ち」 が認識ミス)

これらは ReazonSpeech の認識精度を下げる主要因。

## Goals / Non-Goals

**Goals:**
- 環境音を抑える (afftdn で SNR 改善)
- 音量を -16 LUFS に揃える (ReazonSpeech が安定して動作する音量帯)
- 既存の 16kHz mono PCM 出力を維持

**Non-Goals:**
- 機械学習ベースのノイズ除去 (RNNoise / noisereduce) の導入 (まず ffmpeg 内蔵フィルタで効果検証)
- 高音域強調 (高品質マイク使用前提なので不要)
- 動画自体の音声品質改善 (これは別 change で出力動画にも適用)

## Decisions

### D1: afftdn (FFT-based denoise)
```
afftdn=nr=12:nf=-25
```
- `nr=12`: ノイズ削減量 12 dB (デフォルト 12)
- `nf=-25`: ノイズフロア -25 dB (環境ノイズを -25 dB 以下とみなす)

**理由**: ffmpeg 内蔵で安定。 機械学習モデル不要なので Docker 環境への影響なし。

### D2: loudnorm (EBU R128 正規化)
```
loudnorm=I=-16:LRA=11:TP=-1.5
```
- `I=-16`: target integrated loudness -16 LUFS (SNS 動画の標準)
- `LRA=11`: loudness range 11 LU (適度なダイナミックレンジ)
- `TP=-1.5`: true peak -1.5 dB (クリップ防止)

**理由**: ReazonSpeech は音量 -16 〜 -20 LUFS で最も安定して動作する。 スマホ自撮りの音量バラつきを正規化することで、 小さい声でも認識可能に。

### D3: 適用順序
```
afftdn → loudnorm → 16kHz mono PCM
```
1. ノイズ除去で SNR 改善 (信号 - ノイズ比)
2. 正規化で音量帯を統一
3. resample + downmix

順序逆だと正規化がノイズも増幅してしまう。

### D4: 2-pass / 1-pass
- loudnorm の本来の使い方は 2-pass (1 回目で測定、 2 回目で正規化)
- ただし業務量産で 2-pass は処理時間 ×2 倍
- 1-pass で十分実用的 (target loudness の精度 ±1 LUFS 程度)
- 1-pass を採用

## Risks / Trade-offs

### R1: ノイズ除去が発話の子音まで削ってしまう
**Mitigation**: `nr=12` で控えめに設定。 `nr=20` 以上だと過剰になるが、 12 なら子音は保たれる

### R2: 音量正規化で小さい声を増幅した結果、 ヒスノイズも増幅される
**Mitigation**: afftdn を先に適用してノイズ削減してから正規化するので影響限定

### R3: 既存テストの ffmpeg コマンド検証
**Mitigation**: test_ffmpeg.py の期待値を新コマンドに合わせて更新

## Migration Plan

1. extract_audio に -af afftdn,loudnorm を追加
2. テスト期待値更新
3. seitai_food.mov 再処理で 1 段目 ASR の誤認識減少を観察
