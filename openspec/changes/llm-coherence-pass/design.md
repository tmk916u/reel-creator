## Context

既存パイプラインは複数の独立検出器を直列に並べる構造:

```
silence → filler → restatement (chunked LLM) → tempo cut → far-distance redundancy → merge → cut
```

各検出器は「特定パターン」を見つけて削除区間を出す。だが**「すべての検出が終わった後の transcript が日本語として意味が通っているか」を判定するレイヤーは存在しない**。

回帰ベンチ 4 本のうち 3 本が「ストーリー崩壊」で却下されており、出力動画の再 ASR でも自己訂正・同義反復残存・文脈破綻が確認できる。`detect_restatements` を強化する（プロンプト改善・few-shot 追加）アプローチは「過去 3 日前に同じことをやって失敗した路線」であり、信用に値する打ち手にならない。

「**最終 transcript の意味整合性を判定する別アーキテクチャ**」を導入することが本 change の本質。同じ LLM でも「言い直しを探す」と「意味が通る最小集合を返す」は別タスクで、別プロンプト・別呼出として独立させる。

## Goals / Non-Goals

**Goals:**

- カット後の transcript が日本語として論旨を保てるよう、追加レイヤーで意味整合性を判定する
- 既存検出器を一切変更しない（並列ではなく追加レイヤー）
- フラグでデフォルト OFF。ロールアウトを段階制御可能
- Dry-run モードで本適用前に削除候補を目視可能
- 暴走ガードで「重要発話を全部消す LLM」のリスクを構造的に抑える

**Non-Goals:**

- 既存 `detect_restatements` の置き換え・改修
- ASR 精度向上（字幕誤字・gibberish 等）
- 音量正規化（別 change で扱う）
- 映像系の磨き（カラグレ・クロスフェード）
- 文書要約・並び順最適化（時系列維持）
- 部分的ロールバック（LLM が一部失敗した場合、当該チャンクだけスキップ）

## Decisions

### Decision 1: 挿入位置 — 既存検出群の後段、`merge_ranges` の前

既存検出（filler / restatement / tempo / far-distance redundancy）が `extra_cuts` を作る → これらを既存 `merge_ranges` で統合 → **その統合結果から「カット後の生存 word 列」を再構築** → コヒーレンスパスに渡す → 追加削除候補を得る → 元の `extra_cuts` に append → 再度 `merge_ranges` で統合。

**代替案**:

- 並列実行（既存検出と同時に LLM を呼ぶ）: 既存検出が消す部分を考慮できず、効果が薄れる
- 字幕生成後（最終 SRT に対して）: word timing がフォーマット変換で失われがちで実装複雑

### Decision 2: 入力 — 生存 word 列 + timing のみ（embedding 不使用）

LLM への入力は既存検出後に「生き残った word」だけのリスト。各 word は `{text, start, end}`。confidence は **オプション**（faster-whisper の `word.probability` があれば付ける、なければ省く）。embedding は使わない（本 change のスコープ外）。

理由:

- LLM だけで意味整合性は判定可能（タスクと一致）
- embedding 導入は別の依存と別の検証コストを伴う

### Decision 3: 出力 — 削除候補 + 理由 + 信頼度の構造化 JSON

```json
{
  "deletions": [
    {"start": 47.32, "end": 53.18, "reason": "「ここで一番大事なのは」が直前と重複し、自己訂正の中間状態が残っている", "confidence": 0.85}
  ],
  "summary": "全体としては論旨は通るが、47-53秒で自己訂正の前半が残り文脈が破綻"
}
```

LLM 応答スキーマは Pydantic で validate。スキーマ違反は warning ログを残してスキップ（失敗扱いではない）。

### Decision 4: 暴走ガード — 削除総時間 ≤ 元の 30%

LLM が返した削除候補の合計時間が、入力 word 列の総尺の 30% を超えた場合、その応答**全体を破棄**（部分採用しない）。30% は経験則の安全値。

加えて:

- 最小残存 word 数チェック: 削除後に残る word が元の 50% 未満なら破棄
- 連続削除区間が 8 秒を超える場合は当該削除候補のみドロップ（部分破棄）

**代替案**:

- 信頼度フィルタのみ: LLM が一貫して高信頼を返した場合に止められない
- 上限なし: テスト時に致命的な暴走を起こすリスク

### Decision 5: Dry-run モード必須

環境変数 `LLM_COHERENCE_PASS_DRY_RUN=1` で動作:

- LLM は呼ばれる
- 削除候補は得る
- ただし `extra_cuts` には**追加しない**
- 削除候補を `{tmp_dir}/coherence_dryrun_{job_id}.json` にダンプ
- ジョブログにも `logger.info` で出力

これにより 4 本の回帰ベンチを通して**実カットなしで削除候補を目視確認**できる。本適用前に必須のステップ。

