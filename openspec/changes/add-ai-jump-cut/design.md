## Context

現状の処理パイプライン（`backend/app/routers/video.py:_run_processing`）は以下の順序：

1. 音声抽出（ffmpeg）
2. 無音検出（ffmpeg silencedetect）
3. `compute_voice_segments` で有音区間を算出
4. `cut_and_concat` で結合
5. （オプション）字幕生成・焼き込み

Whisper による字幕生成は **カット後の動画** に対して走るため、フィラー削除に必要な「元動画上のタイムスタンプ」と一致しない。AIジャンプカットは原則として、**カット前の音声** を Whisper で word-level transcribe し、その結果をフィラー辞書・LLM・文末閾値で解析して削除区間を作り出す必要がある。

既存の `compute_voice_segments` は「無音区間 → 有音区間」の差分計算を行うだけで、複数種類の削除区間をマージする機能はない。

## Goals / Non-Goals

**Goals:**
- 既存の無音削除パイプラインに3種の検出を非破壊で統合する
- フロントエンドの変更は最小限（トグル1つ）
- LLM プロバイダ（OpenAI / Anthropic）を環境変数で切替可能にする
- `enable_jump_cut: false` の場合は既存挙動を完全に保つ
- 失敗時（LLM API エラー等）はジョブを止めず、フィラー削除と文末カットだけで継続する degraded mode

**Non-Goals:**
- プレビューUI・承認フロー
- 英語など日本語以外への対応（本変更ではJP固定）
- ユーザーがフィラー辞書を編集できるUI
- 削除区間ごとの個別ON/OFF（全自動・全機能ON）

## Decisions

### D1. Whisper 実行タイミングを「カット前」に変更

- **採用**: 音声抽出後すぐに word-level timestamps 付きで Whisper を実行する
- **代替**: 一度カットしてから Whisper、削除区間を別途算出して2回目のカット → タイムスタンプ整合性が壊れる、二度手間
- **理由**: ジャンプカット検出には word-level timestamps が必須。字幕生成にも同じ transcript を再利用できる（Whisper を1回しか呼ばない）

### D2. 検出結果は「削除区間のリスト」として統一

- **採用**: `[{start, end}, ...]` 形式で silence/filler/restatement/tempo すべてを表現し、上位でマージ
- **代替**: 種類別に別フローで処理 → コードが分岐する
- **理由**: 既存の `compute_voice_segments` は「無音区間 → 有音区間」の差分を計算するだけなので、シルバーバレットとして「削除区間をすべて足し合わせてから差分計算」に拡張すれば全種類の検出を1経路で扱える

### D3. LLM クライアントの抽象化

- **採用**: `backend/app/services/llm.py` に `detect_restatements(transcript: list[Word]) -> list[Range]` を1関数だけ公開。内部で `LLM_PROVIDER` 環境変数を見て OpenAI または Anthropic を呼ぶ
- **代替**: 各プロバイダごとに別ファイル、ルーター側で分岐 → 呼び出し側が増えるたびに分岐が増える
- **理由**: 呼び出し側は1関数だけ知っていればよい。将来的に AI Gateway や別プロバイダに差し替えるときも影響範囲が狭い

### D4. LLM の出力フォーマット

- **採用**: JSON モード（OpenAI: `response_format={"type":"json_object"}` / Anthropic: tool use）で `{"ranges": [{"start": float, "end": float, "reason": str}, ...]}` を強制
- **代替**: 自然言語で返させてパース → 不安定
- **理由**: Pydantic で検証してから採用すればハルシネーションも吸収できる

### D5. フィラー辞書はテキストファイル

- **採用**: `backend/app/data/jp_fillers.txt` に1行1ワードで持ち、起動時にメモリにロード
- **代替**: Python コード内のリテラル / DB 管理 → 編集しづらい / オーバースペック
- **理由**: 辞書は静的でほぼ変わらない。テキストファイルが一番編集しやすい

### D6. 文末テンポカットの判定

- **採用**: word transcript 内で `[、。？！]` を含む単語の end と次の単語の start の差分が `tempo_max_pause`（デフォ 0.4s）を超えた場合、`tempo_target_pause`（デフォ 0.2s）に短縮するように削除区間を作る
- **代替**: 全文末で固定時間にトリム → 自然な間が消える
- **理由**: 元の話速を維持しつつ「無駄に長い間」だけ詰められる

### D7. 失敗時の degraded mode

- **採用**: LLM 呼び出しが例外を投げたら言い直し検出だけスキップ、ログに warning を出して filler + tempo の結果だけで継続
- **理由**: LLM API は外部依存。落ちたときに動画全体が失敗するのは UX が悪い

## Risks / Trade-offs

- **[Whisper の word-level timestamps の精度] → Mitigation**: `base` モデルだと日本語の word boundary が粗いケースがある。実装中にサンプル動画で検証し、必要なら `small` にアップグレードする（処理時間とのトレードオフ）
- **[LLM のハルシネーション]** 存在しないタイムスタンプを返す可能性 → **Mitigation**: 返ってきた range が transcript 内の word 範囲に含まれていることを後段でバリデートし、外れた range は破棄する
- **[アグレッシブな削除でオリジナリティが消える]** → **Mitigation**: フィラー辞書を保守的に始める（最小限の確実なフィラーだけ）、文末カットは「短縮」であって「ゼロ化」しない
- **[LLM コスト]** 長尺動画で transcript が増えるとトークンも増える → **Mitigation**: 現状 3分上限なので問題は小さい。将来的に長尺対応するときは transcript をチャンク分割
- **[Whisper 2回呼び出しによる処理時間増]** → カット前後で2回呼ぶと長尺で重い → **Mitigation**: D1 により1回に統一済み。字幕焼き込みは同じ transcript からタイムスタンプを再計算して使う

## Migration Plan

破壊的変更ではない（`enable_jump_cut: false` がデフォルト）。

1. バックエンド: 新規ファイル追加 → 既存パイプラインに stage 追加 → `requirements.txt` 更新
2. `.env.example` を更新し、本番デプロイ前に `LLM_PROVIDER` と API キーを設定する
3. フロントエンド: トグル追加
4. ロールバック: `enable_jump_cut: false` がデフォルトのため、フロントの該当トグルを隠すだけで実質的に旧挙動に戻せる

## Open Questions

- **Whisper モデルサイズ**: `base` のままで日本語 word timestamps の精度が足りるか、`small` に上げるか → 実装中にサンプル検証
- **LLM プロバイダのデフォルト**: OpenAI と Anthropic どちらをデフォルトにするか → ユーザーが既に持っている API キーに依存。`.env.example` には両方記載してどちらか必須にする
- **削除した区間の最小長**: あまりに短い削除（< 50ms 等）は ffmpeg のフレーム単位で吸収されるので無視するか → 実装時に閾値を導入
