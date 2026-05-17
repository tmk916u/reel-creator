# Contributing - Reel Creator

## 開発フロー (OpenSpec spec-driven)

このリポジトリは [OpenSpec](https://openspec.dev) で spec-driven な開発をしている。
新規機能や品質改善は **change** を通じて進める。

### 基本コマンド

```bash
# 進行中 change の一覧
openspec list

# 新規 change を提案
/openspec-propose <自然言語で説明>

# change を実装
/openspec-apply <change-name>

# 完了 change を archive
/openspec-archive-change <change-name>

# Spec を探索 / 思考整理
/openspec-explore <topic>
```

## 業務量産品質ラインに向けたフロー

業務量産投入の合格基準は **14 項目チェックリスト** として永続化されている:
[`openspec/specs/quality-line/spec.md`](openspec/specs/quality-line/spec.md)

### 不合格項目があった場合の change 起票フロー

ベースライン測定 (`baseline.md`) で不合格項目を見つけたら、 以下の手順で:

1. **1 項目 = 1 change** が原則 (相互依存する項目は 1 change にまとめる判断もあり)
2. `/openspec-propose` で change を起こす
   - 例: 「項目#7 字幕の自然な切れ目を改善。 助詞直後 flush の比率を 13% → 5% に下げる」
3. proposal で対象項目と spec 内の Requirement を明示
4. design で実装方針を決める
5. tasks で実装ステップを 5-15 個に分解
6. apply で実装
7. **必ず test-videos/ で再測定** して合格を確認
8. archive

### 退行検知

修正後は必ず:
1. `backend/scripts/measure_quality.py <job_id>` を再実行
2. 退行 (前は合格していた項目が不合格になった) があれば、 change を撤回または修正
3. ベースライン `baseline.md` を更新

## コミットメッセージ

[Conventional Commits](https://www.conventionalcommits.org/) 形式:

```
feat: 新機能
fix: バグ修正
refactor: リファクタリング
docs: ドキュメント
chore: その他

(本文は日本語OK、 conventional の type は英語)
```

例:
- `feat: 項目#7 字幕の自然な切れ目を改善 (助詞直後 flush 抑制)`
- `fix: 施策G の上限が integer overflow するバグ`

## テスト

```bash
docker compose run --rm --no-deps -e PYTHONPATH=. backend \
  bash -c "pip install -r requirements-dev.txt --quiet && pytest tests/ -v"
```

新規実装には対応するテストを追加。 既存 105 件が PASS する状態を維持。

## 動画レベルの回帰テスト

`test-videos/` 配下の 3 本のテスト動画で:

1. 各動画を処理 (`docker compose up backend` 起動 → API or curl で /api/process)
2. `measure_quality.py <job_id>` で測定
3. `quality_report.md` の機械測定がすべて ✅
4. 目視チェックも合格

を満たすこと。 動画ファイルは git 管理外 (`.gitignore` で除外、 サイズが大きいため)。

期待値ドキュメント `test-videos/*.expected.md` のみ git に含める。
