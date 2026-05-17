## Why

業務量産で 1 動画あたり 1-3 件の誤認識が残る現実 (LLM 校正でも吸収しきれない subword 断片など)。 投稿前に手動修正する運用が現実解だが、 現状は 30 秒の字幕全 Dialogue を読み返す必要がある。

「誤認識候補だけを赤字ハイライト」 すれば、 視覚的に修正対象が一目瞭然で 30 秒 → 10 秒に短縮可能。

## What Changes

- **Backend**:
  - `subtitle.py` に `detect_suspicious_segments(segments)` ヘルパー追加
  - ヒューリスティック検出: (a) 5 文字以下で記号/助詞 比率高い (b) 同一 word の連続反復 (c) 句点・記号で始まる (d) 1 文字 + 助詞のみ
  - `/api/transcribe/{job_id}` の TranscriptSegment レスポンスに `suspicious: bool` フィールド追加
- **Frontend**:
  - `PreviewSegments.tsx` (または相当の編集 UI) で suspicious=true の segment を **赤字 + 警告アイコン** で表示
  - ユーザーが赤字 segment にホバー → 「動画固有辞書に追加」 ボタンで簡単に修正登録
- BREAKING: なし(レスポンスにフィールド追加のみ、 既存 frontend は無視可)

## Capabilities

### Modified Capabilities
- `quality-line`: 項目#13 編集不要 (の代替として「編集が高速で済む」 を実現)

## Impact

- **Backend**: subtitle.py に 30 行、 video router のレスポンス schema 更新
- **Frontend**: PreviewSegments の rendering に 20-30 行
- **業務量産**: 1 動画あたり編集時間 30 秒 → 10 秒、 14 本/週で -4-5 分の手間削減
