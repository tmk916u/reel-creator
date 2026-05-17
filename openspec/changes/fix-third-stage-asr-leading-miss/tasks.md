## 1. 実装

- [ ] 1.1 `video.py` の Stage 5b で `cut2_generated=True` 経路に hybrid 補完を追加:
  - 3段目 first_word.start と閾値 (動画長 × 0.05、 最低 2秒) を比較
  - 超える場合: 1段目 words を `_filter_words_by_segments(words, voice_segments)` で cut.mp4 内時刻に remap
  - その結果を更に `_filter_words_by_segments(words_in_cut_1st, cut2_voices)` で cut2 内時刻に remap
  - `first_3rd_word.start - 0.1` より前の word を補完範囲として抽出
  - start で sort してから 3段目 words の先頭に prepend
  - ログ出力: 補完 word 数 + 補完範囲の時刻
- [ ] 1.2 同じく `cut2_generated=False` (施策F 未発動)経路にも補完を追加:
  - 字幕用 = words_cut (cut.mp4 ベース) の前に 1段目 補完を hybrid prepend
  - 1段目 → cut.mp4 内時刻の 1 段 remap だけで済む

## 2. テスト追加

- [ ] 2.1 既存 112 件のテストが PASS することを確認
- [ ] 2.2 `backend/tests/test_video_router_stage5b.py` にテスト追加:
  - 「3段目 冒頭ミス時に 1段目補完が prepend」
  - 「3段目 冒頭認識成功時は補完なし」

## 3. ベースライン再測定

- [ ] 3.1 `test-videos/seitai_food.mov` を `/api/process` で再処理(tight preset)
- [ ] 3.2 `python backend/scripts/measure_quality.py <new_job_id>` を実行
- [ ] 3.3 字幕冒頭 5 Dialogue を目視確認: 「お客様が悩まれている」(or 同等)が出るか
- [ ] 3.4 動画長と処理時間に退行がないか確認

## 4. baseline.md / HANDOVER.md 更新

- [ ] 4.1 `establish-quality-line/baseline.md` に新 job 列を追加
- [ ] 4.2 概要(機械測定 / 全体合格率)を更新
- [ ] 4.3 `fix-third-stage-asr-leading-miss` を「✅ 解決済」 とマーク
- [ ] 4.4 `.planning/HANDOVER.md` に hybrid 補完を反映

## 5. archive 準備

- [ ] 5.1 全タスクの完了確認
- [ ] 5.2 字幕冒頭に動画冒頭発話が出ていることを確認
- [ ] 5.3 `openspec archive fix-subtitle-word-order-collapse`
- [ ] 5.4 `openspec archive fix-asr-aware-silence-protection`
- [ ] 5.5 `openspec archive fix-third-stage-asr-leading-miss`
- [ ] 5.6 archive 後 `openspec/specs/quality-line/spec.md` に Requirements が反映されていることを確認
