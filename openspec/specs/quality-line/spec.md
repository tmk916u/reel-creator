## Purpose

業務量産投入の合格基準 (14 項目チェックリスト) と、 それを支える測定インフラ (テスト動画セット、 測定スクリプト、 ベースライン記録) の永続化。 各項目に対する合格条件 (数値しきい値 or 目視判定基準) を文書化し、 新規 change の影響を Y/N flip 数で評価する。
## Requirements
### Requirement: 14項目品質チェックリストの永続化

システム SHALL 業務量産投入の合格基準を 14 項目チェックリストとして永続化し、 各項目に対する合格条件(数値しきい値 or 目視判定基準)を文書化する。チェックリストは `openspec/specs/quality-line/spec.md`(本ファイル) に統一管理し、 他の設定ファイルや辞書に分散させない。

#### Scenario: チェックリストの参照
- **WHEN** 開発者が「業務量産投入できるか」を判断するとき
- **THEN** `openspec/specs/quality-line/spec.md` の 14 項目に対する達成度を確認できる

#### Scenario: 項目変更時の運用
- **WHEN** 14項目の合格基準を変更する必要がある
- **THEN** その変更は新規 change の proposal で提案され、 本 spec の MODIFIED Requirements として記録される

### Requirement: 項目#1 ストーリーの保全

出力動画は **元動画の主張・流れ** を保持しなければならない。重要な発話(例: 「お客様が悩まれているダイエットの食事の話をしようと思います」)が削除されてはならない。

#### Scenario: 元動画の主張が出力動画でも分かる
- **WHEN** テスト動画の出力字幕全文を読む
- **THEN** 期待値ドキュメント `*.expected.md` の「動画の主張」と整合する内容が含まれている

#### Scenario: 重要発話の保護
- **WHEN** 期待値ドキュメントの「残るべき発話キーワード」リストを確認する
- **THEN** すべてのキーワードが出力字幕に出現する

### Requirement: 項目#2 冒頭・末尾の発話保護

ASR の認識ミスや施策の暴走によって、 動画の **冒頭または末尾の実発話** が削除されてはならない。

#### Scenario: 冒頭発話の保護
- **WHEN** 元動画で発話開始から 30 秒以内に重要発話がある
- **THEN** 出力動画でも該当発話の字幕が表示されている

#### Scenario: 末尾発話の保護
- **WHEN** 元動画の最後 30 秒以内に締めくくり発話(「ぜひ試してみてください」など)がある
- **THEN** 出力動画でも該当発話の字幕が表示されている

### Requirement: 項目#3 無駄な余白の除去

フィラー(「えーっと」「あの」など)、 言い直し、 微妙な間(0.2 秒以上の word 間ギャップ)、 鼻啜り音などの不要要素は **ほぼ除去** されなければならない。

#### Scenario: フィラーの除去
- **WHEN** 元動画にフィラー語が 5 個以上存在
- **THEN** 出力字幕からフィラーが 80% 以上削除されている

#### Scenario: word 間ギャップの圧縮
- **WHEN** 出力動画の連続する word 間ギャップを計測
- **THEN** ギャップ > 0.5 秒の箇所が 1 動画あたり 3 件以下

### Requirement: 項目#4 出力動画長

出力動画長は **60〜120 秒** の範囲に収まらなければならない(リール最適尺)。

#### Scenario: 動画長レンジ
- **WHEN** ffprobe で output.mp4 の duration を計測
- **THEN** 60.0 ≤ duration ≤ 120.0 秒

#### Scenario: 範囲外の検出
- **WHEN** duration が範囲外(< 60 or > 120 秒)
- **THEN** 不合格としてベースラインに記録される

### Requirement: 項目#5 字幕の誤認識の少なさ

出力字幕の誤認識(ReazonSpeech の音響的誤認識 + LLM 校正の取りこぼし)は **1 動画あたり 0〜1 個** に抑えなければならない。

#### Scenario: 誤認識率の目視判定
- **WHEN** テスト動画の出力字幕を目視確認
- **THEN** 期待値ドキュメントの「想定される誤認識パターン」に該当しない箇所での誤認識が 1 件以下

### Requirement: 項目#6 字幕タイミング同期

字幕の表示時刻と音声の発話時刻のずれは **0.5 秒未満** でなければならない。

#### Scenario: 同期計測
- **WHEN** ASS の Dialogue 開始時刻と、 同じ word の word.start を比較
- **THEN** その差が 0.5 秒以内

### Requirement: 項目#7 字幕の自然な切れ目

字幕の Dialogue は **意味のかたまり** で区切られていなければならない (SHALL)。 具体的には以下の順序で chunk 境界を決定する:

