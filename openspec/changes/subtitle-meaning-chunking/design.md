## Context

### 既存の字幕生成パイプライン (subtitle.py)

- `words_to_segments(words, max_chars=12)` が word リストを ASS Dialogue にグループ化
- アルゴリズム: word を時刻順に走査し、 累積文字数が `max_chars` を超えたら flush
- 助詞抑制 (`_trailing_particles`): 行末が「は」「が」「を」 等で終わる場合は次 word を取り込んで延長
- 短セグメント統合 (`_merge_short_segments`): 0.6秒未満 or 5文字未満は前 segment に結合

### word 構造 (clamp 後)

```python
{
    "start": 33.06, "end": 33.18,           # clamp 後の short range
    "_orig_end": 45.14,                      # clamp 前 (オプション)
    "text": "お",
    "is_word_start": True,                   # ReazonSpeech の word 開始判定
}
```

clamp は `word.duration > 1.0s` の word に対して `word.end = word.start + 文字数/8` で適用される。 ASR ノイズで「お」「結」「目」 など 1 文字 word が大半の oversized 対象。

### 観測される破綻パターン

```
Dialogue 1: 様が悩まれているダエットをお
Dialogue 2: 様が悩まれているダ
Dialogue 3: イエットの食事への食
Dialogue 4: 事の話をしようと思います結
```

3 つの構造的要因:

1. **clamp で word.end が次 word.start とほぼ一致** → 自然な word gap が消える → どこで flush していいか判定不能
2. **同じ文の繰り返し** (元発話で「お客様が悩まれている」を 2 回言っている) → word が時系列で混在
3. **subword 単位の text** (「ダ」「イエット」 等) が独立 word として扱われ、 「ダ + イエット = ダイエット」 と統合する仕組みがない

## Goals / Non-Goals

**Goals:**
- 字幕 1 dialogue が「意味のかたまり」（句または短文）になる
- word の途中で改行されない (「ダ」 単独行を排除)
- 句読点直後で flush する基本原則を維持
- 助詞末尾抑制ロジックを段階的に廃止し、 word gap で判断

**Non-Goals:**
- リアルタイム字幕生成 (バッチ処理のみ)
- 字幕の意味的書き換え (要約・パラフレーズ) → LLM coherence pass の責務
- 重複フレーズ統合 (「お客様が悩まれている」 2 回問題) → 別 change `short-distance-redundancy-merge` で扱う
- 動画の冒頭組み替え (リール hook 化) → 別 change `reel-hook-extraction` で扱う

## Decisions

### D1: chunk 境界の優先順位

```
1. 強境界 (必ず flush): 句読点「。」「、」「!」「?」 で終わる word の直後
2. 中境界 (flush): word 間 gap ≥ 0.4 秒 (発話の間 = 意味の区切り)
3. 弱境界 (条件付き flush): chunk 内文字数 ≥ 12 かつ、 次 word が新たな文節開始
```

**判定順**: 1 → 2 → 3。 1 で flush なら 2, 3 は評価しない。 3 は 1, 2 で flush されなかった長文の補助。

### D2: word gap 閾値 0.4 秒

- 通常の発話間: 0.05-0.15 秒 (息継ぎ・連続発話)
- 意図的なポーズ: 0.3-0.8 秒 (文の切れ目)
- 0.4 を境界にすれば「文の自然な区切り」を捕捉できる
- gap 計算は `word.end → 次 word.start` (clamp の影響を受ける場合は `_orig_end` を優先)

### D3: clamp 済み word の扱い

clamp 済み word (`_orig_end` を持つ) は **単独 chunk として独立**:
- 中身の text が 1 文字程度で意味不明 (例: 「お」 = 「お客様が悩まれている...」 の subword 推定ミス)
- 他 word と結合すると「様が悩まれているダ」 のような誤った chunk になる
- → 1 word = 1 dialogue で隔離し、 短い dialogue として残す or 後処理で削除

