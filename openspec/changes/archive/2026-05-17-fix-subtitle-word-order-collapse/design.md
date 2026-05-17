## Context

### 現在の Stage 5 (字幕生成) の構造
```
input.mp4 (元動画 250s, 元時刻)
  ↓ Stage 1-3: 1段目 transcribe + 施策A-E
  ↓ Stage 4: cut_and_concat (voice_segments)
cut.mp4 (190s, cut.mp4 内時刻)
  ↓ Stage 5: 字幕生成
  │   ├─ 2段目 transcribe (words_cut)
  │   ├─ 施策F (oversized_2nd) + 施策G (1+2段目 OR) → cut2_voices
  │   ├─ cut_and_concat → cut2.mp4 (cut2 内時刻)
  │   ├─ words_cut を cut2_voices で remap (cut.mp4 → cut2 時刻)
  │   ├─ words(1段目) を voice_segments → cut2_voices の 2段 remap
  │   ├─ subtitle_words = words_in_cut_1st (b218159 で primary 戦略)
  │   └─ ASS 生成
  ↓ Stage 6-7: 演出 + 焼き込み
output.mp4
```

### 観測されたバグ (reel_d8d062dc)
- subtitle.ass の Dialogue 0-1 で「**様が悩まれているダイエットお客**」「**様事への食**」と語順崩壊
- transcript.json の word 列で「客」「様」が複数箇所に出現している可能性が高い
- 1 段目 transcribe (元時刻 250s context) は ReazonSpeech NeMo の subword timestamp の精度が揺らぎ、 同一 word が異なる時刻で 2 回出現するケースがある(推測)
- それを `_filter_words_by_segments` で 2 段 remap すると、 voice_segments の境界跨ぎで重複・語順崩壊が起きる

### 制約・依存
- ReazonSpeech NeMo はモデルキャッシュ(`@lru_cache`)済みなので、 3段目 transcribe のロード時間は 0
- 推論時間は cut2.mp4 ≒ 90 秒で 30-60 秒程度(CPU、 docker)
- 既存テスト 105 件を維持
- 既存の API インターフェース (`/api/process`) は変更しない

### 関連 commit
- `b218159`: 1段目 primary 戦略 → 本 change で **廃止**
- `a1f12af`: `_merge_word_streams` 導入 → 本 change で **削除**
- `92ed616`: 動画文脈サマリー(継続)
- `3adae01`: 動画固有辞書(継続)

## Goals / Non-Goals

