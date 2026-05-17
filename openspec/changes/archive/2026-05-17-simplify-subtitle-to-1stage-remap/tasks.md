## 1. 実装 (silence.py)

- [ ] 1.1 `build_orig_to_cut2_mapping(voice_segments, cut2_voices=None)` を追加
- [ ] 1.2 `remap_words_with_mapping(words, mappings)` を追加

## 2. 実装 (video.py)

- [ ] 2.1 import に `build_orig_to_cut2_mapping`, `remap_words_with_mapping` を追加
- [ ] 2.2 Stage 5b を 1 段 remap に書き換え:
  - cut2_audio 抽出を削除
  - 3 段目 transcribe (`transcribe_with_words` 呼出) を削除
  - hybrid 補完 (`_hybrid_prepend_leading_words` 呼出) を削除
  - 1 段目 words + 合成 mapping で字幕用 words を生成
- [ ] 2.3 `_hybrid_prepend_leading_words` 関数を削除
- [ ] 2.4 `_dedup_leading_against_third` 関数を削除
- [ ] 2.5 モジュール冒頭のフロー説明コメントを更新 (Stage 5b の挙動)

## 3. テスト

- [ ] 3.1 `tests/test_silence.py` に新規テスト 4 件:
  - `build_orig_to_cut2_mapping` 施策F 発動時の合成
  - `build_orig_to_cut2_mapping` 施策F 未発動時
  - `remap_words_with_mapping` 標準 remap
  - `remap_words_with_mapping` 削除区間に かかる clamp
- [ ] 3.2 `tests/test_video_router_stage5b.py` の hybrid/dedup 系テスト (6-7 件) を削除
- [ ] 3.3 新規テスト: 「Stage 5b で 3 段目 transcribe が呼ばれない」 を更新
- [ ] 3.4 既存 127 件 - 削除 6-7 + 新規 4 = 約 124 件 で PASS 確認

## 4. ベースライン再測定

- [ ] 4.1 seitai_food.mov を再処理(tight preset)
- [ ] 4.2 出力字幕の冒頭 5 Dialogue を目視: 「お客様が悩まれているダイエットの食事の話をしようと思います」 が出現
- [ ] 4.3 機械測定で退行なし確認

## 5. archive

- [ ] 5.1 全タスクの完了確認
- [ ] 5.2 `openspec archive simplify-subtitle-to-1stage-remap`