1. **強境界 (必ず flush)**: word.text 末尾が句読点 「。」「、」「!」「?」 で終わる場合、 その word 直後で flush
2. **中境界 (flush)**: 次 word との時刻 gap が **0.4 秒以上** の場合 (発話の自然な間 = 意味の区切り) で flush
3. **弱境界 (条件付き flush)**: chunk 内累積文字数が 12 文字以上 かつ 上記 1, 2 で flush されなかった場合のみ flush

word の途中で改行する (1 文字 dialogue が独立行になる) ことは **MUST NOT**。 ただし `clamp_oversized_word_ends` で `_orig_end` が設定された word (ASR ノイズで word.text と実発話が一致しない) は **独立 chunk として隔離** (SHALL)。

旧仕様の「助詞末尾抑制 (`_trailing_particles` リスト)」 ロジックは **廃止** (MUST NOT)。 word gap と句読点による境界判定で同等以上の品質を達成する。

#### Scenario: 句読点による強境界
- **WHEN** word.text 末尾が 「。」 で終わる
- **THEN** その word の直後で必ず flush し、 次 word から新 dialogue を開始する

#### Scenario: word gap による中境界
- **WHEN** 隣接する 2 word の gap (`next.start - cur.get("_orig_end", cur.end)`) が 0.4 秒以上
- **THEN** cur で flush し、 next から新 dialogue を開始する

#### Scenario: clamp 済み word の隔離
- **WHEN** word が `_orig_end` フィールドを持つ (clamp 済み)
- **THEN** その word は単独で 1 dialogue にする (前後 word と結合しない)

#### Scenario: 短 gap の連続発話は結合
- **WHEN** word gap が 0.4 秒未満で chunk 文字数が 12 文字未満
- **THEN** flush せず次 word を取り込んで chunk を延長する

### Requirement: 項目#8 字幕の読みやすい長さ

字幕の Dialogue のうち、 **2〜20 文字に収まるものが 90% 以上** (SHALL) でなければならない。

1 文字 dialogue (clamp 済み word を除く) は隣接 dialogue と統合可能 (SHALL)。 ただし統合後の合計が 20 文字を超える場合や、 前段が句点で終わっている場合は統合しない (MUST NOT)。

#### Scenario: 通常 dialogue の文字数範囲
- **WHEN** word_gap 中境界 + 句読点強境界で chunk を区切る
- **THEN** Dialogue の 90% 以上が 2〜20 文字に収まる

#### Scenario: 1 文字 dialogue の統合
- **WHEN** 1 文字 dialogue (clamp 済みでない) があり、 前後 dialogue との結合で 20 文字以下になる
- **THEN** 統合する

#### Scenario: clamp 済み 1 文字 dialogue は維持
- **WHEN** clamp 済み word (例: 「お」) で 1 文字 dialogue になっている
- **THEN** 統合せず単独 dialogue として残す (中身が壊れているため他 word との結合は誤り)

### Requirement: 項目#9 HOOK の的確さ

冒頭の HOOK テキストは **動画の核心を表現する一文** でなければならない。 比喩や言葉遊びで意味不明な文(例: 「食べ違いは選択で帳消し」)になってはならない。

#### Scenario: HOOK が動画と整合
- **WHEN** 期待値ドキュメントの「期待 HOOK の方向性」と出力 HOOK を比較
- **THEN** HOOK が動画の主張を明確に表現していると目視判定できる

### Requirement: 項目#10 テロップが被写体を隠さない

HOOK・CTA・トピックラベルなどのテロップは **被写体の顔を覆ったり、 画面端からはみ出したり** してはならない。

#### Scenario: HOOK の画面内収まり
- **WHEN** ffmpeg で HOOK 表示中(0-3秒)のフレームを抽出
- **THEN** HOOK テキストが画面幅 1080px の左右マージン 40px 内に収まる

#### Scenario: CTA の位置
- **WHEN** ffmpeg で CTA 表示中(末尾 3 秒)のフレームを抽出
- **THEN** CTA が画面下部 (y > h*0.7) に配置されており、 顔(中央付近)を覆わない

### Requirement: 項目#11 CTA の表示正常

CTA テキストは **絵文字豆腐(☒)なし** で、 指定通りに表示されなければならない。

#### Scenario: 絵文字レンダリング
- **WHEN** CTA テキストに含まれる文字がフォント(Noto Sans CJK JP)でサポートされているか確認
- **THEN** 豆腐文字(☒)が表示されない

### Requirement: 項目#12 トピックラベル

トピックラベルは **動画の構成を反映** していなければならない。 動画と関連しない一般的なラベルではダメ。

#### Scenario: トピックラベルの整合
- **WHEN** 期待値ドキュメントの「動画構成の主要トピック」と出力ラベルを比較
- **THEN** 出力ラベルが動画の構造を表現している(目視判定)

