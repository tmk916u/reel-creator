## Why

回帰ベンチ 4 本（`.planning/intel/regression-bench.md`）で 0/4 が公開可能品質。却下理由のトップは「ストーリーがぐちゃぐちゃ／日本語の文脈がおかしい」（3/4）。

5/18 にチャンク分割対応した `detect_restatements`（コミット `6ce99b3`）は 22/22 単体テスト合格・「production verification 完了」と宣言したが、本ベンチでは 1 本も flip しなかった。出力 `reel_51edb5c1.mp4` の再 ASR で以下のような **既存検出が見落とした自己訂正・同義反復が残存**:

> seg 45-54: 「ここで一番大事なのは **僕がここで一番大事だと思っているの**。健康への食事はどうなのか...一番大事だと思います」（「一番大事」3 回）
>
> seg 55-68: 「**食べたもの**を**食べてしまったら**...悪いものを**食べることを続けないこと**が重要だと思います」（「続けないこと」2 回、「食べる」大量）

`detect_restatements` は「言い直し（speaker が直前の発話を訂正している）」のローカルパターンを検出するが、**カット後の transcript が日本語として意味が通るか**は誰も判定していない。サンプル動画ではこのギャップがそのまま公開可能品質判定を下げている。

## What Changes

- 既存ジャンプカット検出群（フィラー削除・言い直し検出・文末テンポ・遠距離冗長）の **後段** に「LLM コヒーレンスパス」を追加レイヤーとして導入する
- 既存検出後の生存 word 列を LLM に渡し、「日本語として意味が通る最小 word subset」を返させ、削除候補を `extra_cuts` に追加する
- 機能フラグ `ENABLE_LLM_COHERENCE_PASS` で ON/OFF を制御（デフォルト OFF）
- Dry-run モード `LLM_COHERENCE_PASS_DRY_RUN=1` を必須実装。実カットせず削除候補と理由・信頼度をログ出力するだけ
- 削除総時間が元の 30% を超えるレスポンスは「暴走」として丸ごと破棄するガードを実装
- 60 秒以上の入力は `chunked-restatement-detection` と同じく 90 秒チャンク・15 秒オーバーラップで分割
- 合格基準: 回帰ベンチ 4 本に対し `LLM_COHERENCE_PASS_DRY_RUN=1` で生成された削除候補を目視確認 → OK ならフラグ ON にして 4 本再評価で **flip ≥ 2** を達成して初めて本適用とみなす

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

- `ai-jump-cut`: 「LLM コヒーレンスパス」要件を追加（ADDED requirement）

## Impact

- 影響コード: `backend/app/services/llm.py`（新関数 `detect_coherence_violations`）、`backend/app/routers/video.py`（パイプラインへの統合）、`backend/app/models/schemas.py`（リクエストフラグ追加の可能性あり）
- LLM 呼出回数: 機能 ON 時、`detect_restatements` と同等のチャンク数だけ増加（短尺で +1、250 秒入力で +3〜4）
- レイテンシ: 1 ジョブあたり概算 +5〜15 秒（チャンク数・モデル次第）
- API/DB スキーマ変更: なし（環境変数のみ）
- 後方互換: フラグ OFF（デフォルト）で完全に従来挙動
- 失敗時: LLM 不通・スキーマ違反は warning ログを残して **skip**、既存検出結果のみで処理続行（FAILED にしない）

## Acceptance Criteria（ベンチ合格基準）

本 change は `.planning/intel/regression-bench.md` の 4 本サンプルに対し以下を満たすまで本適用しない:

1. Dry-run モードで生成された削除候補を `cat /tmp/coherence_dryrun_*.json` で目視確認し、明らかな誤削除（重要な発話を切る）がないこと
2. フラグ ON で 4 本を再処理し、再評価で **flip ≥ 2 本**（現状 N → Y）を達成すること
3. 単体テスト合格は合格基準ではない（過去の `chunked-restatement-detection` は 22/22 通過したが本ベンチでは 0 flip）
