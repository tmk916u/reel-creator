## Why

`fix-asr-aware-silence-protection` 適用後のベースライン (job b127c11d) で:
- ✅ 発話の **物理保護** は達成 (cut2.mp4 84.6→102.4 秒、 +17.8 秒の発話が残る)
- ❌ しかし **字幕には反映されない** (最初の Dialogue が cut2 内時刻 30.21 秒目から)
- transcript.json 確認: 3段目 ReazonSpeech (cut2.mp4 transcribe) で 0-30 秒範囲の word は **0 個**

つまり **cut2.mp4 の冒頭 30 秒に発話は存在する** が、 3段目 ReazonSpeech が一切認識していない。 元動画 (250秒, long context) を 1段目 transcribe では `20.38秒目「客」「様」「が」「悩」` を認識できているのに、 cut2.mp4 (102秒, short context) では同じ発話を認識できない。

真因仮説:
- cut_and_concat の afade で連結境界の音量が弱められ、 ReazonSpeech が冒頭を聞き逃す
- もしくは ReazonSpeech が短い context で冒頭の信頼度が下がる仕様
- cut.mp4 段階でも 24秒目開始だったので、 連結処理が ASR 精度に影響している可能性大

業務量産品質ライン #2「冒頭・末尾の発話保護」が引き続き不合格(物理は保護されているが字幕に出ない)。

## What Changes

- **Hybrid 戦略**: 3段目 transcribe で word が認識されなかった冒頭区間を、 **1段目 ASR words を remap して補完** する
  - 3段目 first_word.start > 動画長の 5% (最低 2 秒) なら hybrid 補完を発動
  - 1段目 words を `_filter_words_by_segments` で **voice_segments → cut2_voices** の 2 段で remap
  - 補完範囲は `[0.0, first_3rd_start - 0.1)` の word のみ
  - これらを 3段目 words の先頭に prepend して subtitle_words に
- 前回 `fix-subtitle-word-order-collapse` で「2 段 remap は崩壊する」と判断したが、 **補完範囲が冒頭の数秒に限定** されるため subword 重複・順序崩壊のリスクが大幅に低い
- BREAKING: なし(内部実装、 既存 API 不変)
- 処理時間: 影響なし(既存 words 変数を再利用)

## Capabilities

### Modified Capabilities
- `quality-line`: 項目#2 (冒頭発話保護) と #5 (字幕誤認識少なさ) の合格率向上を実証

## Impact

- **Backend**:
  - 変更: `backend/app/routers/video.py` の Stage 5b に hybrid 補完ロジックを追加(約 30 行)
- **テスト**:
  - 既存 112 件は維持
  - 新規 2-3 件: 「3段目が冒頭ミス時に 1段目補完が prepend される」 / 「3段目が冒頭認識成功時は補完しない」
- **ベースライン**: 本 change 完了後、 seitai_food.mov を再測定
- **期待効果**:
  - 字幕冒頭に「お客様が悩まれている」相当が出る
  - #2 ❌ → ✅、 #5 ⚠️ → ✅ 期待
  - 業務量産品質ライン 7/14 → 9-10/14 見込み
- **副作用リスク**:
  - 1段目 words の 2 段 remap で順序崩壊が再発するリスク(補完範囲は限定的なので影響は冒頭数秒のみ)
  - 補完範囲と 3段目範囲の境界で同じ発話が二重に現れる可能性(`first_3rd_start - 0.1` のマージンで緩和)
