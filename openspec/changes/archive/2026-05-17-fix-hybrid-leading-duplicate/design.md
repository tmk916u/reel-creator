## Context

### `_hybrid_prepend_leading_words` (現状)
```python
def _hybrid_prepend_leading_words(third_words, first_stage_words_in_target, target_duration, ...):
    first_3rd_start = third_words[0]["start"]
    if first_3rd_start <= threshold:
        return third_words, 0
    cutoff = first_3rd_start - margin  # 0.1 秒のマージン
    leading = [w for w in first_stage_words_in_target if w["start"] >= 0 and w["end"] <= cutoff]
    leading.sort(key=lambda w: w["start"])
    return leading + third_words, len(leading)
```

### 観測されたバグ (job eabb58b3)
- `first_stage_words_in_target` の末尾: 「お客様が悩まれているダイエットの」 (cut2 内時刻 0-3.10)
- `third_words` の先頭: 「お客様が悩まれているダイエット」 (cut2 内時刻 3.10-6.70)
- `cutoff = 3.10 - 0.1 = 3.0` で leading に「お客様が悩まれているダイエットの」 (end ≤ 3.0) が含まれる
- 結果: leading + third で同じテキストが 2 連続出現

### 真因
- 1 段目 ASR (元動画) と 3 段目 ASR (cut2.mp4) が**同じ発話を異なる位置で** 認識
- 1 段目 word を `_filter_words_by_segments` で remap した時刻は、 3 段目で実測した時刻と一致しない
- 時刻が違うので margin だけでは弾けない → text レベルの dedup が必要

## Goals / Non-Goals

**Goals:**
- hybrid 補完の冒頭重複を解消
- 1 段目 word の有用な補完(本当に 3 段目が認識ミスした冒頭発話)は維持

**Non-Goals:**
- `_filter_words_by_segments` の remap 精度向上
- ReazonSpeech の認識精度向上

## Decisions

### D1: text レベルの subsequence dedup
```python
def _dedup_leading_against_third(leading, third, window=10):
    """leading の末尾と third の先頭が同じ text の sequence なら、 leading から削除。"""
    if not leading or not third:
        return leading
    n = min(window, len(leading), len(third))
    # 末尾から後ろ向きに最長 match を探す
    best = 0
    for k in range(1, n + 1):
        if [w["text"] for w in leading[-k:]] == [w["text"] for w in third[:k]]:
            best = k
    if best > 0:
        return leading[:-best]
    return leading
```

`_hybrid_prepend_leading_words` の末尾で:
```python
leading = _dedup_leading_against_third(leading, third_words)
return leading + third_words, len(leading)
```

**理由**: シンプルな text 完全一致で十分。 部分一致 (subword level) より誤検出が少ない。

### D2: window=10 に制限
- 1 段目補完の末尾 10 word と、 3 段目の先頭 10 word を比較
- 「お客様 / が / 悩 / ま / れ / ている / ダ / イ / エ / ット」 が 10 word でカバーできる範囲
- 短い動画でも 30 word 以上はあるので window=10 は適切

### D3: 完全一致のみ
- text の正規化 (空白除去、 句読点除去) は行わない
- ReazonSpeech の subword tokenization は両方の段で同じはずなので、 一致するなら厳密一致でよい

## Risks / Trade-offs

### R1: 偶然 leading の末尾と third の先頭が一致するが、 別発話のケース
**Mitigation**: 同じテキストの subword が **連続して N 個一致** する確率は極めて低い(window=10 で N=2 以上の連続一致を発火条件にできるが、 シンプルさのため 1 word でも match なら dedup)。 1 word の偶然一致(例: 句点「。」) でも、 1 word 程度の dedup なら影響は小さい

### R2: 1 段目補完の有用性が損なわれる
**Mitigation**: dedup は重複部分のみ削除。 純粋に 3 段目が認識できなかった範囲 (= 3 段目に無いテキスト) は補完として残る

## Migration Plan

1. `_dedup_leading_against_third` ヘルパー追加
2. `_hybrid_prepend_leading_words` で末尾呼出
3. テスト追加 (3 件): 完全重複 / 部分重複 / 重複なし
4. 統合: seitai_food.mov 再処理で eabb58b3 の症状再現と修正確認
