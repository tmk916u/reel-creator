## 1. Backend 実装

- [ ] 1.1 `subtitle.py` に `detect_suspicious_segments(segments)` を追加 (4 条件のヒューリスティック)
- [ ] 1.2 `schemas.py` の `TranscriptSegment` に `suspicious: bool = False` を追加
- [ ] 1.3 `video.py` の `/api/transcribe` で `detect_suspicious_segments` を呼出してレスポンスに反映

## 2. Frontend 実装

- [ ] 2.1 `PreviewSegments.tsx` (or 該当ファイル) で suspicious=true の segment を赤字 border にする
- [ ] 2.2 警告アイコン (例: ⚠️) を表示
- [ ] 2.3 ユーザーが編集 (text 変更) すると border の赤を解除

## 3. テスト

- [ ] 3.1 既存テスト PASS 確認
- [ ] 3.2 `test_subtitle.py` に `detect_suspicious_segments` の テスト 3-4 件追加

## 4. 動作確認

- [ ] 4.1 ブラウザで実機テスト: アップロード → preview モードで赤字 segment 表示確認

## 5. archive

- [ ] 5.1 全タスク完了確認
- [ ] 5.2 `openspec archive add-mishearing-highlight-preview`