**Goals:**
- 字幕の語順崩壊(項目#5)を構造的に解消する
- 字幕タイミング同期(項目#6)を 0.5 秒以内に収める
- 副次的に項目#7/#8 の改善を見込む
- 時刻空間を「字幕生成は cut2 内時刻だけ」に統一する
- BREAKING なし、 既存 API 互換維持

**Non-Goals:**
- 字幕の文字数や切れ目の最適化(項目#7/#8 の根治は `fix-subtitle-segmentation-quality` で別途)
- HOOK や CTA の改善(本 change 範囲外)
- 動画カット判定のロジック変更(施策F/G は現状維持)
- 4 段目以上の transcribe(処理時間との trade-off で 3 段目までに留める)

## Decisions

### D1: 字幕用 words は **cut2.mp4 を直接 transcribe** して取得
**理由**:
- 時刻空間が cut2 内時刻だけになり、 remap 不要 → 境界跨ぎのバグが原理的に発生しない
- ReazonSpeech が短い context (90秒) で推論するので subword timestamp の精度が安定する
- 「動画カット判定 = 1+2段目 ASR、 字幕生成 = 3段目 ASR」 と役割が明確化

**Alternatives**:
- A: 1+2段目 を 1 段 remap に統合 → 真因 (subword の重複出現) は残るため見送り
- C: 3段目を ReazonSpeech ではなく faster-whisper → 速いが日本語精度が落ちる、 整体ドメインで NG

### D2: 1段目 + 2段目 ASR は **動画カット判定のみ** に使用
**理由**:
- 役割が混在している現状(字幕にも使う)が複雑性とバグの温床
- 動画カット判定(施策F/G の OR 判定)は **動画ストーリーを保護する** ために 2 段必要
- 字幕生成は **時刻空間を統一する** ため 1 段(cut2)で十分

### D3: `_merge_word_streams` を削除
**理由**:
- subword レベルでのマージは破綻する(commit b218159 で証明済み)
- 1 段目 primary 戦略も `_filter_words_by_segments` の remap で乱れることが判明
- 本 change で字幕用 words の生成方針が「3段目 直接 transcribe」になるため、 マージ自体が不要

### D4: 3 段目 transcribe の audio は cut2.mp4 から **専用に抽出**
```python
cut2_audio = str(job_dir / "cut2_audio.wav")
extract_audio(cut2_output, cut2_audio)
words_cut2, _ = transcribe_with_words(cut2_audio, initial_prompt=...)
```
既存の `cut_audio.wav`(cut.mp4 用)とは別ファイル。 デバッグ・再現性のため。

### D5: 施策F が動かなかった (cut2 が生成されない)場合のフォールバック
- 施策F の oversized_2nd が空 → cut2.mp4 は生成されず cut_output が cut.mp4 のまま
- この場合は **cut.mp4 を transcribe した結果 (= 2段目 words_cut) を字幕用に使う**
- フォールバックパス: `字幕用 words = words_cut3 if cut2 存在 else words_cut`

### D6: ベースライン再測定の運用
- 本 change apply 後に `seitai_food.mov` で再処理 → `measure_quality.py` で測定
- `baseline.md` の seitai_food.mov 列を更新
- 退行(以前合格していた項目が不合格になる)があれば本 change を撤回 or 修正

## Risks / Trade-offs

### R1: 3段目 transcribe の追加で処理時間 +30-60 秒
**Mitigation**:
- ReazonSpeech モデルキャッシュ済み(ロード時間ゼロ)
- 業務量産 14本/週 で約 +14分/週、 字幕崩壊修正の価値 >> このコスト

### R2: cut2.mp4 で生成された短いセグメント結合動画の音声品質
**Risk**: cut_and_concat の境界でクリックノイズが入ると ASR が誤認識
**Mitigation**:
- 既存の `cut_and_concat` は filter_complex で afade 適用済み(commit a3ab72b)
- cut2.mp4 も同じ実装で生成されるので新規リスクなし

### R3: 施策F が発動しないケースで cut2.mp4 が無い
**Risk**: 3段目 transcribe が呼べない
**Mitigation**: D5 のフォールバック(2段目 words_cut を字幕用に使う)。 ただし通常は施策F が発動するケースが多い(reel_d8d062dc も 30 箇所 oversized 削除あり)

### R4: cut2.mp4 transcribe で新しい認識ミスが発生する可能性
**Risk**: cut2 = 短い動画で context が薄れ、 ReazonSpeech が誤認識する箇所が増えるかも
**Mitigation**:
- 動画固有辞書(commit 3adae01) + LLM 校正(動画文脈サマリー使用)で補正
- 再測定で確認し、 規定値を下回ったら閾値調整

### R5: 既存テスト 105 件への影響
**Mitigation**:
- 既存テストは ASR 結果をモックしている or ロジック単体なので影響なし
- ただし `video.py` の `_run_processing` フローが変わるので、 integration 風のテストが必要なら追加

## Migration Plan

### 段階 1: 実装
1. video.py の Stage 5 を 5a/5b に分割
2. 5b で cut2_audio.wav 抽出 + transcribe_with_words 呼出
3. 字幕用 words の生成元を words_cut3 に切替
4. フォールバック(D5)を実装
5. `_merge_word_streams` を削除 or deprecated コメント追加

### 段階 2: テスト
1. 既存 105 件 PASS 確認
2. 「3 段目 transcribe が呼ばれる」モックテスト追加
3. フォールバック動作のモックテスト追加

### 段階 3: ベースライン再測定
1. seitai_food.mov を再処理(skip_preview=true, ⚡ぎっしりプリセット)
2. measure_quality.py で測定
3. baseline.md の該当行を更新
4. 不合格項目が 4 → 2 以下に減ったことを確認

### Rollback
本 change は `video.py` の Stage 5 のみ変更。 git revert で完全に元に戻る。
ベースラインの数値も `establish-quality-line` change の archive 前であれば更新可能。

## Open Questions

- **Q1**: 3 段目 transcribe で得た words のうち、 1+2段目で削除候補とされた範囲(`extra_cuts`)に重なる word は除外すべきか? それとも cut2.mp4 内に物理的に存在しないので考慮不要か?
  - **暫定方針**: cut2.mp4 を直接 transcribe するので、 物理的に消えた区間の word は ReazonSpeech が返さない。 考慮不要。
- **Q2**: words_cut3 を LLM 校正に渡す時、 video_context は 1+2段目から生成したものを引き継ぐか、 3段目で再生成するか?
  - **暫定方針**: 1+2段目 の transcript 全文から video_context を生成(現状通り)。 3段目 transcribe は字幕用なので context 生成は不要。
- **Q3**: cut2.mp4 が生成されない(施策F が空)ケースで字幕生成は cut.mp4 を transcribe(現状の 2段目)するべきか?
  - **暫定方針**: D5 のフォールバック通り、 cut.mp4 ベースの 2段目 words を字幕用に使う。
