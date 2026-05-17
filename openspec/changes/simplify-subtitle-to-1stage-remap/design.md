## Context

### 現在の Stage 5b (3段目 transcribe + hybrid)
```python
if cut2_generated:
    cut2_audio = ...
    extract_audio(cut_output, cut2_audio)
    words_cut3, _ = transcribe_with_words(cut2_audio, ...)  # 3 段目 transcribe
    if corrections: words_cut3 = apply_corrections_to_words(words_cut3, corrections)
    # Hybrid 補完
    if words and voice_segments and cut2_voices_used:
        words_in_cut_1st = _filter_words_by_segments(words, voice_segments)  # 2 段 remap (1)
        words_in_cut2_1st = _filter_words_by_segments(words_in_cut_1st, cut2_voices_used)  # 2 段 remap (2)
        words_cut3, prepended = _hybrid_prepend_leading_words(words_cut3, words_in_cut2_1st, ...)
    subtitle_words = words_cut3
else:
    # cut.mp4 ベース
    if words and voice_segments and words_cut:
        words_in_cut_1st = _filter_words_by_segments(words, voice_segments)
        words_cut, prepended = _hybrid_prepend_leading_words(words_cut, words_in_cut_1st, ...)
    subtitle_words = words_cut
```

### 問題箇所
- **2 段 remap**: `_filter_words_by_segments(words, voice_segments) → _filter_words_by_segments(..., cut2_voices)` で中間 (cut.mp4 内時刻) を経由 → 順序崩壊リスク
- **3 段目 ASR**: cut2.mp4 (短い context) で subword 断片化
- **hybrid 補完の発動条件**: `first_3rd_start > threshold` だけでは「3 段目が断片的に冒頭認識した」 ケースを救えない

## Goals / Non-Goals

**Goals:**
- 字幕用 words 生成を 1 段目 ASR + 1 段 remap に統一
- 中間状態を経由しない → 順序崩壊リスクをアーキテクチャ的に排除
- 3 段目 transcribe を廃止し処理時間短縮 + コード簡素化
- 1 段目 ASR の高品質テキストを字幕に活かす

**Non-Goals:**
- 1 段目 ASR 自体の認識精度向上 (誤認識は LLM 校正で吸収)
- 動画カット判定 (施策F/G) のロジック変更 (引き続き 2 段目 ASR + 1 段 remap を使用)
- max_chars / segmentation 関連の追加調整

## Decisions

### D1: 合成マッピング (build_orig_to_cut2_mapping)
voice_segments と cut2_voices を **1 つのテーブル** に合成:

```python
def build_orig_to_cut2_mapping(voice_segments, cut2_voices=None):
    """元時刻 → cut2 内時刻 の 1 段マッピングを構築.

    voice_segments: 元動画から残す範囲 (元時刻)
    cut2_voices: cut.mp4 からさらに残す範囲 (cut.mp4 内時刻)。 None なら施策F 未発動

    Returns:
        [{"orig_start": float, "orig_end": float, "cut2_start": float}, ...]
        word.start が [orig_start, orig_end) 内なら、 cut2_start + (w.start - orig_start) で cut2 時刻が得られる
    """
    mappings = []
    cut_offset = 0.0
    for vs in voice_segments:
        vs_dur = vs["end"] - vs["start"]
        vs_cut_start = cut_offset
        vs_cut_end = cut_offset + vs_dur
        cut_offset = vs_cut_end
        if cut2_voices is None:
            mappings.append({
                "orig_start": vs["start"], "orig_end": vs["end"],
                "cut2_start": vs_cut_start,
            })
            continue
        cut2_cum = 0.0
        for cv in cut2_voices:
            inter_start = max(vs_cut_start, cv["start"])
            inter_end = min(vs_cut_end, cv["end"])
            if inter_end > inter_start:
                orig_off_in_vs = inter_start - vs_cut_start
                mappings.append({
                    "orig_start": vs["start"] + orig_off_in_vs,
                    "orig_end": vs["start"] + (inter_end - vs_cut_start),
                    "cut2_start": cut2_cum + (inter_start - cv["start"]),
                })
            cut2_cum += cv["end"] - cv["start"]
    return mappings
```

**理由**: 中間状態 (cut.mp4 内時刻) を **計算には使うが、 word を経由させない**。 mapping テーブルは元時刻と cut2 時刻の直接ペアを保持するので、 1 回の remap で済む。

### D2: remap_words_with_mapping
```python
def remap_words_with_mapping(words, mappings):
    out = []
    for w in words:
        for m in mappings:
            if m["orig_start"] <= w["start"] < m["orig_end"]:
                new_start = m["cut2_start"] + (w["start"] - m["orig_start"])
                w_end_clamped = min(w["end"], m["orig_end"])
                new_end = m["cut2_start"] + (w_end_clamped - m["orig_start"])
                if new_end > new_start + 0.001:
                    new_w = {"start": new_start, "end": new_end, "text": w["text"]}
                    if "is_word_start" in w:
                        new_w["is_word_start"] = w["is_word_start"]
                    out.append(new_w)
                break  # word.start は 1 つの mapping にしか入らない
    return out
```