### Decision 6: 機能フラグ `ENABLE_LLM_COHERENCE_PASS`（デフォルト OFF）

環境変数で全体 ON/OFF。Dry-run は ON 時のみ意味を持つ（OFF だと LLM すら呼ばない）。

| ENABLE | DRY_RUN | 挙動 |
|---|---|---|
| 0 | -  | LLM 呼ばれない（完全に従来通り） |
| 1 | 0 | LLM 呼ばれて削除実行 |
| 1 | 1 | LLM 呼ばれるが削除実行されない（ダンプのみ） |

### Decision 7: 長尺は chunked-restatement-detection と同じ分割戦略

総尺 60 秒未満なら単一呼出、60 秒以上なら 90 秒チャンク・15 秒オーバーラップ。`_split_words_into_chunks` は既存実装を**再利用**（既に `llm.py` に存在）。重複削除候補は `merge_ranges` で統合される。

### Decision 8: LLM 失敗時はフォールバック（FAILED にしない）

LLM 不通・タイムアウト・スキーマ違反・暴走ガード作動はすべて `logger.warning` で記録し、コヒーレンスパスの結果を**空リストとして扱う**。既存検出の結果はそのまま採用される。これにより本 change がパイプライン全体の SLA を下げない。

### Decision 9: 合格基準は回帰ベンチの flip 数のみ

単体テストは PR マージのための gate ではなく、デバッグ用の sanity check として実装する。本 change の「効くか」の判定は `.planning/intel/regression-bench.md` の 4 本での flip 数だけが信用に値する指標（`proposal.md` に明記済み）。

### Decision 10: プロンプト構造

```
あなたは日本語動画編集の校正アシスタントです。
以下は字幕用 transcript の word 列です。すでに無音削除と言い直し検出を経て、いま残っている発話です。

各 word: index, text, start, end

タスク: この transcript を「日本語として意味が通る最小のサブセット」にしたい場合、削除すべき word の連続範囲を返してください。

判定基準:
1. 同じ意味を 2 回以上言っている箇所 → 後の方を残す
2. 自己訂正の中間状態（直後に言い直しているのに残っている） → 中間状態を削除
3. 文脈が前後と繋がらず浮いている発話 → 削除
4. 結論や具体例を補強する重要発話は残す
5. 削除候補の合計時間は入力総尺の 30% 以下に抑える

出力は JSON:
{"deletions": [{"start": float, "end": float, "reason": string, "confidence": 0.0-1.0}], "summary": string}

word 列:
[{"i": 0, "t": "お客様", "s": 0.12, "e": 0.45}, ...]
```

few-shot は **入れない**（既存 detect_restatements で few-shot 路線は失敗実績あり）。プロンプト指示そのものを明示的に書く。

## Risks / Trade-offs

| リスク | 緩和策 |
|---|---|
| LLM が重要発話を消す | 暴走ガード（30%・最小残存・連続8秒）、dry-run 必須 |
| レイテンシ +5〜15 秒 | フラグでデフォルト OFF。本適用は社内アカウント向けなのでレイテンシは許容 |
| 既存検出と二重削除 | `merge_ranges` で統合されるので機能上は問題なし。重複信号はログで確認可能 |
| LLM コスト増 | 1 ジョブあたり追加 +1〜4 呼出。社内用途で月数十本想定なら無視可能 |
| プロンプトが日本語特有 | 多言語拡張時に再設計必要 → 別 change で対応 |
| dry-run の評価コスト | 4 本だけなので 1 回 20-30 分で完了する想定 |

## Migration Plan

1. **コード実装** — フラグ OFF でデプロイ可能。既存挙動は変わらない
2. **dry-run 検証** — `ENABLE_LLM_COHERENCE_PASS=1 LLM_COHERENCE_PASS_DRY_RUN=1` で 4 本処理。`coherence_dryrun_*.json` を目視。明らかな誤削除があればプロンプト調整
3. **本適用** — `LLM_COHERENCE_PASS_DRY_RUN=0` で 4 本再処理 → 新出力を盲検評価 → flip ≥ 2 確認
4. **合格しない場合** — フラグ OFF に戻す。プロンプトかガード値を調整 → step 2 へ
5. **ロールバック** — 環境変数を OFF にするだけ（コード変更不要）

## Open Questions

- **Q1**: dry-run の出力 JSON はどこに置くか？  
  → `job_dir/coherence_dryrun.json`（既に存在する `transcript_words.json` と同階層）
- **Q2**: 削除総時間ガードの 30% は妥当か？  
  → 初期値。dry-run で 4 本見て調整余地あり。明確な数字を入れることが大事
- **Q3**: 既存 `detect_restatements` の chunked 化はそのまま並行運用か？  
  → そのまま並行運用。本 change は追加レイヤーであって置き換えではない
