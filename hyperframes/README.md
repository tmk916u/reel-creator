# HyperFrames リール仕上げ

reel-creator で前処理した映像に、**HyperFrames**（HeyGen の HTML/CSS/GSAP 動画合成）で
ブランドタイポを乗せて、Instagram リール級の縦型動画（1080×1920）を作る工程。

reel-creator 本体の ASS 字幕では出せない、雑誌・CM 級のキネティックタイポ／
ローワーサード／和の縦書きなどを、アカウント情報に沿って自動でセットアップする。

## 役割分担（なぜ 2 つに分かれているか）

HyperFrames のレンダーは**ヘッドレス Chromium** を使うため backend コンテナでは動かない。
そのため次の分業になっている。

| 担当 | 役割 |
| ---- | ---- |
| **コンテナ**（ffmpeg） | ジョブの映像を色味済み・縦型(1080×1920)・字幕なしの footage として配信 |
| **ホスト(mac)**（Node + ブラウザ） | プロファイル＋footage を取得 → プロジェクト組み立て → レンダー |

## 前提

- backend が起動している（`docker compose up` / 既定 http://localhost:8000）
- ホストに Node 18+（`node -v`）。HyperFrames は `npx` で都度取得（事前インストール不要）
- アカウント設定（ブランド名・ハンドル等）を登録済み（アプリの「アカウント設定」or `PUT /api/account-profile`）

## ワンコマンドで作る

reel-creator でアップロード〜処理して得た `job_id` を渡す。

```bash
# 生成 → レンダー → mac で再生 まで一気に
node hyperframes/new-from-job.mjs <job_id> \
  --template tategaki-wa --grade cinematic --start 40 --duration 12 --render --open
```

| オプション | 既定 | 説明 |
| ---------- | ---- | ---- |
| `--template` | `cinematic-serif` | テイスト（下表） |
| `--grade` | `cinematic` | 色味 LUT（none/minimal/cinematic/monochrome/pop） |
| `--start` | `0` | 切り出し開始秒 |
| `--duration` | `12` | 尺（秒） |
| `--render` | （なし） | 生成後そのままレンダー |
| `--open` | （なし） | レンダー後に MP4 を開く（macOS） |

`--render` を付けない場合は `hyperframes/jobs/<job_id>/` にプロジェクトだけ生成される。
出力 MP4 は `hyperframes/jobs/<job_id>/renders/` に出る。

## テイスト（仕上げの世界観）

`brief.json` の `template`、または `--template` で選ぶ。どれも同じ `brief.json` で動く。

| テイスト | 雰囲気 | 文字 |
| -------- | ------ | ---- |
| `cinematic-serif` | 静か・上質・暗 | 明朝・中央 |
| `bold-gothic` | 力強い・SNS 映え・暗 | ゴシック・左寄せ・アクセントバー |
| `minimal-light` | 明るい・エディトリアル | 明朝・クリーム帯 |
| `tategaki-wa` | 和・凛とした余白 | 縦書き明朝 |

## 文言・配色を編集する

生成された `hyperframes/jobs/<job_id>/brief.json`（または雛形 `hyperframes/ichiki-kuukan/brief.json`）を編集。

```jsonc
{
  "template": "cinematic-serif",      // テイスト
  "footage": "footage.mp4",
  "colors": { "ivory": "#f4ede0", "accent": "#e9d9b6", "rule": "#cbb88f", "romaji_color": "#d9cfbf", "bg": "#0a0a0a" },
  "copy": {
    "wordmark": "一木空間",
    "romaji": "ICHIKI　KUUKAN",
    "phrase1": "ととのう、<br />という<em>時間</em>。",   // <em>=アクセント色 / <br>=改行
    "phrase2": "身体と、空間と、<br /><em>呼吸</em>と。",
    "kicker": "SPACE &amp; BODYWORK",
    "handle": "@ichiki_kuukan"
  }
}
```

編集後:

```bash
cd hyperframes/jobs/<job_id>     # or hyperframes/ichiki-kuukan
npm run snapshot   # 5枚のキーフレーム(snapshots/contact-sheet.jpg)で即確認
npm run dev        # ブラウザのスタジオでライブプレビュー(自動リロード)
npm run render     # MP4 を renders/ に書き出し
```

## アーキテクチャ / 関連エンドポイント

```
[reel-creator backend]                         [host (mac)]
 GET /api/account-profile ───────────────┐
 GET /api/hyperframes/footage/{job_id} ──┤   new-from-job.mjs
   ?grade&start&duration                 ├──▶ brief.json 生成
   → 色味済み 1080x1920 クリーン映像       │    footage.mp4 取得
                                          │    templates/ 雛形コピー
                                          └──▶ hyperframes render → MP4
```

- `hyperframes/new-from-job.mjs` … ホスト側オーケストレーション
- `hyperframes/ichiki-kuukan/` … 雛形（`templates/*.tmpl` / `build.mjs` / `fonts/`）兼サンプル
- `hyperframes/jobs/<job_id>/` … 生成プロジェクト（gitignore）

## ディレクトリ

```
hyperframes/
  new-from-job.mjs           # ジョブ→プロジェクト生成 + 任意レンダー
  ichiki-kuukan/             # 雛形 & サンプル（README はここに編集詳細）
    brief.json               # 編集する所（テイスト/コピー/配色/footage）
    templates/*.tmpl         # テイスト別 HTML/CSS/GSAP テンプレ
    build.mjs                # brief を選択テンプレに流し込み index.html 生成
    fonts/                   # Shippori Mincho / Zen Kaku Gothic New
  jobs/<job_id>/             # 自動生成（gitignore）
```

新しいテイストを足すときは `ichiki-kuukan/templates/` に `<name>.tmpl` を追加し、
`brief.template` で選ぶ（プレースホルダ `{{wordmark}}` 等は既存と揃える）。詳細は
[`ichiki-kuukan/README.md`](ichiki-kuukan/README.md)。
