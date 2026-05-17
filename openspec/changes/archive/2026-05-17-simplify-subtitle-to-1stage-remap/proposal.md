## Why

過去 4 ヶ月の字幕生成戦略がイタチごっこに陥っている:

```
旧: 1段目 primary + 2段 remap → subword 語順崩壊 ❌
  ↓ fix-subtitle-word-order-collapse (Stage 5b で 3段目 transcribe)
3段目: 冒頭 36 秒字幕無し ❌
  ↓ fix-asr-aware-silence-protection (silero VAD 補正)
発話保護はできたが 3段目 ASR 認識ミス残る ❌
  ↓ fix-third-stage-asr-leading-miss (1段目で hybrid 補完)
hybrid: 二重表示 ❌
  ↓ fix-hybrid-leading-duplicate (dedup)
dedup: leading 全削除で重要発話消失 ❌ ← 現在地 (job 0ca6b31b)
```

**真因**:
- 1段目 ReazonSpeech (元動画 250 秒 context): テキスト品質 ◎、 timestamp ⚠
- 3段目 ReazonSpeech (cut2 84 秒 context): テキスト品質 ⚠ (subword 断片化)、 timestamp ◎
- 中間状態 (cut.mp4 内時刻) を経由する 2 段 remap が順序崩壊の元凶
- 3 段目 transcribe を導入したが、 短い context での認識品質が低い

**実例 (job 0ca6b31b 100.8 秒)**:
- 3 段目 出力: 「客 事への 食事の話をしよう…」 ← subword 断片
- 1 段目 出力 (remap 候補): 「お客様が悩まれているダイエットの食事の話をしようと思います」 ← 完璧
- hybrid 補完が「first_3rd_start <= threshold」 で発動せず、 3 段目の断片だけ字幕に出る → 業務量産投入できない品質

## What Changes

字幕生成戦略を **1 段目 ASR + 1 段 remap (合成マッピング)** に統一:

- **削除**:
  - Stage 5b の 3 段目 transcribe (cut2.mp4 を transcribe する処理)
  - `_hybrid_prepend_leading_words` ヘルパー
  - `_dedup_leading_against_third` ヘルパー
- **新規追加** (silence.py):
  - `build_orig_to_cut2_mapping(voice_segments, cut2_voices)`: 元時刻 → cut2 内時刻 の 1 段マッピング table を構築 (voice_segments と cut2_voices を **合成**)
  - `remap_words_with_mapping(words, mappings)`: word を mapping table で 1 段 remap
- **Stage 5b 改修** (video.py):
  - 字幕用 words = 1 段目 ASR words を build_orig_to_cut2_mapping で 1 段 remap
  - cut2.mp4 未生成 (施策F 未発動) なら、 voice_segments のみで remap (cut2 部分なし)
- 既存の `_filter_words_by_segments` は施策G 判定用に維持(役割が違う)

旧崩壊の真因は中間状態経由の 2 段 remap。 1 段に統合することで:
- 中間状態を経由しない → 順序崩壊リスクなし
- 1 段目 ASR の高品質テキストを活かせる
- 3 段目 transcribe を廃止 → 処理時間 -30〜60 秒
- hybrid / dedup ロジックを削除 → コード簡素化

## Capabilities

### Modified Capabilities
- `quality-line`: 字幕生成戦略を spec レベルで MODIFIED

## Impact

- **Backend**:
  - 追加: silence.py に 2 関数 (約 50 行)
  - 簡素化: video.py の Stage 5b (約 80 行 → 30 行)
  - 削除: video.py の hybrid/dedup ヘルパー 2 つ (約 60 行)
- **テスト**: 既存 127 件 → 一部 obsolete テスト削除、 新規追加で約 同数を維持
- **処理時間**: -30〜60 秒/動画 (3 段目 transcribe 廃止)
- **業務量産**:
  - 0ca6b31b の 「客 事への」 → 「お客様が悩まれているダイエットの食事の話をしようと思います」 に改善期待
  - 14 本連続処理での ReazonSpeech 連続呼出回数が減る(state leak の遭遇率も低下)
- **副作用リスク**:
  - 1 段目 ASR の認識ミス (「威勢→姿勢」 など) が字幕に出やすくなる
  - LLM 校正 + 動画固有辞書で吸収する設計を維持
