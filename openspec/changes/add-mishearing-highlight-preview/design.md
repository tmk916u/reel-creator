## Context

### 既存 preview の流れ
1. `/api/transcribe/{job_id}` で字幕 segments を取得
2. frontend `PreviewSegments.tsx` で segments を一覧表示、 各 segment はテキストエリア
3. ユーザーが編集 → confirm
4. `/api/process/{job_id}` で edited_segments を送信

### 問題
- 30 件の Dialogue を全部読み返す必要がある
- どれが「誤認識」 か視覚的に分からない
- 「事への」 「悪い要」 のような subword 断片を見落とすリスク

## Goals / Non-Goals

**Goals:**
- 誤認識候補を視覚的にハイライト
- ユーザーが 5-10 秒で全 segment を確認できる

**Non-Goals:**
- 完全な誤認識検出 (false positive / false negative は許容)
- 誤認識の自動修正 (本 change では検出のみ)
- 動画固有辞書への登録 UI (別 change で対応可能、 本 change は表示のみ)

## Decisions

### D1: 検出ヒューリスティック (4 条件いずれか)
```python
def detect_suspicious_segments(segments: list[dict]) -> list[bool]:
    """各 segment が誤認識候補かを返す。 True=赤字ハイライト。"""
    result = []
    for s in segments:
        text = s["text"].strip()
        susp = False
        # (a) 5 文字以下で助詞・記号が 50% 以上
        if len(text) <= 5:
            particles = sum(1 for c in text if c in "はがをにでとのも、。!?ー ")
            if len(text) > 0 and particles / len(text) >= 0.5:
                susp = True
        # (b) 同一文字の連続 3 回以上 (subword 反復)
        for i in range(len(text) - 2):
            if text[i] == text[i+1] == text[i+2]:
                susp = True
                break
        # (c) 句点・記号で始まる
        if text and text[0] in "、。!?,.":
            susp = True
        # (d) 1-2 文字 + 単独 「お / 客 / 事」 等の subword 断片
        if 1 <= len(text) <= 2 and not text.endswith(("。", "?", "!")):
            susp = True
        result.append(susp)
    return result
```

### D2: API レスポンス拡張
`TranscriptSegment` schema に `suspicious: bool = False` 追加。 後方互換: 既存 frontend は無視できる。

### D3: frontend のハイライト
- suspicious=true の segment テキストエリアを **赤い border + 警告アイコン**
- アイコンはツールチップで「誤認識の可能性。 確認してください」 と表示
- ユーザーが編集すると border が消える (= 確認済み扱い)

## Risks / Trade-offs

### R1: false positive で正常な segment が赤字に
**Mitigation**: ヒューリスティックは厳しめに設定。 false positive はユーザーが無視すれば良い (cost 小)

### R2: false negative で誤認識を見逃す
**Mitigation**: ユーザーは全 segment を流し読みする習慣を持つ。 ハイライトは「集中すべき箇所」 のヒント

## Migration Plan

1. subtitle.py に detect_suspicious_segments 追加 + テスト
2. schemas.py の TranscriptSegment に suspicious フィールド追加
3. video.py の /api/transcribe レスポンス構築で detect_suspicious_segments を呼出
4. frontend の PreviewSegments で赤字 rendering
5. 動作確認
