## Context

### 既存の ASR 構成 (asr.py)
- `transcribe_with_words(audio, initial_prompt, model_size)` が 3 段フォールバック:
  - ReazonSpeech (default) → WhisperX → faster-whisper
- 各バックエンドは `_transcribe_with_reazonspeech` / `_transcribe_with_whisperx` / `_transcribe_with_faster_whisper` で実装済み
- 戻り値は `(words, segments)`、 word は `{start, end, text, [is_word_start]}`

### ReazonSpeech と WhisperX の特性差
| 項目 | ReazonSpeech NeMo | WhisperX |
|------|-------------------|----------|
| 単位 | subword (1-3 文字) | word (1-10 文字) |
| timestamp 精度 | subword 単一点 (±0.1-0.3s) | word 境界 align (±0.05s) |
| 日本語精度 | 高 (整体ドメインで強い) | 中 |
| 弱点 | subword 断片化 (「ボメ 康」) | 単語境界の確実性は強いが、 全体一致率は ReazonSpeech と同程度 |

### 観測される誤認識パターン
- ReazonSpeech 単独: 「悪い要」「ボディ康」「こ律」「事への」
- WhisperX 単独: (未測定だが、 おそらく違うパターン)
- 両方同じ誤認識: まれ (両方が同じ音響ミスをする確率は低い)

→ **両方を併用すれば誤認識の重複が少ない** という仮説。

## Goals / Non-Goals

**Goals:**
- 1 ASR では取れない誤認識を ensemble で補完
- 不一致箇所のみ LLM cross-check で意訳修正
- 処理時間の悪化を並列実行で抑制 (max 数十秒)

**Non-Goals:**
- GPT-4o Whisper / Claude voice API の使用 (将来選択肢として残すが本 change の範囲外)
- 3 ASR ensemble (ReazonSpeech + WhisperX + faster-whisper)
- リアルタイム ensemble (バッチ処理のみ)

## Decisions

### D1: 並列実行は ThreadPoolExecutor
```python
import concurrent.futures
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f_r = ex.submit(_transcribe_with_reazonspeech, audio_path)
    f_w = ex.submit(_transcribe_with_whisperx, audio_path, initial_prompt, model_size)
    r_result = f_r.result(timeout=600)
    w_result = f_w.result(timeout=600)
```
**理由**: ASR は CPU バウンド + I/O 待ち。 ThreadPoolExecutor で 2 並列実行すれば total time = max(R, W) = ~80秒。 直列なら 150秒。

### D2: ensemble merge アルゴリズム
1. WhisperX words を **基準** にする (word 単位で安定)
2. 各 WhisperX word に対し、 ReazonSpeech subwords を 時刻 overlap 50% 以上 でクラスタリング
3. クラスタ内の ReazonSpeech subwords を結合した text と WhisperX word text を比較:
   - **同じ text** → WhisperX word を採用、 `agree=True`
   - **違う text** → WhisperX word を採用、 `disagreement: {wx_text, rs_text, start, end}` に記録
4. WhisperX words に対応しない ReazonSpeech subwords (= WhisperX が認識できなかった range) → ReazonSpeech subwords を補完で追加

### D3: LLM cross-check は disagreement のみ
- merge 後の disagreements リストを LLM に投げる
- prompt: 「以下は ASR の不一致箇所。 前後 context から正しい text を選んでください」
- output: `{"corrections": [{"index": 0, "text": "正しい text"}, ...]}`
- 不一致が少なければ LLM 呼出も少ない (動画 1 本あたり 3-10 箇所程度を想定)

### D4: テキスト比較は正規化後に行う
- 全角空白除去、 「、」「。」 除去、 lower case (英字)
- 「重要」 と「重要、」 を同じ text として扱う

### D5: WhisperX 失敗時のフォールバック
- WhisperX 例外 → ReazonSpeech 単独で transcribe (現状と同じ)
- ReazonSpeech 例外 → WhisperX 単独で transcribe
- 両方失敗 → faster-whisper にフォールバック (既存)

### D6: words の data structure
ensemble 後の word に新フィールド `source: "agree" | "wx_only" | "rs_only" | "disagreement"` を追加。 debugging とログ用。

```python
{
    "start": 1.5, "end": 1.9, "text": "重要",
    "source": "disagreement",
    "rs_text": "悪い要", "wx_text": "重要",  # 不一致時のみ
}
```

## Risks / Trade-offs

### R1: WhisperX も誤認識する場合
**Mitigation**: 不一致 → LLM cross-check で意訳修正で吸収。 両方が同じ誤認識をした場合は依然残る (限界)

### R2: 処理時間が +10〜30 秒
**Mitigation**: 並列実行で抑制。 業務量産 14本/週 で +3-7 分。 受容範囲

### R3: WhisperX の word.text が日本語として粗い
**Mitigation**: ReazonSpeech のテキスト品質を信頼するケースを残す (両方確認、 ReazonSpeech が「悪い要」 でも WhisperX が「重要」 と一致してれば改善)

### R4: ThreadPoolExecutor 内で GIL 競合
**Mitigation**: ASR は内部で C 拡張を使うので GIL 解放される。 並列実行効果あり

### R5: ReazonSpeech state leak バグの再発
**Mitigation**: 既存の `fix-reazonspeech-model-state-leak` の retry 機構が動作する

## Migration Plan

### Phase 1 (3 時間): 並列実行 + 結果保存
1. `transcribe_ensemble(audio_path, initial_prompt, model_size)` を asr.py に追加
2. ThreadPoolExecutor で R + W を並列実行
3. 両方の transcript を job_dir に保存
4. 戻り値は `(ensemble_words, ensemble_segments, debug_info)`

### Phase 2 (3 時間): merge アルゴリズム
1. `_ensemble_merge(r_words, w_words)` を実装
2. 時刻 overlap で word クラスタリング
3. 多数決ルールで merge
4. テスト追加 (3-4 件)

### Phase 3 (2 時間): LLM cross-check
1. `cross_check_disagreements(disagreements, video_context)` を llm.py に追加
2. ensemble の不一致箇所のみ LLM 呼出
3. 結果を ensemble_words に反映
4. テスト追加 (2 件)

### Phase 4: 統合 + 検証
1. video.py の 1 段目 transcribe を `transcribe_ensemble` に置換
2. seitai_food.mov 再処理で誤認識減少を確認
3. ベースライン比較

### Rollback
asr.py / llm.py / video.py 限定。 git revert で完全に戻る。
ASR_BACKEND 環境変数で従来 ReazonSpeech 単独に戻せる仕組みも温存。
