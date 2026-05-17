## Why

`establish-quality-line` のベースライン測定(seitai_food.mov / job `d8d062dc`)で、 字幕の冒頭 3 行が **subword レベルで語順崩壊** していることが判明:

```
1: 様が悩まれているダイエットお客     ← 「お客」が末尾に飛んでいる
2: 様事への食                        ← subword 残骸
3: 事の話をしようと思います。          ← 前段と続いてやっと正常
```

業務量産品質ライン (`openspec/specs/quality-line/spec.md`) で:
- #5 字幕の誤認識 ❌
- #6 字幕タイミング同期 ❌ (18 件で 0.5 秒超のずれ)

が不合格になっており、 **業務量産投入の致命的ブロッカー**。

直前の `1段目 primary` 戦略(commit b218159) でも崩壊しており、 単なるロジック調整では救えない。 ReazonSpeech 1段目 transcribe の subword 出力を `_filter_words_by_segments` で **2 段 remap** している構造そのものに無理があるため、 **構造変更** で根治する。

## What Changes

- 動画処理パイプラインの **Stage 5 (字幕生成)** を **Stage 5a + 5b** に分割
  - **Stage 5a**: cut.mp4 transcribe (2段目) → 施策F/G で `oversized_2nd` 検出 → cut2.mp4 生成(既存パスを維持)
  - **Stage 5b** (新規): **cut2.mp4 を 3段目 transcribe** → 字幕用 words を取り直し → words_to_segments → ASS 生成
- 字幕用 words の生成方針を変更:
  - 旧: 1段目 words を 2 段 remap(元時刻 → cut.mp4 → cut2 時刻)
  - 新: **cut2.mp4 を直接 transcribe** → cut2 内時刻の words がそのまま得られる
- `_merge_word_streams` ヘルパー (commit a1f12af で導入、 b218159 で運用停止)を **削除** または **deprecated** に
- 1段目 + 2段目 ASR は **動画カット判定にのみ** 使用(`detect_oversized_words`, 施策G の OR 判定)。 字幕生成からは切り離す
- BREAKING: なし(API 不変、 内部実装の変更のみ)
- 処理時間: ReazonSpeech 推論 1 回追加で **+30-60 秒**(モデルはキャッシュ済みなのでロード時間は無視可能)

## Capabilities

### New Capabilities
なし(既存パイプラインの内部変更)

### Modified Capabilities
- `quality-line`: 項目#5, #6, #7, #8 の合格率改善を実証する。 spec の Requirement 内容は変えず、 ベースラインの数値を更新

## Impact

- **Backend**:
  - 変更: `backend/app/routers/video.py` `_run_processing` の Stage 5 を 5a/5b に分割。 約 30-50 行の書き換え
  - 変更: `_filter_words_by_segments` の字幕用呼び出しを削除(動画カット判定用は維持)
  - 廃止 or deprecated: `_merge_word_streams`(用途消滅)
- **Frontend**: 影響なし(API 不変)
- **テスト**:
  - 既存 105 件は維持
  - 新規 1-2 件: 「Stage 5b で 3段目 transcribe が呼ばれる」モックテスト
- **処理時間**: 5 分動画で +30-60 秒(週 14 本量産時に +7-14 分/週)
- **ベースライン**: 本 change 完了後、 seitai_food.mov を再測定して `baseline.md` を更新
- **既存機能との互換性**: 100% (動画出力・字幕出力の形式は変わらず、 品質が向上する)
- **後続 change**: 残る不合格項目(特に #7 / #8)は `fix-subtitle-segmentation-quality` として別 change で対応
