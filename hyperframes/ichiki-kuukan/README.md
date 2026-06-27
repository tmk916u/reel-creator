# ichiki-kuukan — HyperFrames リール

reel-creator の前処理（色味・9:16・尺抜き）済み映像に、HyperFrames で
ブランドタイポを乗せた縦型リール（1080×1920 / 12秒）。

## 編集のしかた（コピー・配色）

1. **`brief.json` を編集**する（これだけでOK）
   - `template` … **テイスト選択**。`cinematic-serif`（明朝・静か・暗）/ `bold-gothic`（ゴシック・力強い・暗）/ `minimal-light`（明朝・クリーム帯・明るいエディトリアル）
   - `copy.wordmark` / `phrase1` / `phrase2` / `kicker` / `handle` … 文言
     - `phrase` は `<em>…</em>` でアクセント色、`<br />` で改行
   - `colors.*` … 配色（ivory=本文 / accent=強調 / rule=罫線 / bg=背景）
   - `footage` … 使う動画ファイル名（このフォルダ直下に置く）
2. ビルド＆確認
   ```bash
   npm run build      # brief.json → index.html を生成
   npm run snapshot   # 5枚のキーフレームPNG（snapshots/contact-sheet.jpg）で確認
   npm run dev        # ブラウザでライブプレビュー
   npm run render     # MP4 を renders/ に書き出し
   ```

タイミングやレイアウト（フォントサイズ・シーンの秒数・モーション）を変えるときは
`templates/<テイスト>.tmpl`（GSAP タイムライン）を編集する。新テイストは
`templates/` に `.tmpl` を足して `brief.template` で選ぶ。
どのテイストも同じ `brief.json`（コピー・配色・footage）で動く。

## ファイル構成

| ファイル           | 役割                                                    |
| ------------------ | ------------------------------------------------------- |
| `brief.json`       | **編集する所**。テイスト・コピー・配色・footage         |
| `templates/*.tmpl` | HTML/CSS/GSAP テンプレ（`{{placeholder}}`）。テイスト別 |
| `build.mjs`        | brief を選択テンプレに流し込み `index.html` を生成      |
| `index.html`       | 生成物（gitignore）                                     |
| `footage.mp4`      | 前処理済み素材（reel-creator 出力相当）                 |
| `fonts/`           | Shippori Mincho / Zen Kaku Gothic New                   |

## 素材の差し替え

別の動画を使う場合は、reel-creator 側で色味・9:16・尺を整えた MP4 を
`footage.mp4` として置き、`brief.json` の `footage` を合わせる。
（例: `ffmpeg -ss S -t T -i src.mp4 -vf "lut3d=file=cinematic.cube,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1" -an footage.mp4`）
