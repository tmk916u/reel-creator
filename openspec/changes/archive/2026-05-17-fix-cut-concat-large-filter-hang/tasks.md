## 1. 実装

- [ ] 1.1 `_chunk_segments(segments, chunk_size=10)` ヘルパーを ffmpeg.py に追加
- [ ] 1.2 `cut_and_concat` を chunk 分割ロジックに書き換え:
  - segments ≤ 10: 従来通り 1 パス filter_complex
  - segments > 10: chunk 分割 + 各 chunk を 個別 ffmpeg + concat demuxer 結合
- [ ] 1.3 subprocess.run に timeout=600 を追加、 `subprocess.TimeoutExpired` を捕捉して RuntimeError 化
- [ ] 1.4 中間ファイルは `tempfile.TemporaryDirectory` で自動削除

## 2. テスト

- [ ] 2.1 既存 128 件 PASS 確認
- [ ] 2.2 `_chunk_segments` のテスト 2 件 (25 → 3 chunks、 5 → 1 chunk)
- [ ] 2.3 cut_and_concat の chunk 分割 mock テスト (subprocess.run の呼出回数で確認)

## 3. 動作確認

- [ ] 3.1 プレビュー編集モードで seitai_food.mov を処理 → hang せず完走
- [ ] 3.2 量産モードでも従来通り動作

## 4. archive

- [ ] 4.1 全タスク完了確認
- [ ] 4.2 `openspec archive fix-cut-concat-large-filter-hang`
