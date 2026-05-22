## Phase 1: 重複文字正規化 helper

- [ ] 1.1 `subtitle.py` に `_normalize_repeated_chars(text: str) -> str` を追加
- [ ] 1.2 連続重複文字を 1 文字に圧縮 (3 連続以上は保持)
- [ ] 1.3 テスト追加 (3 件):
  - 「ほほとんど」 → 「ほとんど」
  - 「めめんたる」 → 「めんたる」
  - 「あああ」 → 「あああ」 (3 連続は保持)
- [ ] 1.4 `words_to_segments` 入口で word.text に適用

## Phase 2: 新 chunking ロジック

- [ ] 2.1 chunk 境界判定関数 `_chunk_boundary_after(word, next_word, chunk_text) -> bool` を実装
  - 強境界: word.text 末尾が 「。」「、」「!」「?」
  - 中境界: 次 word との gap (`next.start - word.get("_orig_end", word.end)`) ≥ 0.4 秒
  - 弱境界: chunk_text 累積文字数 ≥ 12 かつ 句読点で切れない場所
- [ ] 2.2 clamp 済み word (`_orig_end` あり) は強制的に独立 chunk
- [ ] 2.3 `words_to_segments` を新方針で書き直し
  - 旧 `_trailing_particles` 抑制ロジック削除
  - 旧 `_merge_short_segments` 削除 (新ロジックで包含)
- [ ] 2.4 テスト追加 (6-8 件):
  - 句読点で flush
  - 0.4 秒 gap で flush
  - 12 文字超で flush
  - clamp word が独立 dialogue
  - 句読点なし長文の弱境界 flush
  - gap が 0.4 秒未満の連続発話は結合
  - 句読点 + gap 両方ある場合は強境界が優先
  - 1 文字 dialogue の後処理

## Phase 3: 旧助詞抑制廃止

- [ ] 3.1 `_trailing_particles` 定数と関連ヘルパー削除
- [ ] 3.2 既存 `_merge_short_segments` 削除 (Phase 2 で代替済み)
- [ ] 3.3 既存テスト見直し (助詞抑制を直接 assert する 2 件) → 新方針で同等品質を満たすケースに書き換え or 削除
- [ ] 3.4 全 subtitle テスト pass 確認

## Phase 4: 統合 + 実機検証

- [ ] 4.1 `make rebuild` でコンテナ反映 (hot-reload で済むなら skip)
- [ ] 4.2 同 input.mp4 を再処理 (curl + analyze_reel.py)
- [ ] 4.3 字幕 dialogue を目視確認:
  - 「様が悩まれている」 のような word 途中切れ がないか
  - 「ほほとんど」 が「ほとんど」 に正規化されているか
  - 句読点直後で改行されているか
- [ ] 4.4 regression-bench.md に新結果追記 (Y/N 評価は手動)
- [ ] 4.5 全 94+ テスト pass 確認

## Phase 5: 完了処理

- [ ] 5.1 全タスク完了確認
- [ ] 5.2 commit (`fix: 字幕を意味のかたまりで chunk 分割 (subtitle-meaning-chunking)`)
- [ ] 5.3 `openspec archive subtitle-meaning-chunking`
