## ADDED Requirements

### Requirement: 音声前処理 (afftdn + loudnorm) の適用

`extract_audio` は元動画から audio.wav を生成する際、 ASR 認識精度を高めるための前処理として以下のフィルタを適用すること (SHALL):

- **afftdn** (FFT-based denoise) で背景ノイズを除去 (nr=12, nf=-25)
- **loudnorm** (EBU R128) で音量を -16 LUFS、 LRA=11、 TP=-1.5 に正規化

これらは 16kHz mono PCM への変換の前段で適用される (SHALL)。

#### Scenario: extract_audio のフィルタチェーン
- **WHEN** `extract_audio(input_video, audio_path)` を呼出
- **THEN** ffmpeg コマンドに `-af afftdn=nr=12:nf=-25,loudnorm=I=-16:LRA=11:TP=-1.5` が含まれる

#### Scenario: 出力フォーマットの維持
- **WHEN** 前処理後の audio.wav を確認
- **THEN** sample rate 16000、 mono、 PCM 形式である (既存と同じ)
