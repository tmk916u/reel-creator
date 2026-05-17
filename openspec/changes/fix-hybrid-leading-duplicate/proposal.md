## Why

job eabb58b3 の実際の出力で、 字幕冒頭 6 秒間 **同じフレーズが二重表示** される現象を確認:

```
Dialogue 1 (0.14-3.10): 客様が悩まれているダイエットの
Dialogue 2 (3.10-6.70): お客様が悩まれているダイエット
```

これは `fix-third-stage-asr-leading-miss` で導入した **hybrid 補完** の副作用:
- 1段目 ASR (元動画) で「お客様が悩まれているダイエットの食事の話…」を 元時刻 0-9 秒で認識
- これを voice_segments → cut2_voices で remap し、 cut2 内時刻 0-3.10 秒に配置
- 3段目 ASR (cut2.mp4) で同じ発話を cut2 内時刻 3.10-9.0 秒で認識(物理的には同じ位置の音声)
- hybrid 補完で 1 段目分を prepend → 同じテキストが 2 つの位置に並ぶ

視聴者目線では「字幕が壊れている」 ように見えるため、 投稿可否レベルの問題。 業務量産には致命的。

## What Changes

- `_hybrid_prepend_leading_words` 内で **prepend 前に dedup** を実施:
  - 1段目 補完 (`leading_candidates`) の末尾 word と、 3段目 (`third_words`) の先頭 word の text を比較
  - 連続して一致する subsequence があれば、 leading 側から重複分を削除
  - 1-N word の最長 match を探す(N = 10 程度に制限)
- BREAKING: なし(hybrid 補完を発動するケースの内部処理改善)
- 処理時間: O(N²) 比較だが N=10、 word 数 5-10 程度なのでオーバーヘッド微小

## Capabilities

### Modified Capabilities
- `quality-line`: 項目#2 / #5 の品質を保ちつつ、 hybrid 補完の副作用を解消

## Impact

- **Backend**: `video.py` の `_hybrid_prepend_leading_words` ヘルパーを強化(約 20 行)
- **テスト**: 既存 120 件 PASS、 新規 2-3 件(dedup 動作確認)
- **業務量産**: 字幕の二重表示が消えて投稿可能なクオリティへ
