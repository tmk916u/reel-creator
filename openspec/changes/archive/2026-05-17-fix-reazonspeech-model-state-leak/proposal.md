## Why

backend で連続して動画を処理していると、 2 ジョブ目以降で ReazonSpeech が以下のエラーで失敗:

```
ReazonSpeech failed, falling back: Cannot unfreeze partially without first freezing the module with `freeze()`
```

WhisperX フォールバックも稀に hang して backend 全体が停止する状態を確認 (実測: job 4b0636e8 で 09:08:42 にエラー → 数分後も backend 応答せず → restart 必要)。

真因: `_load_reazonspeech_model()` は `@lru_cache(maxsize=1)` で同一インスタンスを再利用しているが、 NeMo の `transcribe()` 内部で行われる `freeze()` / `unfreeze()` 操作が連続呼出でモジュール状態を破壊する。 1 ジョブ中に 1〜2 回 transcribe するため、 業務量産 14 本連続処理時に確実に再現する致命バグ。

## What Changes

- `_transcribe_with_reazonspeech` を fail-fast + retry 構造に改修:
  1. キャッシュ済みモデルで transcribe を試行
  2. `Cannot unfreeze partially` 等の状態破損エラーを検出
  3. `_load_reazonspeech_model.cache_clear()` で キャッシュ破棄、 fresh load
  4. もう一度 transcribe (今度は確実に成功)
  5. 2 回目も失敗したら WhisperX フォールバックへ
- transcribe 前に `model.freeze()` を明示呼出して状態を強制リセット(NeMo の API)
- BREAKING: なし(内部実装の堅牢化のみ)
- 処理時間: 通常時の影響なし。 状態破損時のみ +10〜20 秒(モデル再ロード)

## Capabilities

### Modified Capabilities
- `quality-line`: 業務量産 14 本連続処理の安定性を担保

## Impact

- **Backend**: `asr.py` の `_transcribe_with_reazonspeech` を強化(約 30 行追加)
- **テスト**: 既存 120 件を維持。 新規 1-2 件(状態破損エラー → 再ロード → 成功 のモックテスト)
- **業務量産**: 14 本連続処理が確実に通る状態へ
