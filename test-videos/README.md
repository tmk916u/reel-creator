# test-videos/

業務量産品質ライン (`openspec/specs/quality-line/spec.md`) の検証用テスト動画セット。

## ファイル

| ファイル名 | 想定特性 | 期待値 |
|---|---|---|
| `seitai_standard.mov` | 整体・血流・筋肉系の標準動画(2-3分) | `seitai_standard.expected.md` |
| `seitai_food.mov` | 整体師が食事/ダイエットを話題に(2-4分) | `seitai_food.expected.md` |
| `seitai_long.mov` | 5分以上の長尺、言い直し・間が多い | `seitai_long.expected.md` |

## 運用ルール

### 1. 動画ファイルの管理
- `*.mov` は **git 管理外** (`.gitignore` で除外、サイズが大きいため)
- ユーザーが手元の動画から選定して配置する
- 期待値ドキュメント `*.expected.md` のみ git に含める

### 2. 期待値ドキュメントの形式
各 `<name>.expected.md` には以下のセクションを含める:

```markdown
# <ファイル名> 期待値

## 動画の主張
<1-2 文>

## 残るべき発話キーワード
- <キーワード1>
- <キーワード2>
- ...(5-10個)

## 期待 HOOK の方向性
<明示的な一文ではなくテーマレベル。例:「食事の習慣化が体づくりの鍵」>

## 想定出力動画長
<範囲、例: 60-90秒>

## 想定される誤認識パターン
- <パターン1>(例:「不定愁訴」→「不定収走」)
- ...
```

### 3. ベースライン測定への組み込み
- `backend/scripts/measure_quality.py <job_id>` で各動画の出力を測定
- 結果は `openspec/changes/establish-quality-line/baseline.md` に集約
- 不合格項目は新規 change として枝分かれする

### 4. 動画セットの更新
- 業務量産で「うまくいかなかった動画」を順次追加する
- 動画追加時は対応する `*.expected.md` も作成
- 既存動画の差し替え時は `baseline.md` を再測定
