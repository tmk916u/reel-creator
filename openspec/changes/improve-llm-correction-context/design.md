## Context

### 現状の校正パイプライン (video.py Stage 5b 末尾付近)
```python
pre_correction_text = " ".join(s["text"] for s in sub_segments)
video_context, dynamic_corrections = summarize_with_mishearings(pre_correction_text)

# 1. 動画固有 + 静的辞書で text 置換
merged_corrections = {**dynamic_corrections, **corrections}
for seg in sub_segments:
    seg["text"] = apply_corrections_to_text(seg["text"], merged_corrections)

# 2. LLM 校正 (segment 単位で書き換え)
texts = [s["text"] for s in sub_segments]
corrected_texts = correct_transcript_segments(texts, video_context=video_context)
for seg, new_text in zip(sub_segments, corrected_texts):
    seg["text"] = new_text
```

### 観測される問題
- `dynamic_corrections` が「事への → の」 「悪い要 → 重要」 「ボメ → ボディーメイク」 を抽出していない (プロンプト不足)
- `correct_transcript_segments` が「客 事への 食」 (5 文字) を「お客様が」 (4 文字) に書き換えできない (長さ制約 -50%、 = 2.5 文字超必要)

## Goals / Non-Goals

**Goals:**
- 動画固有辞書で短い subword 断片を吸収できるよう、 LLM 抽出を強化
- 校正プロンプトの長さ制約を緩めて、 短い断片の大幅修正を許容
- 上記により業務量産での手動編集負荷を 50% 以上減らす

**Non-Goals:**
- 校正 LLM のモデル変更 (引き続き Haiku/gpt-4o-mini)
- segment 統合・分割の許可 (時刻整合性が崩れるため)
- 元動画 ASR 自体の精度向上

## Decisions

### D1: summarize_with_mishearings プロンプト強化
追加する例:
- 「短い subword 断片」: `{"wrong":"事への","right":"の"}` (「ダイエットの」 が subword 化)
- 「意味不明な並び」: `{"wrong":"ボメ","right":"ボディーメイク"}` (subword 大幅欠落)
- 「反義語的誤り」: `{"wrong":"悪い要","right":"重要"}` (音響近似の誤り)
- 「1 字目欠落」: `{"wrong":"こ律神経","right":"自律神経"}`

抽出上限を 10 個 → 15 個に緩和 (リスト解析量が増えるが、 適用対象が増える)。

### D2: correct_transcript_segments プロンプトの長さ制約緩和
- 旧:「各セグメントは元のセグメントの -50% 〜 +30% 程度の長さ」
- 新:「各セグメントは元のセグメントの -70% 〜 +50% 程度の長さ」

加えて文言追加:
- 「短い subword 列 (5 文字以下で意味が不明) は周辺の文脈から推測して、 意味の通る日本語に書き換えてください」

### D3: 長さチェック (実装側) も緩和
- 旧: `len(new_text) > max(int(len(original) * 2.0), len(original) + 10)`
- 新: `len(new_text) > max(int(len(original) * 2.5), len(original) + 15)`

これで 5 文字 → 12 文字、 10 文字 → 25 文字 の書き換えを許容。 統合は依然拒否される。

### D4: 既存 retry 機構との整合性
- `_CORRECTION_RETRY_PROMPT` (誤字のみ控えめ校正) は変更しない
- 長さ制約緩和で rejected が減るので、 retry の発動頻度も減る → 影響なし

## Risks / Trade-offs

### R1: LLM が過度に意訳して原意を失う
**Mitigation**:
- プロンプトに「**内容の主張・結論・数字は改変しない**」 を維持
- 長さ制約は緩めるが、 上限 +50% で過度な追加は抑制
- 既存の retry 機構 (rejected → 控えめ校正で再試行) が safety net

### R2: dynamic_corrections の誤抽出 (正しい text を誤認識と判定)
**Mitigation**:
- プロンプトに「文脈から明らかに誤りと判断できるもののみ」 を維持
- 「自信が無いものは含めない」 を強調
- 抽出後の `apply_corrections_to_text` は単純な文字列置換なので、 影響範囲が限定的

### R3: 既存テスト (test_llm.py) への影響
**Mitigation**:
- 既存テストは LLM 呼出をモックしているので、 プロンプト変更の影響なし
- 長さチェック緩和は test_llm.py で確認可能 (もしテスト対象なら更新)

## Migration Plan

1. `llm.py` のプロンプト 2 つを更新
2. `correct_transcript_segments` の長さチェック緩和
3. テスト確認 + 必要なら期待値更新
4. seitai_food.mov 再処理で 301574d9 相当の「客 事への 食」 が改善されるか確認
5. archive

### Rollback
`llm.py` 限定の変更。 git revert で完全に戻る。
