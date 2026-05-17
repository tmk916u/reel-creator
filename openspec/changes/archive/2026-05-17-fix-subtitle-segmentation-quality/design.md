## Context

### 現在の words_to_segments のロジック (subtitle.py L29-123)

```python
def words_to_segments(words, max_chars=18, max_gap=0.6, ...):
    hard_limit = max(int(max_chars * 1.5), max_chars + 4)
    _trailing_particles = set("はがをにでとのもへやかな")
    for w in words:
        over_chars = len(current_text) + len(text) > max_chars
        over_hard = len(current_text) + len(text) > hard_limit
        ends_with_particle = (current_text and current_text[-1] in _trailing_particles)
        should_flush_before = current_words and (
            gap > max_gap
            or (over_chars and is_word_start and not ends_with_particle)
            or over_hard
        )
        if should_flush_before: flush()
        current_words.append(w); current_text += text
        if text and text[-1] in "、。！？!?.":
            flush()
    # ...
    segments = _dedupe_adjacent_overlaps(segments)
    segments = _merge_short_segments(segments, min_dur=0.6, max_chars=max(max_chars, 24))
```

### 観測 (job f4703bef, tight preset max_chars=10)

短い Dialogue (1-7 文字) が頻発する典型例:
- 「メンタルです。」 (6 文字、 「、」 直前で flush)
- 「客」 (1 文字、 hybrid 補完先頭)
- 「ただ、」 (3 文字、 「、」 で flush)
- 「実際にそのとおりできる方」 → 「うえで実際にそのとおりできる方」「っていうのはほとんどいません。」 のように 14 文字超

助詞直後切れの典型:
- 「結論から言うと一番大事なのは」 → 「は」 で flush
  - `_trailing_particles` には「は」 が含まれるはずだが、 max_chars 10 を超えても hard_limit 15 を超えるとflush
  - 実は「のは」 の段階で hard_limit (15) 内、 だが over_chars True で flush 候補。 「は」 が末尾 → flush 抑制。 確認必要

実は表面的には抑制ロジックは機能している。 問題は:
1. `_trailing_particles` に「て」「で(接続)」「ば」「し」 等が抜けている
2. 「、」 で flush するため、 「、」 直前の長い文 + 「、」 直後の短い断片 という pattern 多発

## Goals / Non-Goals

**Goals:**
- #7 助詞直後切れ < 10%
- #8 字幕 8-14 文字比率 ≥ 70%
- 全体合格率 9/14 → 11/14

**Non-Goals:**
- 字幕の文章校正(LLM 校正は別ロジック)
- 字幕表示時間の調整 (lead_time / tail_time)
- 字幕のフォントや色

## Decisions

### D1: `_trailing_particles` の拡張
- 追加: 「て」「ば」「し」「ず」
- 削除候補: 無し(既存 11 文字は維持)
- 接続助詞「から」「ので」「のに」「けど」 は 2-3 文字なので、 末尾 2 文字でチェックする `_trailing_particle_phrases` を別途追加

**理由**: 「て / ば / し / ず」 は活用語尾で文が続くことが多い。 「これして、 あれして」 のようなパターンで切れるのを防ぐ。

### D2: 「、」 では flush しない
- 旧: `if text and text[-1] in "、。！？!?.":`
- 新: `if text and text[-1] in "。！？!?.":` (「、」 を除外)

**理由**: 「、」 は日本語の中で柔軟な区切り。 字幕でも「、」 で切らずに、 max_chars/句点で切る方が読みやすい。 「、」 で切ると短い Dialogue が量産される。

### D3: `_merge_short_segments` の閾値変更
- min_chars (新規): 8 文字。 これ未満は積極的に統合
- max_chars (合計上限): `max(max_chars * 1.4, 14)` = max_chars=10 なら 14。 max_chars=18 なら 25
- 句点で終わっている場合は依然として統合しない (文の境界)

**理由**: 8 文字未満を「短すぎる」と定義し、 隣接が句点で終わっていなければ統合。 max_chars × 1.4 まで結合許容することで 8-14 範囲に Dialogue を集めやすい。

### D4: hard_limit はそのまま
- `hard_limit = max(int(max_chars * 1.5), max_chars + 4)` を維持
- max_chars=10 → hard_limit=15

**理由**: 強制 flush の上限は変えない。 _trailing_particles 拡張と「、」 緩和で flush タイミングを調整するだけ

## Risks / Trade-offs

### R1: 過剰統合で 1 Dialogue が 15 文字超になる可能性
**Mitigation**: hard_limit (15) は維持。 統合後も `len <= max_chars * 1.4` の上限を守る

### R2: 「、」 で切らないと、 「、」 を含む長い文が連続表示される
**Mitigation**: hard_limit と「、」直後の助詞抑制で間接的にコントロール。 体感は再測定で確認

### R3: 拡張助詞「て」「ば」 で flush 抑制が効きすぎて、 文が一向に切れない
**Mitigation**: hard_limit (15) で必ず強制 flush するので無限延長は起きない。 max_gap (0.6 秒) でも切れる

### R4: 既存テスト 115 件への影響
**Mitigation**: words_to_segments と _merge_short_segments の境界変更は既存テストに影響しうる。 影響範囲を確認し、 必要に応じて期待値を更新する

## Migration Plan

### 段階 1: 実装
1. `_trailing_particles` を拡張
2. flush 句読点セットから「、」 を除外
3. `_merge_short_segments` の min_chars=8 ロジックを追加

### 段階 2: テスト
1. 既存 115 件 PASS 確認(変更が出れば期待値を調整)
2. 新規テスト:
   - 接続助詞「て」 末尾で flush 抑制
   - 「、」 直後で flush されない
   - 8 文字未満の Dialogue が次と統合される
   - max_chars × 1.4 を超えた段階で強制 flush

### 段階 3: ベースライン再測定
1. seitai_food.mov 再処理
2. measure_quality → #7 #8 の改善を確認
3. 字幕の冒頭 5 Dialogue を目視

### Rollback
subtitle.py 限定の変更。 git revert で完全に戻る。

## Open Questions

- **Q1**: `_trailing_particle_phrases` (2-3 文字パターン) は本 change で実装?
  - **暫定方針**: No。 まず単一文字拡張で効果を測定。 必要なら次の change
- **Q2**: max_chars × 1.4 の係数は妥当?
  - **暫定方針**: 1.4。 既存 hard_limit 1.5 より少し小さく、 過剰統合を抑える
