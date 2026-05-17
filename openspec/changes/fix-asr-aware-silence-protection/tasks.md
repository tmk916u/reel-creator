## 1. 実装

- [ ] 1.1 `backend/app/services/silence.py` を読んで既存関数のスタイルを把握
- [ ] 1.2 `protect_words_from_silences(silences, words, margin=0.1)` を `silence.py` に追加
- [ ] 1.3 `video.py` の Stage 3 末尾(`snap_silences_to_word_boundaries` の直前)に `protect_words_from_silences(silences, words)` を 1 行追加
- [ ] 1.4 `video.py` 冒頭の import に `protect_words_from_silences` を追加

## 2. テスト追加

- [ ] 2.1 既存 107 件のテストが PASS することを確認
- [ ] 2.2 `tests/test_silence.py` に `protect_words_from_silences` のテストを 4 件追加:
  - silence の先頭境界で word が重なる場合の穴あけ
  - silence の中央に word がある場合の 2 分割
  - silence と重なる word が無い場合の no-op
  - 複数 word の merge + 穴あけ

## 3. ベースライン再測定

- [ ] 3.1 `test-videos/seitai_food.mov` を `/api/process` で再処理(tight preset)
- [ ] 3.2 `python backend/scripts/measure_quality.py <new_job_id>` を実行
- [ ] 3.3 `quality_report.md` 確認: 機械測定の退行が無いか
- [ ] 3.4 出力字幕の冒頭 Dialogue を目視確認: 「お客様が悩まれている」 (or 同等) が出るか
- [ ] 3.5 動画長と処理時間に退行がないか確認(処理時間は ±5 秒以内)

## 4. baseline.md 更新

- [ ] 4.1 `openspec/changes/establish-quality-line/baseline.md` に新 job (3 列目) を追加
- [ ] 4.2 概要セクション(機械測定、 全体合格率)を更新
- [ ] 4.3 「不合格項目 → 次に起票すべき change 候補」の `fix-third-stage-asr-leading-gap` を「✅ 解決済」相当に置換、 もしくは「`fix-asr-aware-silence-protection` で解決」と注記

## 5. ドキュメント

- [ ] 5.1 `.planning/HANDOVER.md` を更新: 「ASR-aware silence 保護を追加」「冒頭発話の物理消失を根治」を反映
- [ ] 5.2 video.py のステージフローコメントに「Stage 2-3 間で protect_words_from_silences を適用」を追記

## 6. archive 準備

- [ ] 6.1 全タスクの完了確認
- [ ] 6.2 ベースライン再測定で項目#2 (冒頭発話保護) が改善していることを確認
- [ ] 6.3 `openspec archive fix-subtitle-word-order-collapse` も先に archive
- [ ] 6.4 `openspec archive fix-asr-aware-silence-protection` で archive
- [ ] 6.5 archive 後 `openspec/specs/quality-line/spec.md` に MODIFIED + ADDED Requirements が反映されていることを確認
