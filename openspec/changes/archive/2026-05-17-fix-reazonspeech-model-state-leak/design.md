## Context

### 現在の `_transcribe_with_reazonspeech` (asr.py L77-98)
```python
@lru_cache(maxsize=1)
def _load_reazonspeech_model():
    from reazonspeech.nemo.asr import load_model
    return load_model(device="cpu")

def _transcribe_with_reazonspeech(audio_path):
    try:
        model = _load_reazonspeech_model()
        audio = audio_from_path(audio_path)
        result = transcribe(model, audio)
        return words, segments
    except Exception as e:
        logger.warning("ReazonSpeech failed, falling back: %s", e)
        return None
```

### 観測されているエラー
- 「Cannot unfreeze partially without first freezing the module with `freeze()`」
- 同一プロセス内で 2 回目以降の `transcribe()` 呼出で発生
- NeMo の `transcribe()` 内部で `model.freeze()` / `model.unfreeze()` を呼ぶが、 何らかの理由で部分的 unfreeze 状態が残り、 次の呼出で整合性チェックに失敗

### 量産時の影響
- 1 ジョブ中: Stage 3 で 1 段目 + Stage 5a で 2 段目 + Stage 5b で 3 段目 = 最大 3 回 transcribe
- 連続 14 ジョブ = 42 回 transcribe → 確実にエラー発生
- WhisperX フォールバックも何らかで hang する事象あり (要追加調査)

## Goals / Non-Goals

**Goals:**
- ReazonSpeech が連続呼出でも確実に動作
- 失敗時の自動 self-heal (キャッシュ破棄 + 再ロード)
- 業務量産 14 本連続処理を保証

**Non-Goals:**
- WhisperX の hang 問題は別 change で対応(本 change の Scope は ReazonSpeech)
- NeMo モデル自体のパッチ
- GPU 化(CPU のまま)

## Decisions

### D1: 2-tier retry strategy
```python
def _transcribe_with_reazonspeech(audio_path):
    for attempt in (1, 2):
        try:
            model = _load_reazonspeech_model()
            # 防御的: 状態を明示的にリセット (NeMo の freeze() API)
            try:
                model.freeze()
            except Exception:
                pass
            result = transcribe(model, audio)
            return words, segments
        except Exception as e:
            err_msg = str(e)
            is_state_error = (
                "freeze" in err_msg.lower()
                or "unfreeze" in err_msg.lower()
                or "partial" in err_msg.lower()
            )
            if attempt == 1 and is_state_error:
                logger.warning(
                    "ReazonSpeech state error (attempt %d), invalidating cache and retrying: %s",
                    attempt, e,
                )
                _load_reazonspeech_model.cache_clear()
                continue
            logger.warning("ReazonSpeech failed, falling back: %s", e)
            return None
    return None
```

**理由**:
- 通常時のオーバーヘッドは `model.freeze()` の呼出 1 回 (ms オーダー)
- エラー発生時は cache_clear + fresh load で確実に修復(+10〜20 秒だが、 数十ジョブに 1 回程度)
- それでも失敗するなら WhisperX フォールバックに委ねる(現状の挙動を維持)

### D2: model.freeze() の防御呼出
- 各 transcribe 前に明示的に `freeze()` を呼ぶ
- これで internal state を「freezed」 に正規化し、 NeMo の `transcribe()` が期待する状態にする
- API が無ければ try/except で無視(後方互換)

### D3: state エラーの判定
- エラーメッセージに「freeze」 「unfreeze」 「partial」 のいずれかを含むものを state エラーとみなす
- 他のエラー(GPU 不足、 音声ファイル不正等)は state エラーではないので retry しない

## Risks / Trade-offs

### R1: model.freeze() が NeMo の API として存在しない場合
**Mitigation**: try/except で握り潰す。 freeze() が存在しないなら、 NeMo の内部状態管理が不要な実装ということ → そのまま transcribe を試す

### R2: cache_clear 後の fresh load が +10〜20 秒
**Mitigation**: 業務量産でほぼ毎ジョブ発生しなければ許容範囲。 業務 14 本/週 で 1-2 回発生しても +30 秒程度の影響

### R3: 既存テストへの影響
**Mitigation**: 既存テストは ReazonSpeech をモックしているので影響なし

## Migration Plan

1. `_transcribe_with_reazonspeech` を 2-tier retry に書き換え
2. テスト追加: state error → cache_clear → 成功 のモックテスト
3. backend restart で適用
4. 業務量産でモニタリング

### Rollback
asr.py 限定の変更。 git revert で完全に戻る。