### Requirement: 項目#13 編集不要

業務量産モード(skip_preview=true)で、 **プレビュー編集なしで出力動画を投稿可能** でなければならない。プレビュー画面を通過しても字幕が崩れない。

#### Scenario: 量産モードでの動作
- **WHEN** skip_preview=true で動画を処理
- **THEN** プレビュー画面を経由せず output.mp4 が生成され、 字幕・テロップが正常に表示される

### Requirement: 項目#14 処理時間

5 分動画 1 本の処理時間は **10 分以内** でなければならない。

#### Scenario: 処理時間計測
- **WHEN** 5 分の元動画(test-videos/seitai_long.mov)を処理
- **THEN** /api/process リクエストから completed 通知までが 600 秒以内

### Requirement: テスト動画セットの整備

`test-videos/` ディレクトリに業務代表動画 3 本を整備し、 各動画に **期待値ドキュメント** を付与する。

#### Scenario: 動画ファイルの配置
- **WHEN** リポジトリ直下の `test-videos/` を確認
- **THEN** 以下のファイルが存在する:
  - `seitai_standard.mov` + `seitai_standard.expected.md`
  - `seitai_food.mov` + `seitai_food.expected.md`
  - `seitai_long.mov` + `seitai_long.expected.md`

#### Scenario: 期待値ドキュメントの内容
- **WHEN** 各 `*.expected.md` を確認
- **THEN** 以下のセクションが含まれる:
  - 動画の主張(1-2 文)
  - 残るべき発話キーワード(5-10 個)
  - 期待 HOOK の方向性(明示的な一文ではなくテーマレベル)
  - 想定出力動画長(範囲)
  - 想定される誤認識パターン(あれば)

### Requirement: 測定スクリプト

14 項目のうち **機械的に判定可能な項目** を自動測定するスクリプトを用意する。残りの項目は目視チェック用のテンプレートを提供する。

