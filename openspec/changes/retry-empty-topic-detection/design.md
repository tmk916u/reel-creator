## Context

### 現状の detect_topics
```python
def detect_topics(segments, max_topics=4, video_context=""):
    # LLM 呼出
    raw = _call_anthropic(user_message, system_prompt=_TOPICS_SYSTEM_PROMPT)
    parsed = _TopicsResponse.model_validate(_extract_json(raw))
    result = []
    for t in parsed.topics:
        if 0 <= t.start_seg < len(segments):
            result.append({...})
    return result  # 0 件のこともある
```

現行プロンプトに「動画が短すぎる or 単一トピック の場合は分割しない」 とあり、 LLM が判断ミスして 0 件を返すケース ~10%。

## Goals / Non-Goals

**Goals:**
- トピック 0 件のケースで 1 回リトライ
- リトライで強制的に最低 2 件を返させる
- LLM コスト増は最小限 (リトライ率 ~10% なら +10% コスト)

**Non-Goals:**
- 3 回以上のリトライ (2 回目も 0 件なら諦める、 元動画が本当に単一トピックの可能性)
- segments の内容ベースでのフォールバック (例: 等分割) — LLM の判断を優先

## Decisions

### D1: リトライ条件
- 1 回目の result が **完全に空** (0 件) のときのみリトライ
- 1 件でも返してくれば、 リトライしない (LLM の判断を尊重)

### D2: リトライ用プロンプト `_TOPICS_FORCE_PROMPT`
```
あなたは動画コンテンツの構造化アシスタントです。
入力された日本語の文字起こしを **必ず 2〜4 個** のポイント/章に分割してください。

ルール:
- **必ず最低 2 個** に分割する (単一トピックでも論理的な分割を見つける)
- 各ポイントには 8 文字以内の短いラベル
- start_seg は分割の開始セグメント番号
- 「導入」「展開」「結論」 のような構造的分割でも OK

出力 JSON:
{"topics": [{"index": 1, "start_seg": 0, "label": "..."}, ...]}
```

### D3: リトライ失敗時の挙動
- 2 回目も 0 件なら 0 件のまま返す (現状と同じ)
- ログに「detect_topics retry also returned 0 topics」 を warning で出力

## Risks / Trade-offs

### R1: LLM コスト増
**Mitigation**: リトライ発動率 ~10% なので、 月コスト +10%。 業務量産で許容範囲

### R2: 強制分割で不自然なトピックラベル
**Mitigation**: 「導入 / 展開 / 結論」 のような構造的分割を許容するプロンプト。 不自然でも空よりマシ

## Migration Plan

1. `_TOPICS_FORCE_PROMPT` を llm.py に追加
2. `detect_topics` にリトライロジックを組込
3. テスト追加 (モック: 1 回目空 → リトライで 2 件返す)
4. 動作確認 (実 LLM で seitai_food.mov 再処理)