### D4: 重複文字正規化

ASR ノイズで「ほほとんど」「めめんたる」 のような連続重複文字が出る:

```python
def _normalize_repeated_chars(text: str) -> str:
    # 同じ文字が 2 連続 → 1 文字に圧縮 (3 連続以上は意図的な強調として保持)
    # 例: 「ほほとんど」 → 「ほとんど」
    return _re.sub(r'(.)(?=\1)(?!\1\1)', '', text)
```

辞書照合は今回スコープ外 (別 change `asr-text-normalization` で扱う)。

### D5: 既存 `_trailing_particles` 抑制リストの廃止

新方針では word gap と句読点で chunk 境界を決めるため、 助詞末尾抑制は不要 (副作用で過剰結合を引き起こす場合もある):

- 旧: 「は」「が」 で終わる → 次 word を取り込む
- 新: 「は」「が」 の次に word gap < 0.4 秒 かつ chunk 文字数 < 12 なら自然に取り込まれる
- gap が大きければ独立 chunk として残す方が「文の区切り」として正しい

### D6: 1 dialogue の文字数下限・上限

- 下限: 2 文字 (1 文字 dialogue は他 word と統合を試みる)
- 上限: 20 文字 (D1 の弱境界閾値 12 を超えても文構造を壊さないため柔軟に)
- ASS は max 1-2 行表示なので、 20 文字超は視覚的に圧迫感あり

### D7: 既存のキーワードハイライトは保持

`apply_keyword_highlight` の挙動は変更しない。 chunk 内に keyword があれば `<font>` タグ付与。

## Risks / Trade-offs

### R1: word gap 0.4 秒が音響的特性に左右される

**Mitigation**: 設定可能パラメータとして `settings.subtitle_chunk_gap_threshold` を追加 (デフォルト 0.4)。 ベンチで調整。

### R2: clamp word が 1 文字 dialogue として大量発生

**Mitigation**: D3 の隔離 + 後処理で「1 文字 dialogue を _orig_end まで延長して表示時間を確保」 を検討。 ただし 1 dialogue 1 文字でも視聴時間 0.1-0.5 秒なら気にならない。

### R3: 既存テストが助詞末尾抑制を前提に書かれている

**Mitigation**: 既存 8 テスト分析 → 助詞末尾抑制を直接 assert するテストは 2 件のみ。 新方針で同等品質を満たすケースとして書き換える。

### R4: 「意味のかたまり」 判定が日本語特有

**Mitigation**: 今回は日本語限定 (整体・健康ドメインがターゲット)。 多言語対応は将来 change で。

## Migration Plan

### Phase 1: 重複文字正規化 helper 追加 (30 分)
1. `subtitle.py` に `_normalize_repeated_chars` 追加
2. テスト 3 件 (「ほほとんど」「めめんたる」 等の正規化)
3. `words_to_segments` 入口で word.text に適用

### Phase 2: 新 chunking ロジック実装 (1.5 時間)
1. `words_to_segments` を新方針で書き直し
2. 強・中・弱境界の判定ロジック
3. clamp 済み word の独立処理
4. テスト 6-8 件追加 (句読点 flush, gap flush, 弱境界, clamp 隔離, 文字数下限)

### Phase 3: 旧助詞抑制廃止 (30 分)
1. `_trailing_particles` と関連ヘルパーを削除
2. 既存テスト 2 件を新方針で書き換え (or 削除)
3. 全 subtitle テストパス確認

### Phase 4: 統合 + 検証 (1 時間)
1. 同 input.mp4 を再処理
2. 字幕 dialogue を目視確認 (「様が悩まれている」「結から言うと」 等の破綻がないか)
3. regression-bench.md に新結果を追記 (Y/N 評価は手動)

### Rollback
`subtitle.py` のみ変更。 git revert で完全に戻る。 設定で旧挙動に戻す scoring は今回作らない (新方針が劣化なら revert する)。