**特徴**:
- word.start が含まれる mapping を線形探索 (mapping 数は通常 10-50 程度なので O(n) でも問題なし)
- word.end が mapping 範囲を越える場合は clamp (subword の半分が削除区間にかかる時の処理)
- is_word_start を保持(words_to_segments の単語境界判定用)

### D3: Stage 5b の簡素化
```python
# 旧: 80 行
# 新: 約 15 行
job.update({"stage": "transcribe", "progress": 80, "message": "字幕を生成中..."})
if cut2_generated:
    mappings = build_orig_to_cut2_mapping(voice_segments, cut2_voices_used)
else:
    mappings = build_orig_to_cut2_mapping(voice_segments, None)
subtitle_words = remap_words_with_mapping(words, mappings)
if corrections and subtitle_words:
    subtitle_words = apply_corrections_to_words(subtitle_words, corrections)
logger.info("字幕用 words: 1段目 + 1段 remap で %d words 生成", len(subtitle_words))
```

### D4: 削除する要素
- `_hybrid_prepend_leading_words` (video.py)
- `_dedup_leading_against_third` (video.py)
- Stage 5b 内の cut2_audio 抽出 / 3段目 transcribe / hybrid 補完
- 関連テスト (`tests/test_video_router_stage5b.py` の hybrid/dedup 系)

### D5: words_cut (2 段目 cut.mp4 transcribe) はどうするか?
- 施策F/G の判定用に必須 (`detect_oversized_words(words_cut)`, 施策G の `combined_first/last`)
- これは維持
- ただし字幕生成からは完全に切り離す

### D6: 1 段目 ASR が認識ミスした場合の救済
- 誤認識: LLM 校正 (`correct_transcript_segments`) で文脈的に修正
- 動画固有用語: `summarize_with_mishearings` で抽出された辞書で `apply_corrections_to_text`
- 静的辞書: `jp_corrections.txt` で繰り返し誤認識を吸収
- 本 change ではこの辞書改善は Non-Goal

## Risks / Trade-offs

### R1: 1 段目 ASR の timestamp 精度が低い (subword 単一点 timestamp)
**実態**: ReazonSpeech NeMo は subword の time stamp を「単一点」 として返す。 隣接 subword の差で duration を推定 (asr.py の `_reazonspeech_result_to_words_segments`)。 精度は ±0.1-0.3 秒程度
**Mitigation**: 字幕タイミング同期 (#6) の許容差 0.5 秒以内には収まる

### R2: 1 段目 ASR の誤認識が直接字幕に出やすくなる
**Mitigation**:
- LLM 校正 + 動画固有辞書 + 静的辞書の 3 段防御で吸収
- 誤認識頻度は低い (job 0ca6b31b の例で「威勢」 程度)
- 業務量産ではプレビュー編集での手動修正も可能

### R3: 旧 2 段 remap の崩壊が再発しないか
**Mitigation**:
- 1 段マッピングは **中間状態を経由しない** ので、 順序崩壊の余地がない
- mapping は voice_segments と cut2_voices の **直接合成** (合成過程で時刻順は保たれる)
- 各 word は単一 mapping にのみマッチ (break で 1 回)、 重複生成なし
- 既存テストの subword 連続性検証を維持

### R4: 既存テスト 127 件への影響
**Mitigation**:
- `_hybrid_prepend_leading_words` 系のテスト約 6 件は削除 (ロジック削除のため)
- `_filter_words_by_segments` のテストは維持 (施策G 判定用に残存)
- 新規テスト: 合成マッピング系 4-5 件追加
- 結果: 約 125 件で同等カバレッジ

## Migration Plan

1. silence.py に `build_orig_to_cut2_mapping` + `remap_words_with_mapping` を追加 + テスト
2. video.py の Stage 5b を 1 段 remap に書き換え
3. video.py から `_hybrid_prepend_leading_words` / `_dedup_leading_against_third` を削除
4. テスト整理 + 既存 PASS 確認
5. seitai_food.mov 再処理で 0ca6b31b 相当ジョブが「お客様が悩まれている…」 を出すこと確認

### Rollback
silence.py の追加分は単独。 video.py 限定の変更。 git revert で完全に戻る。

## Open Questions

- **Q1**: 字幕 spec の Requirement「Stage 5b として cut2.mp4 を 3 段目 transcribe する」(archive 済) はどう扱うか?
  - **暫定方針**: 本 change で MODIFIED Requirement に書き換え、 「字幕用 words は 1 段目 ASR を 1 段 remap で cut2 時刻に変換する」 を新仕様とする
- **Q2**: cut2.mp4 の音声品質を再評価するか?
  - **暫定方針**: No。 字幕は 1 段目ベース、 動画は cut2.mp4 のまま
