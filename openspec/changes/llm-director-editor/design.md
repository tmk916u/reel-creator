## Context

### 既存パイプライン (rule_based)

```
transcribe → silence + jump_cut + coherence → 削除候補 merge → cut_and_concat
```

各レイヤーが独立に「これは削るべき」 を判断 → 残りを時系列順に繋ぐ。 動画の **順序は維持** され、 ストーリー的な再構成は行わない。

### 既存 LLM 利用箇所

- `summarize_with_mishearings`: 動画の文脈サマリー + 動画固有の誤認識辞書 (Stage 3 前)
- `detect_coherence_violations`: 言い直し検出 (Stage 3 後、 削除候補に追加)
- `detect_restatements`: 言い直し検出 (chunked)
- `generate_hook`, `detect_topics`, `select_bgm_style`, `generate_captions`, `predict_buzz_score`

LLM provider は環境変数 `LLM_PROVIDER=openai|anthropic` で切替、 既存基盤を再利用する。

### transcript の構造

```python
segments: [{start, end, text}]  # ASR 出力の文単位
words: [{start, end, text, is_word_start?}]  # word-level
```

director に渡すのは `segments` + `words`。 segments は LLM が読みやすい (文単位 + 時刻)、 words は最終的な切り出し範囲の word boundary snap に使う。

## Goals / Non-Goals

**Goals:**
- 雑撮り動画 (台本なし、 言い直し多い、 拡散した内容) でもリール品質を出す
- 字幕ブツ切れ・冒頭弱・重複未統合 を構造的に解決
- 既存パイプラインを壊さない (rule_based モードは無変更)
- LLM 失敗時は既存にフォールバック (degraded mode)

**Non-Goals:**
- 動画の映像解析 (シーン変化、 表情検出) → 将来別 change
- リアルタイム処理 (バッチのみ)
- 多言語対応 (日本語のみ)
- LLM の自己評価ループ (生成結果を別 LLM で評価) → 将来別 change

## Decisions

### D1: LLM Provider と Model

- Provider: 既存 `LLM_PROVIDER` 環境変数を踏襲 (openai or anthropic)
- Model: 構造化出力に強い model を使用
  - OpenAI: `gpt-4o` または `gpt-4o-mini` (JSON mode 対応)
  - Anthropic: `claude-sonnet-4-6` (tool use または system prompt で JSON 強制)
- 既存の coherence pass と同じ設定を再利用

### D2: prompt 構造

#### System role
```
あなたは TikTok/Instagram Reels の動画編集 AI ディレクターです。
整体院の話者が話す動画 transcript を読み、 30〜60 秒の縦動画リールに
再構成してください。

リール構造の原則:
1. HOOK (冒頭 0-3 秒): 結論または強いメッセージ。 必ず先頭に置く
2. REASON (3-30 秒): 結論の理由・根拠を 1-2 個
3. EXAMPLE (30-50 秒): 具体例・体験談 (オプション)
4. CTA (50-60 秒): 行動喚起・締めくくり

削除すべき発話:
- 言い直し、 噛み、 フィラー
- 同じ内容の繰り返し
- 結論につながらない雑談
- 30 秒以上の冗長な説明

返り値は **必ず JSON** で、 transcript 内の時刻範囲を指定すること。
範囲外の時刻や、 transcript にない発話を含めてはいけない。
```

#### User role
```
以下は整体院動画の transcript です。
目標尺: {target_duration} 秒 (40〜80 秒の範囲で動画の内容次第)

[動画文脈]
{video_context}  # summarize_with_mishearings の出力

[transcript (segment 単位、 時刻付き)]
1. [20.65-31.90] 皆さんが悩まれているダイエットの食事についての話をしようと思います
2. [31.91-54.06] 結論から言うと
3. [54.07-65.18] 一番大事なのはメンタルです。目標に向けて食事をどうしていくか考えたうえで
...

各 segment は ASR の自動セグメンテーションで、 内部に複数の発話を含む場合があります。
clips は segment より細かい粒度 (word level) で指定できます。

出力 JSON:
{
  "clips": [
    {"start": float, "end": float, "role": "hook"|"reason"|"example"|"cta",
     "order": int, "text": str}
  ],
  "summary": "全体の構成意図を 1 文で"
}
```

### D3: 出力 schema と検証

```python
class Clip(TypedDict):
    start: float  # transcript の最小時刻 ≤ start < end ≤ 最大時刻
    end: float
    role: Literal["hook", "reason", "example", "cta"]
    order: int  # 動画内で表示する順序 (1, 2, 3, ...)
    text: str  # 該当区間の発話 (LLM が伝える意図、 表示には使わない)
```

検証ルール:
- start < end
- 範囲 [transcript_min, transcript_max] 内
- order が連番 (1, 2, ...) かつ重複なし
- clips の合計尺が 30 ≤ total ≤ 90 秒
- 不正な clip は破棄 (warning ログ)
- 全 clip が破棄されたら → フォールバック (rule_based)

### D4: 順序入れ替えと動画の自然さ

LLM は order で並び替えを指定できる。 整体院動画は **話者がほぼ静止** なのでジャンプカットが目立たない (背景・服装の変化なし)。 ただし:

- 同じ role 内では時系列順を維持する規則を prompt で指定
- 異なる role 間 (hook → reason 等) は入れ替え可

将来的に映像のシーン変化検出を入れて、 動きがある場面は入れ替え禁止にする (別 change)。

### D5: word boundary snap

LLM が指定する [start, end] は文意ベースで、 word 境界とは限らない。 切り出し時に word の境界 (word.start / word.end) に snap する:

```python
def snap_clip_to_words(clip, words):
    # clip.start に最も近い word.start (clip.start 以前) を使う
    snapped_start = max((w["start"] for w in words if w["start"] <= clip["start"]), default=clip["start"])
    # clip.end に最も近い word.end (clip.end 以後) を使う
    snapped_end = min((w["end"] for w in words if w["end"] >= clip["end"]), default=clip["end"])
    return {**clip, "start": snapped_start, "end": snapped_end}
```

### D6: 字幕生成

director mode では word を直接 ASS/SRT に変換:
- 各 clip 内に含まれる word を抽出
- 既存の `words_to_segments` でチャンク化 (順序は clip.order に従う)
- clip 跨ぎの結合は禁止 (clip 境界で必ず flush)

### D7: フォールバック挙動

director フローが失敗するケース:
- LLM API エラー / timeout
- LLM 応答が JSON 不正
- 全 clip が範囲外で破棄
- clips の合計尺が範囲外

→ 既存の rule_based パイプラインに切替えて処理続行。 warning ログ + job.message に「director失敗のため標準モードで処理」 を追記。

### D8: フロントエンド UI 設計

最初のステップ (動画アップロード後の設定画面) に **編集モード選択** を配置:

```
┌─────────────────────────────────────┐
│  動画アップロード ✓                  │
│                                     │
│  編集モードを選択 *                  │
│  ┌─────────────────────────────┐    │
│  │ ⚪ ✂️ 標準モード              │    │
│  │    不要な間とフィラーを削除    │    │
│  │    [推奨: 台本ありの撮影]     │    │
│  ├─────────────────────────────┤    │
│  │ ⚪ 🎬 AI 監督モード Beta      │    │
│  │    LLM がストーリー再構成     │    │
│  │    [推奨: 雑撮り、 言い直し多] │    │
│  └─────────────────────────────┘    │
│                                     │
│  [字幕] [BGM] [尺]  ...             │
└─────────────────────────────────────┘
```

実装は既存の `ProcessingPanel` or `ProcessRequest` 編集 UI に追加。 デフォルトは「標準モード」 で、 ユーザーが明示的に切り替える設計。

## Risks / Trade-offs

### R1: LLM の確率的揺らぎ (同じ動画でも結果が変わる)
**Mitigation**: temperature=0 で安定化。 失敗時 retry 1 回。

### R2: LLM が transcript にない発話を出力 (hallucination)
**Mitigation**: D3 検証で範囲外を破棄。 text フィールドは表示に使わず時刻だけ信頼。

### R3: 順序入れ替えで動画が不自然
**Mitigation**: D4 で同 role 内は時系列維持。 整体院動画は静的なので影響小。 ベンチで判定。

### R4: LLM コスト増加 (1 動画 +$0.05-0.10)
**Mitigation**: 業務量産 14 本/週 で +$0.7-1.4/週。 Y フリップが出れば ROI 十分。

### R5: prompt が長すぎて context 切れ
**Mitigation**: 5 分動画 transcript ≈ 5000 tokens。 gpt-4o (128k) / claude-sonnet (200k) で余裕。 10 分超は将来分割対応。

### R6: 失敗時のユーザー体験
**Mitigation**: フォールバック発動時にフロントエンドに「AI 監督モードが使えなかったため標準モードで処理しました」 を通知。

## Migration Plan

### Phase 0: LLM 単体 PoC (1 時間)
1. `backend/scripts/director_poc.py` 作成
2. 既存 input.mp4 の transcript を読み、 LLM director に投げる
3. 返ってきた clips を確認 (人間の目で「これでリールになるか」 判定)
4. 失敗なら prompt を調整して 3-5 回試行
5. 撤退基準: 5 回試行で良い clips が返らなければ Phase 1 中止

### Phase 1: バックエンド統合 (4 時間)
1. `app/services/director.py` 実装
2. `app/models/schemas.py` に editor_mode 追加
3. `app/routers/video.py` に分岐追加
4. word boundary snap + 字幕生成の director 対応
5. テスト追加 (mock LLM、 検証ルール、 フォールバック)
6. 同 input.mp4 で実機検証

### Phase 2: フロントエンド UI (2 時間)
1. ProcessingPanel に編集モード選択追加
2. ツールチップ・推奨基準の説明文
3. API リクエストに editor_mode を含める
4. director 失敗時の通知 UI

### Phase 3: 検証 + commit (1 時間)
1. 同 input.mp4 で両モード比較
2. regression-bench.md に結果追加
3. 全テスト pass 確認
4. commit + archive

### Rollback
`editor_mode` のデフォルトを `rule_based` のまま維持すれば既存挙動。 director 関連コードは独立モジュールなので削除しやすい。 git revert で完全に戻る。
