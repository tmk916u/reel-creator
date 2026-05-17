## Context

### 現在の voice_segments 計算フロー
```
1. silero VAD で音声/無音を判別 → silences (ML ベース)
2. silero が None なら ffmpeg silencedetect (-25 dB 閾値) でフォールバック
3. micro_silence_min_duration > 0 なら ffmpeg silencedetect で短い無音(0.1秒)も検出 → union
4. snap_silences_to_word_boundaries: silences が word の中央を切らないよう境界調整
5. compute_voice_segments(silences, duration, padding): silences の補集合 = voice_segments
```

### 観測事実 (job 994f47eb / tight preset)
- 元動画 250.27 秒
- 1 段目 ReazonSpeech が **20.38 秒目で「客」「様」「が」「悩」** を認識(信頼性高い、 subword timestamp ±0.05秒)
- silero VAD の silences 第 1 行: `0.00-20.75` (1段目 ASR の発話開始 20.38 を無音と判断)
- micro_silence は 0-3 秒, 3-5 秒, ... を 0.10 秒以上の無音として検出 → silero と union
- 結果: silences `0.00-20.821`
- voice_segments の最初のセグメント: 20.77-22.62 秒 (0.37 秒分の冒頭発話が消失)

silero VAD が cut.mp4 (165.2 秒) で 24 秒目まで認識しないのも、 同様に「短い区間で発話が認識されているが silero が無音判定」している。

### snap_silences_to_word_boundaries の限界
`snap_silences_to_word_boundaries(silences, words)` は既に実装されている (Stage 3 末尾、 L411)。 しかしこれは **silence の境界を最寄りの word 境界に揃える** だけで、 word を完全に含む長い silence を分割しない:

```python
# 元: silence [0.0, 20.75], word [20.38, 20.94]
# snap 後: silence [0.0, 20.38] (or [0.0, 20.94]) になる可能性
```

実際の snap 実装次第だが、 観察結果では voice_segments の最初が 20.77 から始まっているので、 snap が「word の前端へスナップ」されていない、 もしくは順序や処理の都合で word が無視されている。

### 制約・依存
- silero VAD はモデルキャッシュ済みで、 推論は安定
- 1 段目 transcribe (元時刻 250 秒) の word.start/end は信頼性高い
- 既存テスト 107 件を維持
- ReazonSpeech が確率的に誤認識する場合の安全策が必要(margin 制御)

## Goals / Non-Goals

**Goals:**
- 1 段目 ASR が認識した発話を voice_segments で **物理的に保護** する
- 結果として cut.mp4 / cut2.mp4 から冒頭発話が消える問題を根治
- 項目#2 (冒頭・末尾の発話保護) と #5 (字幕誤認識) の合格

**Non-Goals:**
- silero VAD のチューニング(ML モデル自体の改善)
- snap_silences_to_word_boundaries の改修(役割が異なる、 境界スナップは別目的)
- enable_jump_cut が False (1段目 transcribe を行わない) ケースの対応(対象外、 jump_cut なしなら本問題は発生しない)
- cut.mp4 / cut2.mp4 の音響特性改善(別 change のスコープ)

## Decisions

### D1: `protect_words_from_silences(silences, words, margin)` を silence.py に追加
**実装方針**:
```python
def protect_words_from_silences(
    silences: list[dict], words: list[dict], margin: float = 0.1,
) -> list[dict]:
    """silences のうち、 ASR が word を認識した範囲を穴あけして除外する。

    silence と重なる word があれば、 silence を word の前端(margin 含む) より
    前と、 word の後端(margin 含む)より後に分割する。
    word が完全に silence の中央にある場合、 silence は 2 つに分かれる。
    """
    if not words:
        return silences
    out: list[dict] = []
    for s in silences:
        s_start, s_end = s["start"], s["end"]
        overlapping = [
            w for w in words
            if w["start"] < s_end and w["end"] > s_start
        ]
        if not overlapping:
            out.append(s)
            continue
        # word のレンジを margin 付きで構築し、 silence からくり抜く
        protected_ranges = sorted(
            (max(s_start, w["start"] - margin), min(s_end, w["end"] + margin))
            for w in overlapping
        )
        # protected_ranges を merge してから silence の補集合を取る
        merged: list[tuple[float, float]] = []
        for p_s, p_e in protected_ranges:
            if merged and p_s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], p_e))
            else:
                merged.append((p_s, p_e))
        cursor = s_start
        for p_s, p_e in merged:
            if p_s > cursor:
                out.append({"start": cursor, "end": p_s})
            cursor = p_e
        if cursor < s_end:
            out.append({"start": cursor, "end": s_end})
    # 0 以下の長さは除外
    return [r for r in out if r["end"] > r["start"]]
```

