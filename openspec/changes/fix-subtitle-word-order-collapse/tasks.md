## 1. 実装(video.py の Stage 5 分割)

- [x] 1.1 `_run_processing` 内の Stage 5 ブロックを把握し、 5a / 5b の境界を引く(目視確認)
- [x] 1.2 Stage 5a を整理: cut.mp4 transcribe(2段目)→ 施策F/G で oversized_2nd 検出 → cut2.mp4 生成。 出力は `cut_output`(cut2.mp4 or cut.mp4)。 字幕用 words の remap は廃止
- [x] 1.3 既存の「字幕用 sub_segments を words_in_cut_1st (1段目 primary) から生成」ロジックを削除
- [x] 1.4 Stage 5b を新規追加: `cut2_audio = str(job_dir / "cut2_audio.wav")` で extract_audio
- [x] 1.5 Stage 5b で `transcribe_with_words(cut2_audio, initial_prompt=settings.transcript_prompt or None)` を呼び、 `words_cut3` を得る
- [x] 1.6 辞書補正: `if corrections and words_cut3: words_cut3 = apply_corrections_to_words(words_cut3, corrections)`
- [x] 1.7 `sub_segments = words_to_segments(words_cut3, max_chars=settings.subtitle_max_chars)` で字幕用 segments を生成
- [x] 1.8 フォールバック実装: 施策F が発動しない(`oversized_2nd` が空)で cut2.mp4 が無い場合、 `sub_segments = words_to_segments(words_cut, ...)` (cut.mp4 ベース)
- [x] 1.9 `_merge_word_streams` ヘルパーを削除(commit a1f12af 由来、 用途消滅)
- [x] 1.10 `_filter_words_by_segments` の字幕用呼び出し(words_in_cut_1st 周辺)を削除。 動画カット判定用(施策G の `words_in_cut_1st`)は維持

## 2. テスト追加

- [x] 2.1 既存 105 件のテストが PASS することを確認
- [x] 2.2 「Stage 5b で 3 段目 transcribe が呼ばれる」ことを検証するモックテストを追加(`tests/test_video_router_stage5b.py`)
- [x] 2.3 「施策F 未発動時に 2 段目 words_cut へフォールバックする」モックテストを追加

## 3. ベースライン再測定

- [ ] 3.1 docker compose で backend を再起動(uvicorn --reload で自動でも可)
- [ ] 3.2 `test-videos/seitai_food.mov` を `/api/process` で再処理(skip_preview=true, ⚡ぎっしりプリセット)
- [ ] 3.3 完了後 `python backend/scripts/measure_quality.py <new_job_id>` を実行
- [ ] 3.4 `quality_report.md` を確認: #5 #6 が ✅ になっていることを期待。 #7 #8 も改善傾向か確認
- [ ] 3.5 出力字幕の冒頭 5 Dialogue を目視確認: subword 語順崩壊が消失しているか
- [ ] 3.6 HOOK / CTA / 動画長 / 処理時間 に退行がないか確認(処理時間は +30-60 秒の範囲)

## 4. baseline.md 更新

- [ ] 4.1 `openspec/changes/establish-quality-line/baseline.md` の seitai_food.mov 列を更新
- [ ] 4.2 概要セクション(機械測定 X/6、 全体 X/14)を更新
- [ ] 4.3 「不合格項目 → 次に起票すべき change 候補」の `fix-subtitle-word-order-collapse` を「✅ 解決済」とマーク
- [ ] 4.4 まだ残る不合格項目(#7 #8 など)を `fix-subtitle-segmentation-quality` 候補として明示

## 5. ドキュメント

- [ ] 5.1 `.planning/HANDOVER.md` を更新: 「Stage 5 が 5a/5b に分割された」「字幕生成は 3 段目 transcribe に統一」を反映
- [x] 5.2 video.py のクラスドキュストリングまたはモジュールコメントに新フロー(5a/5b)を記載

## 6. archive 準備

- [ ] 6.1 全タスクの完了確認
- [ ] 6.2 ベースライン再測定で項目#5, #6 が合格していることを確認(必須)
- [ ] 6.3 `openspec archive fix-subtitle-word-order-collapse` で archive
- [ ] 6.4 archive 後 `openspec/specs/quality-line/spec.md` に MODIFIED Requirements が反映されていることを確認
