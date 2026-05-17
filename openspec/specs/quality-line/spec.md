## ADDED Requirements

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

字幕は **格助詞直後(は・が・を・に・で・と・の・も)** または **subword の途中** で機械的に切れてはならない。句読点・自然なフレーズ境界で区切ること。

#### Scenario: 助詞直後で切れない
- **WHEN** 出力字幕の各 Dialogue の末尾文字を確認
- **THEN** 末尾が格助詞である Dialogue が全体の 10% 以下

#### Scenario: subword 途中で切れない
- **WHEN** 出力字幕で「ボディ」「メイク」のような単語が連続する 2 つの Dialogue に分かれていないか確認
- **THEN** is_word_start=False で word の途中で切れた箇所がない(目視確認)

### Requirement: 項目#8 字幕の読みやすい長さ

1 字幕(Dialogue 行)の文字数は **8〜14 文字** が望ましい。

#### Scenario: 文字数レンジ
- **WHEN** ASS の各 Dialogue の text を文字数カウント
- **THEN** 全 Dialogue のうち 8〜14 文字に収まるものが 70% 以上

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

出力字幕の誤認識(誤認識 + 語順崩壊)は 1 動画あたり 0〜1 個に抑えられること(SHALL)。 特に subword レベルの語順崩壊(例:「様が悩まれているダイエットお客」のような順序乱れ)は **MUST NOT** 発生してはならない。

字幕用 words は cut2.mp4(または施策F 未発動時は cut.mp4)を直接 transcribe したものを使うこと(SHALL)。 1段目 transcribe (元動画) の word を `_filter_words_by_segments` で 2 段 remap した結果を字幕に使うのは **MUST NOT** (過去にこの構成で語順崩壊が確認された)。

#### Scenario: 誤認識率の目視判定
- **WHEN** テスト動画の出力字幕を目視確認
- **THEN** 期待値ドキュメントの「想定される誤認識パターン」に該当しない箇所での誤認識が 1 件以下

#### Scenario: subword 語順崩壊の禁止
- **WHEN** 出力字幕の任意の Dialogue を確認
- **THEN** 「お客様」が「様...お客」のように同一語の subword が異なる位置に分散する崩壊が発生していない

#### Scenario: 字幕用 words の生成元
- **WHEN** Stage 5 の実装を確認
- **THEN** 字幕用 sub_segments は cut2.mp4 を直接 transcribe した words(3 段目)から生成されている(施策F 未発動時は cut.mp4 の 2 段目 words からのフォールバック)

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

### Requirement: Stage 5b として cut2.mp4 を 3 段目 transcribe する

`_run_processing` の Stage 5 を 2 段(5a/5b)に分割し、 5b では cut2.mp4 を独立した audio として抽出した上で transcribe_with_words に流すこと (SHALL)。

#### Scenario: 3 段目 transcribe の実行
- **WHEN** 施策F が発動して cut2.mp4 が生成された
- **THEN** Stage 5b で `extract_audio(cut2_output, cut2_audio)` および `transcribe_with_words(cut2_audio, ...)` が呼ばれる

#### Scenario: 3 段目 transcribe のフォールバック
- **WHEN** 施策F が発動せず cut2.mp4 が生成されない(oversized_2nd が空)
- **THEN** Stage 5b は 3 段目 transcribe をスキップし、 2 段目の words_cut(cut.mp4 ベース)を字幕用に使う

#### Scenario: 動画カット判定との分離
- **WHEN** 動画カット判定(施策F/G) と字幕生成のロジックを確認
- **THEN** 施策F/G は 1 + 2 段目 ASR(words / words_cut)のみを使用し、 字幕生成は 3 段目 (words_cut3) のみを使用している

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

