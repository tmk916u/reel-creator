## Context

### 直前までの解決済 / 未解決
- `fix-subtitle-word-order-collapse`: 字幕の語順崩壊を Stage 5 を 5a/5b に分割して根治。 3段目 transcribe(cut2.mp4)で字幕生成
- `fix-asr-aware-silence-protection`: silero VAD と ASR の判断が食い違う場合に ASR を優先して silence を穴あけ。 発話の物理保護を実現

### 観測されている残課題 (job b127c11d)
- cut2.mp4 (102.4秒) の冒頭 30 秒に発話が物理的に存在
- しかし 3段目 ReazonSpeech (cut2.mp4 transcribe) では word_count(0-30s) = 0
- 1段目 transcribe (元動画 audio) では同じ発話を 20.38 秒目で認識できる
- つまり ReazonSpeech が cut_and_concat 後の冒頭認識を苦手としている

### 制約・依存
- 既存の `_filter_words_by_segments` ヘルパーは元時刻 → カット後時刻の remap に使える
- `voice_segments` (元時刻のセグメント) と `cut2_voices` (cut.mp4 内時刻のセグメント) が両方利用可能
- `fix-subtitle-word-order-collapse` で「2 段 remap は崩壊する」と判明済み → 範囲を限定して再利用

## Goals / Non-Goals

**Goals:**
- 3段目 ReazonSpeech の冒頭認識ミスを 1段目補完で穴埋め
- 字幕に動画冒頭の発話を出現させる(#2, #5 改善)
- 影響範囲を「補完が必要な冒頭区間のみ」に限定して、 前回の崩壊リスクを最小化

**Non-Goals:**
- cut_and_concat 自体の改善 (afade 軽減 / 音声品質向上)。 これは別 change で対応可能だが本 change のスコープ外
- 動画末尾の認識ミス補完 (今のところ症状なし)
- ReazonSpeech 自体のチューニング

## Decisions

### D1: 補完を発動する閾値
- `leading_threshold = max(2.0, cut2_duration * 0.05)`
- 動画長 100 秒なら閾値 5 秒。 50 秒なら閾値 2.5 秒、 但し最低 2 秒
- 3段目 first_word.start がこの閾値を超えるなら補完発動

**理由**: 5% は経験的な比率。 短い動画でも閾値が極端に小さくならないよう 2 秒のフロアを設定

### D2: 補完範囲のマージン
- `补完_end = first_3rd_word.start - 0.1`
- 0.1 秒のマージンで 3段目との境界の重複を防ぐ

**理由**: 1段目 と 3段目 で同じ発話を別 word として認識した場合、 マージンで二重を吸収

### D3: 1段目 words の remap 方法
- `words → _filter_words_by_segments(words, voice_segments) → words_in_cut_1st`
- `words_in_cut_1st → _filter_words_by_segments(words_in_cut_1st, cut2_voices) → words_in_cut2_1st`
- cut2_voices が None (施策F 未発動) なら 1 段で済む

**理由**: 既存ヘルパーをそのまま使う。 2 段 remap の崩壊リスクは「補完範囲が冒頭数秒に限定」 で大幅低減

### D4: フォールバック(施策F 未発動)時
- cut2_generated = False → 字幕用は 2段目 words_cut (cut.mp4 ベース)
- この場合の補完は `1段目 → cut.mp4 内時刻 → 2段目との hybrid`
- 既存の `subtitle_words = words_cut` の前に補完判定を入れる

### D5: 補完 word の subword 順序保証
- 1段目 補完の範囲を `cut2 内時刻 < first_3rd_word.start - 0.1` で絞ったあと、 **start で sort** する
- 順序崩壊が起きていれば start が逆転するので、 ソートで強制的に整列
- 万一順序崩壊が見つかった場合は補完を諦める(`drop_leading_corrupted_words` 的な保護)

## Risks / Trade-offs

### R1: 1段目 ASR 補完で順序崩壊が再発するリスク
**Mitigation**:
- 補完範囲を冒頭の数秒に限定 → 影響は冒頭の数 Dialogue のみ
- start で sort して時刻順序を強制
- 補完範囲を後の `words_to_segments` で max_chars=10 で切るので、 短い分節になる程度

### R2: 1段目 補完が誤認識をそのまま字幕に流す
**Mitigation**:
- 後続の LLM 校正 (`correct_transcript_segments`) で文章として整える
- 動画固有辞書 (`apply_corrections_to_words`) も適用済み

### R3: 補完範囲が広すぎる場合の処理時間増加
**Mitigation**:
- 1段目 words は既にメモリ上 → 追加の transcribe 不要
- remap は O(n²) だが word 数は 200-400 程度なので影響なし

## Migration Plan

### 段階 1: 実装
1. Stage 5b の `if cut2_generated:` ブロック内に hybrid 補完ロジックを追加
2. 同 `else:` ブロック(施策F 未発動)にもフォールバック補完を追加
3. ログ出力で補完範囲を可視化

### 段階 2: テスト
1. 既存 112 件 PASS 確認
2. 「3段目 冒頭ミス時に 1段目補完が prepend」テスト追加
3. 「3段目 冒頭認識成功時は補完なし」テスト追加

### 段階 3: ベースライン再測定
1. seitai_food.mov 再処理
2. measure_quality.py → quality_report.md
3. 字幕冒頭 5 Dialogue を目視確認
4. baseline.md に新 job を 4 列目で追加

### Rollback
本 change は video.py の Stage 5b 内の追加のみ。 git revert で完全に元に戻る。

## Open Questions

- **Q1**: 末尾の認識ミスも補完すべきか?
  - **暫定方針**: No。 観測で症状なし。 必要時に別 change で対応
- **Q2**: 動画長 5% の閾値は環境別に調整すべきか?
  - **暫定方針**: ハードコード。 settings に出すのは過剰
