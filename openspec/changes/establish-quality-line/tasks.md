## 1. Spec の永続化

- [x] 1.1 `openspec/specs/quality-line/spec.md` を本 change の `specs/quality-line/spec.md` と同じ内容で作成(apply 段階で OpenSpec が自動同期)
- [x] 1.2 README に「業務量産品質ラインは `openspec/specs/quality-line/spec.md` 参照」のリンクを追加

## 2. テスト動画セット整備

- [x] 2.1 `test-videos/` ディレクトリを作成
- [ ] 2.2 `seitai_standard.mov` をユーザー所有の動画から 1 本選定して配置(2-3分の整体・血流系)
- [ ] 2.3 `seitai_food.mov` を選定(整体師が食事/ダイエット話題、 IMG_3270.mov 等から流用)
- [ ] 2.4 `seitai_long.mov` を選定(5 分以上の長尺、 言い直しが多い)
- [x] 2.5 `seitai_standard.expected.md` を作成(動画の主張、残るべきキーワード、期待 HOOK 方向、想定動画長、想定誤認識)
- [x] 2.6 `seitai_food.expected.md` を作成(同上の項目)
- [x] 2.7 `seitai_long.expected.md` を作成(同上の項目)
- [x] 2.8 `test-videos/README.md` を作成(各動画の概要と運用ルール)
- [x] 2.9 `.gitignore` に `test-videos/*.mov` を追加(動画ファイルは git に入れない、 期待値 md のみ管理)

## 3. 測定スクリプト

- [x] 3.1 `backend/scripts/measure_quality.py` を新規作成
- [x] 3.2 入力: `job_id`(or job_dir パス)、 出力: JSON + Markdown チェックリスト
- [x] 3.3 機械測定実装(項目#4): ffprobe で output.mp4 の duration を取得し 60-120秒 範囲判定
- [x] 3.4 機械測定実装(項目#6): ASS Dialogue 開始時刻と words の word.start を比較し、 差 > 0.5秒 の箇所をカウント
- [x] 3.5 機械測定実装(項目#7): ASS Dialogue 末尾文字を集計し、 格助詞(はがをにでとのもへやか)で終わる比率を出力
- [x] 3.6 機械測定実装(項目#8): 各 Dialogue の text 文字数分布を集計し、 8-14 文字に収まる比率を出力
- [x] 3.7 機械測定実装(項目#11): CTA テキストの各文字が Noto Sans CJK JP でレンダリング可能か `fc-list` または `ffmpeg drawtext` 試行でチェック
- [x] 3.8 機械測定実装(項目#14): 処理時間を `backend logs` 経由または job_dir のファイル更新時刻差で算出
- [x] 3.9 目視チェックリストテンプレ出力(項目#1, #5, #9, #10, #12 など)
- [x] 3.10 結果を `<job_dir>/quality_report.json` と `<job_dir>/quality_report.md` に保存

## 4. ベースライン測定

- [ ] 4.1 3 本のテスト動画それぞれを `docker compose up backend` で処理 (⚡ぎっしりプリセット、 skip_preview=true)
- [ ] 4.2 各 job について `measure_quality.py` を実行
- [ ] 4.3 機械測定結果を集約
- [ ] 4.4 目視判定(項目#1, #5, #9, #10, #12)を実施
- [ ] 4.5 `openspec/changes/establish-quality-line/baseline.md` に Markdown テーブルで集約
- [ ] 4.6 不合格項目それぞれに **コメント** を付与(具体的な状況、 推測される原因)

## 5. 不合格項目のトリアージ

- [ ] 5.1 baseline.md の不合格項目を優先度別に分類(致命的/重要/任意)
- [ ] 5.2 致命的項目について `/openspec-propose` で新規 change を起こす候補リストを作成
- [ ] 5.3 候補リストを baseline.md の末尾に追記

## 6. 既存 change のクローズ

- [x] 6.1 `add-ai-jump-cut` の残タスク 9.2(目視確認)を実質完了として check
- [x] 6.2 `/openspec-archive-change add-ai-jump-cut` で archive
- [x] 6.3 archive 後の状態を確認 (2026-05-17-add-ai-jump-cut として保存、 specs/ai-jump-cut/spec.md に 8 件の Requirement が同期された)

## 7. ドキュメント整備

- [x] 7.1 `README.md` に「業務量産品質ライン」のセクションを追加(spec へのリンク、 ベースライン測定の運用ルール)
- [x] 7.2 `.planning/HANDOVER.md` を更新(品質ライン到達戦略、 次回セッションで「不合格項目を 1 つずつ change として起こす」運用)
- [x] 7.3 `CONTRIBUTING.md`(無ければ作成)に「不合格項目があった場合の change 起票フロー」を記載

## 8. 検証

- [x] 8.1 全 105 件の既存テストが PASS することを確認
- [x] 8.2 `measure_quality.py` がエラーなく動作することを確認 (任意ジョブで動作確認済)
- [ ] 8.3 ベースライン baseline.md が読みやすく、 各項目の合否が一目で分かることを確認
- [ ] 8.4 不合格項目候補リストが空でない場合、 次に起票すべき change が 1 つ以上明確になっていることを確認
- [ ] 8.5 ユーザーレビュー: 14 項目チェックリストと baseline がユーザーの業務量産観点で過不足ないか確認

## 9. archive 準備

- [ ] 9.1 全タスクの完了確認
- [ ] 9.2 `/openspec-archive-change establish-quality-line` で archive 候補に移行
- [ ] 9.3 archive 後の `openspec/specs/quality-line/spec.md` が永続化されていることを確認
