## Why

`fix-subtitle-word-order-collapse` 適用後のベースライン (job 994f47eb) で、 動画 84.58 秒中、 字幕が **36.38 秒目** から始まる (前半 43% に字幕無し) 問題が確認された。

調査により真因が **動画カット段階での発話消失** であることが判明:

```
# 元動画 audio で 1段目 ReazonSpeech transcribe (元時刻):
  20.38- 20.70: 客
  20.70- 20.94: 様
  20.94- 21.18: が
  21.18- 21.42: 悩
  21.42- 21.74: ま
  21.74- 21.82: れ

# 一方、 silero VAD の silences (tight preset 設定):
  0.00 - 20.75   <- ASR が 20.38 で「客」を認識した区間を silence と判断
  22.674-23.278  <- 「悩まれている」発話の途中の閉鎖音を silence と判断
```

silero VAD が音声を「無音」と誤判断 → 該当区間が voice_segments から除外 → cut.mp4 / cut2.mp4 から物理削除 → 字幕に出ない。

これは **3 段目 ASR の認識ミスではなく、 そもそも音声が動画から消えている** 構造的問題。 ASR-aware の保護メカニズムが無いため、 silero VAD の判断ミスを補正できない。

業務量産品質ライン #2「冒頭・末尾の発話保護」が不合格になっており、 業務量産投入の致命的ブロッカー。

## What Changes

- **新規ヘルパー** `protect_words_from_silences(silences, words, margin)` を `backend/app/services/silence.py` に追加
  - silences のうち、 ASR が word を認識した範囲を**穴あけ**して除外する
  - 例: silence [0.0, 20.75], word [20.38, 20.94] → silence [0.0, 20.28]
  - margin (デフォルト 0.1 秒) で word の前後にバッファを設ける
- `backend/app/routers/video.py` の **Stage 2 と Stage 3 の間** で、 1 段目 transcribe が利用可能な場合に `protect_words_from_silences(silences, words)` を適用
  - micro_silence の merge_ranges の後、 voice_segments を計算する前
- BREAKING: なし(既存 API 不変、 voice_segments がより発話を保護する方向に変わるのみ)
- 処理時間: 影響ほぼなし(O(n×m) の単純計算)

## Capabilities

### New Capabilities
なし(既存パイプラインへの保護機能追加)

### Modified Capabilities
- `quality-line`: 項目#2 (冒頭・末尾の発話保護) の合格率改善を実証する。 spec の Requirement 内容は変えず、 ベースラインの数値を更新

## Impact

- **Backend**:
  - 追加: `silence.py` に `protect_words_from_silences` 関数 (約 25 行)
  - 変更: `video.py` の Stage 2-3 間に 1 行(条件分岐含めて約 5 行)
- **Frontend**: 影響なし
- **テスト**:
  - 既存 107 件は維持
  - 新規 3 件: 「silence が word を含む場合の穴あけ」「複数 word を含む場合」「margin 適用」
- **ベースライン**: 本 change 完了後、 seitai_food.mov を再測定して `baseline.md` を更新
- **期待効果**:
  - 冒頭の発話「お客様が悩まれているダイエットの食事の話をしようと思います」が字幕に出る
  - 項目#2 ❌ → ✅、 #5 ⚠️ → ✅ 期待
  - 全体合格率 7/14 → 9-10/14 見込み
- **副作用リスク**:
  - 1段目 transcribe で誤認識(ノイズを word として誤検出)した場合、 ノイズ区間が voice_segments に含まれる → 削除し損ねる可能性
  - 緩和策: margin=0.1 秒に抑えて影響を局所化。 ReazonSpeech は誤認識しても word.start/end は概ね正確
