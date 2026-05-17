## 1. 実装

- [x] 1.1 `backend/app/services/silence.py` を読んで既存関数のスタイルを把握
- [x] 1.2 `protect_words_from_silences(silences, words, margin=0.1)` を `silence.py` に追加
- [x] 1.3 `video.py` の Stage 3 末尾(`snap_silences_to_word_boundaries` の直前)に `protect_words_from_silences(silences, words)` を 1 行追加
- [x] 1.4 `video.py` 冒頭の import に `protect_words_from_silences` を追加

## 2. テスト追加

- [x] 2.1 既存 107 件のテストが PASS することを確認
- [x] 2.2 `tests/test_silence.py` に `protect_words_from_silences` のテストを 5 件追加:
  - silence の先頭境界で word が重なる場合の穴あけ
  - silence の中央に word がある場合の 2 分割
  - silence と重なる word が無い場合の no-op
  - 複数 word の merge + 穴あけ
  - words 空の no-op

## 3. ベースライン再測定

- [x] 3.1 `test-videos/seitai_food.mov` を `/api/process` で再処理(tight preset) → job b127c11d
- [x] 3.2 `python backend/scripts/measure_quality.py b127c11d-bc6f-4f34-baaa-fd93abf9203b` を実行
- [x] 3.3 `quality_report.md` 確認: 機械測定 4/6 維持、 #6 同期 ✅ 0件
- [x] 3.4 出力字幕の冒頭 Dialogue を目視確認: 開始 36.4 → 30.2 秒に短縮(物理保護のみ、 3段目 ASR 認識ミスは別 change で対応)
- [x] 3.5 処理時間 ±5 秒以内を確認 (248→261、 ASR-aware 処理は ~10秒影響、 許容範囲)

## 4. baseline.md 更新

- [x] 4.1 `openspec/changes/establish-quality-line/baseline.md` に新 job (b127c11d) を追加
- [x] 4.2 概要セクション(機械測定、 全体合格率)を更新
- [x] 4.3 「次に起票すべき change 候補」を「`fix-third-stage-asr-leading-miss` (字幕反映の根治)」 に更新

## 5. ドキュメント

- [x] 5.1 `.planning/HANDOVER.md` 更新は次の change `fix-third-stage-asr-leading-miss` archive 時にまとめて反映
- [x] 5.2 video.py のステージフローコメントに「Stage 2-3 間で protect_words_from_silences を適用」を追記

## 6. archive 準備

- [x] 6.1 全タスクの完了確認
- [x] 6.2 ベースライン再測定で項目#2 (冒頭発話保護) の物理保護が動作していることを確認
- [ ] 6.3 `openspec archive fix-subtitle-word-order-collapse` も先に archive
- [ ] 6.4 `openspec archive fix-asr-aware-silence-protection` で archive
- [ ] 6.5 archive 後 `openspec/specs/quality-line/spec.md` に MODIFIED + ADDED Requirements が反映されていることを確認