**理由**: silence の穴あけは「ASR が認識した発話の証拠を信頼する」という意味で原理的に妥当。 ReazonSpeech は誤認識でも timestamp は正確(subword の境界推定で ±0.05 秒程度)なので、 margin=0.1 秒で十分な safe マージン。

### D2: video.py の適用箇所
**位置**: Stage 3 末尾の `if words: silences = snap_silences_to_word_boundaries(silences, words)` の **直前**(L411)に追加。

```python
# 単語境界スナップの前に、 ASR が認識した word を silence からくり抜く
if words:
    silences = protect_words_from_silences(silences, words)
    silences = snap_silences_to_word_boundaries(silences, words)
    if extra_cuts:
        extra_cuts = snap_silences_to_word_boundaries(extra_cuts, words)
```

**理由**:
- 1 段目 transcribe (Stage 2.5) が完了して `words` が利用可能
- voice_segments を計算する前なので、 削除候補がまだ確定していない
- snap よりも前: snap は境界調整、 protect は範囲除外で、 protect → snap の順が自然

### D3: margin 値はデフォルト 0.1 秒
**理由**:
- ReazonSpeech の subword timestamp 推定精度は ±0.05 秒程度
- 0.1 秒の余白で word 前後の閉鎖音・息継ぎを軽く残せる
- 大きくしすぎると silence の効果(短縮目的)が薄れる

### D4: enable_jump_cut が False のケース
**方針**: 適用しない。 enable_jump_cut が False の場合、 1 段目 transcribe を実行せず words が空。 本機能はそのケースで自動的に no-op になる(if words: ... ガード)。

### D5: extra_cuts (施策A-E のフィラー/重複/word_gap/oversized など) には適用しない
**理由**: extra_cuts は意図的に「削除すべき発話/フィラー」を含む。 ここに ASR-aware 保護を入れると、 フィラー削除が無効化される。

## Risks / Trade-offs

### R1: ASR の誤認識(ノイズを word として検出)による silence 保護のミス
**Mitigation**:
- margin=0.1 秒に抑えて影響を局所化
- ReazonSpeech の認識は十分高精度
- 検証: ベースライン再測定で cut.mp4 が長くなりすぎていないか確認(処理時間も含めて)

### R2: 「ASR が認識した発話」が単なる呼吸音や口の音まで含む可能性
**Mitigation**:
- ReazonSpeech は word.text を返すので、 「。」や空文字、 「えー」「あー」のような filler は word として返ることがあるが、 本機能ではテキスト内容に依存せず word の **時刻範囲のみ** で保護
- フィラー削除は本機能の **後** で施策A (`detect_filler_ranges`) が word.text ベースで判断するので、 二重保護にならない

### R3: 既存テスト 107 件への影響
**Mitigation**:
- 既存テストは voice_segments の特定状況を assert している
- protect_words_from_silences は新規追加で、 既存ロジックに変更なし
- 影響を受けるのは新しいフロー(words が利用可能な場合)
- ベースライン再測定で動画長と #4 (60-120 秒)、 #14 (処理時間) の合格を確認

## Migration Plan

### 段階 1: 実装
1. `silence.py` に `protect_words_from_silences` を追加
2. `video.py` の Stage 3 末尾を更新

### 段階 2: テスト
1. 既存 107 件 PASS 確認
2. 「silence が word を 1 個含む場合の穴あけ」テスト
3. 「silence が word を 2 個含む場合の merge」テスト
4. 「margin 適用で word の前後にバッファ」テスト

### 段階 3: ベースライン再測定
1. seitai_food.mov を再処理(skip_preview=true, tight preset)
2. measure_quality.py で測定
3. 出力字幕の冒頭 Dialogue を目視確認: 「お客様が悩まれている」が出るか
4. baseline.md の該当行を更新

### Rollback
本 change は `silence.py` の追加と `video.py` の 1 行追加のみ。 git revert で完全に元に戻る。

## Open Questions

- **Q1**: protect_words_from_silences は cut2.mp4 段階 (Stage 5b で 3 段目 transcribe する前)でも適用すべきか?
  - **暫定方針**: No。 cut2.mp4 は既に施策F でカット済み。 3 段目 transcribe が冒頭発話を聞き逃すケースは、 元時刻 1 段目で発話が保護されていれば cut2 にも残るはず。 適用は元時刻 silences のみ。
- **Q2**: 1 段目 transcribe で word が認識されなかった「真の無音」と区別できるか?
  - **暫定方針**: word.text の空白チェックは行わず、 word.start/end の存在のみで判断。 word が無い区間は silence のまま保持される(=削除候補)。
- **Q3**: margin=0.1 秒は環境別に調整すべきか(例: 整体院動画は呼吸音多め)?
  - **暫定方針**: デフォルト 0.1 秒。 必要なら settings.protect_margin で外出しできるが、 初期版ではハードコード。