#### Scenario: スクリプト実行
- **WHEN** `python backend/scripts/measure_quality.py <job_id>` を実行
- **THEN** 出力動画の以下が JSON で返る:
  - 動画長(項目#4)
  - 1 字幕あたりの文字数分布(項目#8)
  - 末尾が格助詞である Dialogue 比率(項目#7)
  - 処理時間(項目#14)
  - CTA に含まれる文字の豆腐検出(項目#11)

#### Scenario: 目視テンプレ
- **WHEN** 目視判定が必要な項目を確認するとき
- **THEN** `measure_quality.py` がチェックリスト形式のマークダウンも出力する

### Requirement: ベースライン記録

本 change の完了時に、 14 項目の現状達成度を **1 度測定** し、 `baseline.md` に記録する。

#### Scenario: ベースライン作成
- **WHEN** 3 本のテスト動画を処理した直後
- **THEN** `openspec/changes/establish-quality-line/baseline.md` に各動画 × 14 項目の達成度マトリクスが書かれている

#### Scenario: 不合格項目の起点
- **WHEN** ベースラインで不合格となった項目がある
- **THEN** それぞれが新規 change の提案候補としてリスト化される

### Requirement: ASR ノイズの重複文字正規化

字幕生成パイプラインは word.text の連続重複文字を正規化する SHALL。 ReazonSpeech の subword 重複出力 (「ほほとんど」「ダエット」のうち重複部分など) を、 字幕表示前に去重する。

正規化規則:
- 同一文字が **2 連続** の場合は 1 文字に圧縮 (例: 「ほほとんど」 → 「ほとんど」)
- 同一文字が **3 連続以上** の場合は意図的な強調と見なして保持 (例: 「あああ」 → 「あああ」)

#### Scenario: 2 連続重複の圧縮
- **WHEN** word.text に「ほほとんど」 が含まれる
- **THEN** 字幕では「ほとんど」 として表示される

#### Scenario: 3 連続の保持
- **WHEN** word.text に「あああ」 が含まれる
- **THEN** 字幕でも「あああ」 として表示される

## Requirements
### Requirement: 14項目品質チェックリストの永続化

システム SHALL 業務量産投入の合格基準を 14 項目チェックリストとして永続化し、 各項目に対する合格条件(数値しきい値 or 目視判定基準)を文書化する。チェックリストは `openspec/specs/quality-line/spec.md`(本ファイル) に統一管理し、 他の設定ファイルや辞書に分散させない。

#### Scenario: チェックリストの参照
- **WHEN** 開発者が「業務量産投入できるか」を判断するとき
- **THEN** `openspec/specs/quality-line/spec.md` の 14 項目に対する達成度を確認できる

#### Scenario: 項目変更時の運用
- **WHEN** 14項目の合格基準を変更する必要がある
- **THEN** その変更は新規 change の proposal で提案され、 本 spec の MODIFIED Requirements として記録される

### Requirement: 項目#1 ストーリーの保全

出力動画は **元動画の主張・流れ** を保持しなければならない。重要な発話(例: 「お客様が悩まれているダイエットの食事の話をしようと思います」)が削除されてはならない。

#### Scenario: 元動画の主張が出力動画でも分かる
- **WHEN** テスト動画の出力字幕全文を読む
- **THEN** 期待値ドキュメント `*.expected.md` の「動画の主張」と整合する内容が含まれている

#### Scenario: 重要発話の保護
- **WHEN** 期待値ドキュメントの「残るべき発話キーワード」リストを確認する
- **THEN** すべてのキーワードが出力字幕に出現する

### Requirement: 項目#2 冒頭・末尾の発話保護

期待値ドキュメント `*.expected.md` の「残るべき発話キーワード」が **すべて出力字幕に出現** しなければならない。

物理保護(voice_segments に発話が含まれる)に加え、 **3段目 ReazonSpeech がその発話を認識できない場合でも、 1段目 ASR の補完によって字幕に出現する** こと。 3段目 first_word.start が動画長の 5%(最低 2 秒)を超える場合、 1段目 words を cut.mp4 / cut2.mp4 内時刻に remap した上で hybrid prepend する。

#### Scenario: 3段目 冒頭認識ミスの補完
- **WHEN** 3段目 transcribe (cut2 or cut.mp4 audio) の first_word.start が動画長 × 0.05 (最低 2 秒) を超える
- **THEN** 1段目 words を voice_segments → cut2_voices で remap し、 3段目 first_word.start - 0.1 秒より前の word を hybrid 補完として字幕用 words の先頭に prepend

#### Scenario: 3段目 冒頭認識成功時は補完しない
- **WHEN** 3段目 transcribe の first_word.start が動画長 × 0.05 (最低 2 秒) 以下
- **THEN** 1段目補完は発動せず、 字幕用 words は 3段目のみで構成される

#### Scenario: 補完 word の順序保証
- **WHEN** 1段目補完 word を字幕用に追加
- **THEN** 補完 words を start で sort してから prepend、 順序崩壊を起こさない

### Requirement: 項目#3 無駄な余白の除去

フィラー(「えーっと」「あの」など)、 言い直し、 微妙な間(0.2 秒以上の word 間ギャップ)、 鼻啜り音などの不要要素は **ほぼ除去** されなければならない。

#### Scenario: フィラーの除去
- **WHEN** 元動画にフィラー語が 5 個以上存在
- **THEN** 出力字幕からフィラーが 80% 以上削除されている

#### Scenario: word 間ギャップの圧縮
- **WHEN** 出力動画の連続する word 間ギャップを計測
- **THEN** ギャップ > 0.5 秒の箇所が 1 動画あたり 3 件以下

### Requirement: 項目#4 出力動画長

出力動画長は **60〜120 秒** の範囲に収まらなければならない(リール最適尺)。

#### Scenario: 動画長レンジ
- **WHEN** ffprobe で output.mp4 の duration を計測
- **THEN** 60.0 ≤ duration ≤ 120.0 秒

#### Scenario: 範囲外の検出
- **WHEN** duration が範囲外(< 60 or > 120 秒)
- **THEN** 不合格としてベースラインに記録される

### Requirement: 項目#5 字幕の誤認識の少なさ

出力字幕の誤認識(誤認識 + 語順崩壊 + 重複表示)は 1 動画あたり 0〜1 個に抑えられること (SHALL)。

1 段目 ASR の認識ミスを吸収するため、 以下の **3 段防御** をすべて備えること (SHALL):

1. **動画固有辞書** (`summarize_with_mishearings`): LLM が動画 transcript 全体から誤認識ペアを抽出する。 プロンプトには「subword 化された短い断片」「意味不明な並び」「反義語的誤り」「1 字目欠落」 などの例を含むこと
2. **静的辞書** (`jp_corrections.txt`): 繰り返し観測される誤認識を蓄積
3. **LLM 校正** (`correct_transcript_segments`): 動画固有辞書で吸収しきれない subword 列を、 文脈から推測して書き換える。 長さ制約は **-70% 〜 +50%** の範囲で書き換えを許容すること (SHALL)

#### Scenario: subword 断片の動画固有辞書による吸収
- **WHEN** ASR が「事への」 「悪い要」 「ボメ」 のような subword 断片を出す
- **THEN** `summarize_with_mishearings` がこれらを誤認識として抽出し、 `apply_corrections_to_text` で正しい text に置換される

#### Scenario: LLM 校正による文脈推測修正
- **WHEN** subword 列 5 文字以下で意味が通らない segment が存在
- **THEN** `correct_transcript_segments` が周辺の文脈から推測し、 意味の通る日本語に書き換える (元の -70% 〜 +50% の範囲)

#### Scenario: 長さチェックの拒否範囲
- **WHEN** LLM が segment を 元の 2.5 倍超、 もしくは 15 文字以上長く書き換える
- **THEN** その修正は拒否され、 retry 機構 (控えめ校正) で再試行される

### Requirement: 項目#6 字幕タイミング同期

字幕の表示時刻と音声の発話時刻のずれは 0.5 秒未満でなければならない (SHALL)。 字幕用 words は cut2.mp4 内時刻空間で生成され、 remap による時刻ねじれを発生させてはならない (MUST NOT)。

#### Scenario: 同期計測
- **WHEN** ASS の Dialogue 開始時刻と、 同じ word の word.start を比較
- **THEN** その差が 0.5 秒以内

#### Scenario: 時刻空間の一貫性
- **WHEN** 字幕用 words が生成された時刻空間を確認
- **THEN** cut2.mp4(または cut.mp4)内時刻のみで構成され、 元動画時刻からの 2 段 remap を経由していない

### Requirement: 項目#7 字幕の自然な切れ目

字幕の Dialogue のうち、 末尾が単一文字格助詞・接続助詞・活用語尾 (はがをにでとのもへやかなてばしず) で終わるものは **10% 未満** (SHALL) にしなければならない。

接続助詞 (「て」「ば」「し」「ず」 など) や 格助詞 (「は」「が」「を」「に」 など) の直後で flush するのは、 ハードリミット (`max_chars × 1.5` 以上) に達した時だけ許容される (SHALL)。 それ以外は次の語まで持ち越すこと (SHALL)。

また、 句読点「、」 では flush せず、 「。」 「！」 「？」 等の文末記号のみで flush すること (MUST)。 「、」 で切ると短い断片が量産され、 #8 文字数比率を下げる副作用がある。

#### Scenario: 助詞抑制の動作
- **WHEN** current_text が「結論から言うと一番大事なのは」 で次の word が「メンタル」
- **THEN** 「は」 直後で flush せず、 「メンタル」 まで持ち越して 「結論から言うと一番大事なのはメンタル」 1 つの Dialogue にする(hard_limit 内なら)

#### Scenario: 「、」 では flush しない
- **WHEN** current_text に「、」 が含まれる
- **THEN** 「、」 自体では flush せず、 句点 or hard_limit まで継続

### Requirement: 項目#8 字幕の読みやすい長さ

字幕の Dialogue のうち、 **8〜14 文字に収まるものが 70% 以上** (SHALL) でなければならない。

8 文字未満の Dialogue は隣接 Dialogue と統合可能(SHALL)。 ただし統合後の合計が max_chars × 1.4 を超える場合や、 隣接前段が句点で終わっている場合は統合しない (MUST NOT)。

#### Scenario: 短い Dialogue の統合
- **WHEN** 隣接する 2 つの Dialogue のうち、 どちらかが 8 文字未満で、 合計が max_chars × 1.4 以下、 前段が句点で終わっていない
- **THEN** 2 つを統合して 1 つの Dialogue にする

#### Scenario: 統合の上限保証
- **WHEN** 統合候補の合計文字数が max_chars × 1.4 を超える
- **THEN** 統合しない(独立した Dialogue として残す)

### Requirement: 項目#9 HOOK の的確さ

冒頭の HOOK テキストは **動画の核心を表現する一文** でなければならない。 比喩や言葉遊びで意味不明な文(例: 「食べ違いは選択で帳消し」)になってはならない。

#### Scenario: HOOK が動画と整合
- **WHEN** 期待値ドキュメントの「期待 HOOK の方向性」と出力 HOOK を比較
- **THEN** HOOK が動画の主張を明確に表現していると目視判定できる

### Requirement: 項目#10 テロップが被写体を隠さない

HOOK・CTA・トピックラベルなどのテロップは **被写体の顔を覆ったり、 画面端からはみ出したり** してはならない。

#### Scenario: HOOK の画面内収まり
- **WHEN** ffmpeg で HOOK 表示中(0-3秒)のフレームを抽出
- **THEN** HOOK テキストが画面幅 1080px の左右マージン 40px 内に収まる

#### Scenario: CTA の位置
- **WHEN** ffmpeg で CTA 表示中(末尾 3 秒)のフレームを抽出
- **THEN** CTA が画面下部 (y > h*0.7) に配置されており、 顔(中央付近)を覆わない

### Requirement: 項目#11 CTA の表示正常

CTA テキストは **絵文字豆腐(☒)なし** で、 指定通りに表示されなければならない。

#### Scenario: 絵文字レンダリング
- **WHEN** CTA テキストに含まれる文字がフォント(Noto Sans CJK JP)でサポートされているか確認
- **THEN** 豆腐文字(☒)が表示されない

### Requirement: 項目#12 トピックラベル

動画には **最低 2 件、 最大 4 件のトピックラベル** が表示されること (SHALL)。

`detect_topics` は 1 回目で 0 件を返した場合、 強制分割プロンプト (`_TOPICS_FORCE_PROMPT`) で 1 回リトライすること (SHALL)。 リトライプロンプトには「必ず最低 2 個に分割」 を明示する。

#### Scenario: 0 件のリトライ発動
- **WHEN** 1 回目の detect_topics が 0 件を返す
- **THEN** `_TOPICS_FORCE_PROMPT` で LLM をリトライし、 返り値 (2-4 件想定) を採用する

#### Scenario: 1 件以上ならリトライしない
- **WHEN** 1 回目で 1 件以上のトピックが返る
- **THEN** リトライせずそのまま採用

#### Scenario: リトライも失敗
- **WHEN** 2 回目も 0 件
- **THEN** 0 件のまま返し、 warning ログを出す

### Requirement: 項目#13 編集不要

業務量産モード(skip_preview=true)で、 **プレビュー編集なしで出力動画を投稿可能** でなければならない。プレビュー画面を通過しても字幕が崩れない。

#### Scenario: 量産モードでの動作
- **WHEN** skip_preview=true で動画を処理
- **THEN** プレビュー画面を経由せず output.mp4 が生成され、 字幕・テロップが正常に表示される

### Requirement: 項目#14 処理時間

動画 1 本の処理時間は **10 分以内** であること (SHALL)。 hang や無限待機は MUST NOT 発生してはならない。

`cut_and_concat` 内の ffmpeg subprocess.run は **timeout=600** で fail-fast すること (SHALL)。 timeout 時は明示的に RuntimeError を raise し、 ユーザーには「処理に時間がかかりすぎました」 等のエラーメッセージが表示される。

segments が 10 個を超える場合は filter_complex を 1 つの巨大 graph にせず、 **chunk 分割 + concat demuxer** で結合すること (SHALL)。 これにより ffmpeg のメモリ消費が分散され、 docker VM resource starvation を防ぐ。

#### Scenario: timeout 発火
- **WHEN** ffmpeg cut_and_concat が 600 秒を超えても完了しない
- **THEN** RuntimeError が raise され、 ジョブは failed 状態になる

#### Scenario: 大量 segments の chunk 分割
- **WHEN** segments の数が 10 個を超える
- **THEN** segments を 10 個ずつ chunk に分割し、 各 chunk を個別 ffmpeg で処理 → concat demuxer で結合する

#### Scenario: 小規模 segments は従来通り
- **WHEN** segments ≤ 10 個
- **THEN** 1 パスの filter_complex で処理する (chunk 分割なし)

### Requirement: テスト動画セットの整備

`test-videos/` ディレクトリに業務代表動画 3 本を整備し、 各動画に **期待値ドキュメント** を付与する。

#### Scenario: 動画ファイルの配置
- **WHEN** リポジトリ直下の `test-videos/` を確認
- **THEN** 以下のファイルが存在する:
  - `seitai_standard.mov` + `seitai_standard.expected.md`
  - `seitai_food.mov` + `seitai_food.expected.md`
  - `seitai_long.mov` + `seitai_long.expected.md`

#### Scenario: 期待値ドキュメントの内容
- **WHEN** 各 `*.expected.md` を確認
- **THEN** 以下のセクションが含まれる:
  - 動画の主張(1-2 文)
  - 残るべき発話キーワード(5-10 個)
  - 期待 HOOK の方向性(明示的な一文ではなくテーマレベル)
  - 想定出力動画長(範囲)
  - 想定される誤認識パターン(あれば)

### Requirement: 測定スクリプト

14 項目のうち **機械的に判定可能な項目** を自動測定するスクリプトを用意する。残りの項目は目視チェック用のテンプレートを提供する。

#### Scenario: スクリプト実行
- **WHEN** `python backend/scripts/measure_quality.py <job_id>` を実行
- **THEN** 出力動画の以下が JSON で返る:
  - 動画長(項目#4)
  - 1 字幕あたりの文字数分布(項目#8)
  - 末尾が格助詞である Dialogue 比率(項目#7)
  - 処理時間(項目#14)
  - CTA に含まれる文字の豆腐検出(項目#11)

#### Scenario: 目視テンプレ
- **WHEN** 目視判定が必要な項目を確認するとき
- **THEN** `measure_quality.py` がチェックリスト形式のマークダウンも出力する

### Requirement: ベースライン記録

本 change の完了時に、 14 項目の現状達成度を **1 度測定** し、 `baseline.md` に記録する。

#### Scenario: ベースライン作成
- **WHEN** 3 本のテスト動画を処理した直後
- **THEN** `openspec/changes/establish-quality-line/baseline.md` に各動画 × 14 項目の達成度マトリクスが書かれている

#### Scenario: 不合格項目の起点
- **WHEN** ベースラインで不合格となった項目がある
- **THEN** それぞれが新規 change の提案候補としてリスト化される

### Requirement: Stage 5b として cut2.mp4 を 3 段目 transcribe する

(廃止)字幕用 words は 1 段目 ASR + 1 段 remap で生成する。 3 段目 transcribe は字幕用には不要 (MUST NOT)。

`_run_processing` の Stage 5b では:
- 1 段目 ASR の words (Stage 3 で生成) を保持
- voice_segments と cut2_voices (施策F 未発動なら None) を `build_orig_to_cut2_mapping` で合成
- 合成 mapping で 1 段目 words を cut2 内時刻に remap → 字幕用 words

#### Scenario: 3 段目 transcribe をスキップ
- **WHEN** Stage 5b に到達
- **THEN** `extract_audio(cut2_output, cut2_audio)` および `transcribe_with_words(cut2_audio, ...)` は呼ばれない

#### Scenario: 1 段マッピングでの remap
- **WHEN** 字幕用 words の生成
- **THEN** `build_orig_to_cut2_mapping` が voice_segments と cut2_voices_used で 1 回呼ばれ、 `remap_words_with_mapping` が 1 段目 words で 1 回呼ばれる

### Requirement: `protect_words_from_silences` ヘルパー

`backend/app/services/silence.py` に `protect_words_from_silences(silences, words, margin)` 関数を提供する。 silences のうち、 word が認識された範囲を穴あけして除外する。

#### Scenario: silence と word の重なり穴あけ
- **WHEN** silence `[0.0, 20.75]`、 word `{"start": 20.38, "end": 20.94}`、 margin=0.1
- **THEN** 返り値は `[{"start": 0.0, "end": 20.28}]` (word.end + margin = 21.04 > silence.end 20.75 なので後ろは無し)

#### Scenario: silence の中央に word がある場合の 2 分割
- **WHEN** silence `[0.0, 30.0]`、 word `{"start": 10.0, "end": 12.0}`、 margin=0.1
- **THEN** 返り値は `[{"start": 0.0, "end": 9.9}, {"start": 12.1, "end": 30.0}]`

#### Scenario: silence と重なる word が無い場合
- **WHEN** silence `[5.0, 10.0]`、 words `[]`
- **THEN** 返り値は `[{"start": 5.0, "end": 10.0}]` (変更なし)

#### Scenario: 複数 word の merge
- **WHEN** silence `[0.0, 30.0]`、 words `[{"start": 5.0, "end": 7.0}, {"start": 6.5, "end": 8.0}]`、 margin=0.1
- **THEN** 返り値は `[{"start": 0.0, "end": 4.9}, {"start": 8.1, "end": 30.0}]` (word が merge されてから穴あけ)

### Requirement: ReazonSpeech の連続呼出に対する堅牢性

`_transcribe_with_reazonspeech` は、 同一プロセス内の連続呼出で発生する `freeze()/unfreeze()` 関連の状態破損エラーから自動回復しなければならない (SHALL)。

具体的には、 transcribe が `Cannot unfreeze partially` 等のキーワードを含むエラーで失敗した場合、 `_load_reazonspeech_model.cache_clear()` でキャッシュを破棄し、 fresh load して 1 回 retry すること (SHALL)。 retry も失敗したら WhisperX フォールバックへ抜けること (SHALL)。

業務量産 14 本連続処理 (= 約 42 回の transcribe 呼出) で **1 回も hang や失敗で停止してはならない** (MUST NOT)。

#### Scenario: 状態破損エラーからの自動回復
- **WHEN** `transcribe()` が「Cannot unfreeze partially without first freezing」 を含むエラーを raise
- **THEN** `_load_reazonspeech_model.cache_clear()` が呼ばれ、 fresh load 後に再度 transcribe される

#### Scenario: state エラー以外は retry しない
- **WHEN** `transcribe()` が「audio file not found」 のような state とは無関係のエラーを raise
- **THEN** retry せず WhisperX フォールバックへ即抜ける

#### Scenario: 防御的 freeze の常時呼出
- **WHEN** transcribe 前
- **THEN** `model.freeze()` を try/except で呼出し、 内部状態を正規化する(失敗時は無視)

### Requirement: 合成マッピング `build_orig_to_cut2_mapping` ヘルパー

`backend/app/services/silence.py` に `build_orig_to_cut2_mapping(voice_segments, cut2_voices)` を提供する (SHALL)。

返り値は `[{"orig_start": float, "orig_end": float, "cut2_start": float}, ...]` で、 word.start が `[orig_start, orig_end)` の中にあれば、 `cut2_start + (word.start - orig_start)` で cut2 内時刻が得られる。

cut2_voices が None の場合は施策F 未発動 (cut.mp4 = 最終動画) として、 voice_segments を単純に cut.mp4 内時刻にマップしたテーブルを返す。

#### Scenario: 施策F 発動時の合成
- **WHEN** voice_segments と cut2_voices の両方が与えられる
- **THEN** voice_segments の各範囲と cut2_voices の交差を計算し、 元時刻 → cut2 内時刻の直接マッピングを返す

#### Scenario: 施策F 未発動時
- **WHEN** cut2_voices が None
- **THEN** voice_segments をそのまま cut.mp4 内時刻へのマップとして返す (orig_start, orig_end, cut2_start = cut_offset)

### Requirement: `remap_words_with_mapping` ヘルパー

`backend/app/services/silence.py` に `remap_words_with_mapping(words, mappings)` を提供する (SHALL)。

各 word について、 `word.start` が含まれる mapping を探し、 cut2 内時刻に変換する。 word の `end` が mapping 範囲を超える場合は clamp する。

#### Scenario: 標準的な remap
- **WHEN** word.start が mapping[i] の範囲内
- **THEN** 返り値の word は `start = mapping.cut2_start + (word.start - mapping.orig_start)` になる

#### Scenario: 削除区間にかかる word の clamp
- **WHEN** word.end が mapping[i].orig_end を超える
- **THEN** word.end は mapping.orig_end までで clamp され、 新しい end が cut2 時刻でも対応して clamp される

### Requirement: 音声前処理 (afftdn + loudnorm) の適用

`extract_audio` は元動画から audio.wav を生成する際、 ASR 認識精度を高めるための前処理として以下のフィルタを適用すること (SHALL):

- **afftdn** (FFT-based denoise) で背景ノイズを除去 (nr=12, nf=-25)
- **loudnorm** (EBU R128) で音量を -16 LUFS、 LRA=11、 TP=-1.5 に正規化

これらは 16kHz mono PCM への変換の前段で適用される (SHALL)。

#### Scenario: extract_audio のフィルタチェーン
- **WHEN** `extract_audio(input_video, audio_path)` を呼出
- **THEN** ffmpeg コマンドに `-af afftdn=nr=12:nf=-25,loudnorm=I=-16:LRA=11:TP=-1.5` が含まれる

#### Scenario: 出力フォーマットの維持
- **WHEN** 前処理後の audio.wav を確認
- **THEN** sample rate 16000、 mono、 PCM 形式である (既存と同じ)

### Requirement: 字幕プレビューでの誤認識候補ハイライト

`/api/transcribe/{job_id}` のレスポンスは、 各 segment に `suspicious: bool` フィールドを含むこと (SHALL)。 suspicious=true の segment は frontend で **赤字 + 警告アイコン** で表示され、 ユーザーが視覚的に修正対象を特定できる (SHALL)。

検出ロジック (`detect_suspicious_segments`) は以下のいずれかに該当する segment を suspicious=true とする (SHALL):
- (a) 5 文字以下で助詞・記号比率が 50% 以上
- (b) 同一文字の 3 連続以上 (subword 反復)
- (c) 句点・記号で始まる (segment 境界の不自然)
- (d) 1-2 文字で文末記号で終わらない (subword 断片)

#### Scenario: subword 断片の検出
- **WHEN** segment.text = "客 事への 食" (5 文字、 助詞・記号 1 個)
- **THEN** suspicious=true

#### Scenario: 正常な日本語は false positive にならない
- **WHEN** segment.text = "結論から言うと一番大事なのは" (普通の発話)
- **THEN** suspicious=false

#### Scenario: API レスポンスの後方互換
- **WHEN** 既存 frontend (suspicious フィールドを知らない) がレスポンスを処理
- **THEN** suspicious フィールドは無視され、 既存の編集 UI で表示される

### Requirement: `_chunk_segments` ヘルパー

`backend/app/services/ffmpeg.py` に `_chunk_segments(segments, chunk_size=10)` を提供する (SHALL)。 segments を `chunk_size` 個ずつのリストに分割して返す。

#### Scenario: 25 segments を 10 ずつに分割
- **WHEN** `_chunk_segments(segments=25 個, chunk_size=10)`
- **THEN** 返り値は `[10 segments, 10 segments, 5 segments]` の 3 つ

