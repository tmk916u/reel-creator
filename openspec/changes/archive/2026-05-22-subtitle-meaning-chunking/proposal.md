## Why

直近の clamp + _orig_end 修正 (commit b0afa2f) で **音声カット品質と字幕同期は大幅改善** したが、 動画 reel_a9f0a821_CLAMPV2.mp4 を実機確認した結果、 **字幕の意味的セグメンテーションが破綻** していることが判明。 word を時刻順に機械連結しているため、 単語の途中で改行・分断され、 視聴者は字幕を読めない。

具体的な観測（output_segments と subtitles の比較、 81秒、 22 dialogue 件中の冒頭抜粋）:

```
Dialogue 1: 様が悩まれているダエットをお        ← 「お」「客」「ダ」「イ」が欠落・分断
Dialogue 2: 様が悩まれているダ                  ← 同じ発話の 2 回目もブツ切れ
Dialogue 3: イエットの食事への食                ← 「イ」「事」が単独行頭、 「食」が単独行末
Dialogue 4: 事の話をしようと思います結          ← 「事の話を」で次に流出、 「結」末尾流出
Dialogue 5: から言うと一番大事なのはメンタルです目  ← 「から言うと」始まり、 「目」末尾流出
Dialogue 6: に向けて食事をどういうふうにしていこうというふうに考え
Dialogue 7: たうえで実                          ← 「実」 1 文字、 「たうえで」 始まり
Dialogue 8: にそのとおりできる方っていうのはほほとんどいませんた  ← 「ほほ」 重複、 「た」 流出
```

過去の `2026-05-17-fix-subtitle-segmentation-quality` change は「助詞抑制リスト拡張」 + 「短セグ統合」で対処したが、 今回の問題は **より深い構造的破綻**：

- clamp の追加 (word.end を短縮) で、 隣接 word の境界がさらに微細化
- subword 単位の text が直接 dialogue line を形成
- 「結論から」「メンタル」のような **意味のまとまり** で改行されていない

業務量産品質ライン (`quality-line` spec) 14 項目のうち #7 (助詞直後切れ ≤ 10%) と #8 (字幕 8-14 文字比率 ≥ 70%) が再び不合格状態 (推定 80%+ が破綻). 字幕が読めないリールは公開不可能であり、 これを直さないと regression-bench の Y flip は実現しない。

## What Changes

- **新方針: 「意味のかたまり」 chunking**
  - 既存の `subtitle.py:words_to_segments` が word を時系列で max_chars 単位に切るアルゴリズムを撤廃
  - 代わりに以下の階層で chunk 境界を決める:
    1. **強境界**: 句読点「。」「、」「!」「?」 (必ず flush)
    2. **中境界**: word 間ギャップ ≥ 0.4 秒 (発話の間 = 意味の区切り)
    3. **弱境界**: 単純な文字数上限 (12-14 文字) は **強・中の境界を跨がない範囲** でのみ適用
  - 1 chunk = 1 dialogue として ASS/SRT に出力
  - clamp された word (`_orig_end` を持つ) は、 word の text を 1 chunk として独立保持 (中身が壊れているので他 word と結合しない)
- **重複文字の去重**: 「ほほとんど」「ダエット」のような ASR ノイズを word.text レベルで自動正規化 (重複文字検出 + 辞書照合)
- **既存の `_trailing_particles` 抑制ロジックは廃止**: 新方針で十分カバーされる

- BREAKING: なし (内部実装の変更、 ASS/SRT 出力 format は不変)

## Capabilities

### Modified Capabilities

- `ai-jump-cut`: subword/word transcript から字幕生成する部分の挙動を変更 (delta spec で記述)
- `quality-line`: 字幕セグメンテーション品質 (項目 #7, #8) の合格基準を達成

## Impact

- **Backend**:
  - `subtitle.py:words_to_segments` の再実装 (~80 行)
  - `subtitle.py` に重複文字正規化 helper を追加 (~30 行)
  - 既存の助詞抑制リスト (`_trailing_particles`) は削除
- **テスト**: 既存の subtitle テスト全パス維持 + 新規 8-10 件
  - 句読点 flush
  - word gap flush
  - 文字数上限 (内部に句読点なし)
  - clamp word の独立保持
  - 重複文字正規化
- **処理時間**: 影響なし (subtitle 生成は元々 < 1 秒)
- **業務量産**: 字幕の可読性が劇的改善 → regression-bench Y flip の主要ブロッカー解除
