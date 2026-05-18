# backend/tests/test_llm.py
from unittest.mock import patch

from app.services import llm


def _words():
    return [
        {"start": 0.0, "end": 1.0, "text": "今日は"},
        {"start": 1.0, "end": 2.0, "text": "いや"},
        {"start": 2.0, "end": 3.0, "text": "明日は"},
        {"start": 3.0, "end": 4.0, "text": "雨です"},
    ]


def test_detect_restatements_unset_provider(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert llm.detect_restatements(_words()) == []


def test_detect_restatements_missing_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert llm.detect_restatements(_words()) == []


def test_detect_restatements_empty_words(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    assert llm.detect_restatements([]) == []


def test_detect_restatements_openai_success(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    fake = '{"ranges": [{"start": 1.0, "end": 2.0, "reason": "言い直し"}]}'
    with patch.object(llm, "_call_openai", return_value=fake):
        result = llm.detect_restatements(_words())
    assert result == [{"start": 1.0, "end": 2.0}]


def test_detect_restatements_anthropic_success(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    fake = '{"ranges": [{"start": 0.5, "end": 1.5}]}'
    with patch.object(llm, "_call_anthropic", return_value=fake):
        result = llm.detect_restatements(_words())
    assert result == [{"start": 0.5, "end": 1.5}]


def test_detect_restatements_out_of_range_discarded(monkeypatch):
    """transcript の時間範囲外の range は破棄される"""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    fake = '{"ranges": [{"start": 1.0, "end": 2.0}, {"start": 100.0, "end": 200.0}]}'
    with patch.object(llm, "_call_openai", return_value=fake):
        result = llm.detect_restatements(_words())
    assert result == [{"start": 1.0, "end": 2.0}]


def test_detect_restatements_empty_ranges(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    with patch.object(llm, "_call_openai", return_value='{"ranges": []}'):
        result = llm.detect_restatements(_words())
    assert result == []


def test_detect_restatements_api_error_returns_empty(monkeypatch):
    """LLM 呼び出しが例外でも空リストを返す（degraded mode）"""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    with patch.object(llm, "_call_openai", side_effect=RuntimeError("boom")):
        assert llm.detect_restatements(_words()) == []


def test_detect_restatements_invalid_json(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    with patch.object(llm, "_call_openai", return_value="not json"):
        assert llm.detect_restatements(_words()) == []


def test_detect_restatements_negative_range_discarded(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    fake = '{"ranges": [{"start": 2.0, "end": 1.0}]}'
    with patch.object(llm, "_call_openai", return_value=fake):
        assert llm.detect_restatements(_words()) == []


def test_extract_json_handles_code_fence():
    raw = '```json\n{"ranges": []}\n```'
    assert llm._extract_json(raw) == {"ranges": []}


# === detect_topics retry (retry-empty-topic-detection) ===

def test_detect_topics_retries_when_empty(monkeypatch):
    """1 回目が 0 件返したら強制分割プロンプトで 1 回リトライする。"""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")

    call_count = {"n": 0}
    prompts_seen: list[str] = []

    def fake_call(text, system_prompt=None):
        call_count["n"] += 1
        prompts_seen.append(system_prompt or "")
        if call_count["n"] == 1:
            return '{"topics": []}'
        return '{"topics": [{"index": 1, "start_seg": 0, "label": "導入"}, {"index": 2, "start_seg": 2, "label": "結論"}]}'

    monkeypatch.setattr(llm, "_call_anthropic", fake_call)

    segments = ["最初の話", "途中", "結論部分"]
    result = llm.detect_topics(segments)
    assert call_count["n"] == 2  # 1 回目 + リトライ
    assert len(result) == 2
    assert result[0]["label"] == "導入"
    assert result[1]["label"] == "結論"
    # リトライプロンプトに「必ず最低 2 個」 を含む
    assert "必ず最低 2 個" in prompts_seen[1] or "必ず 2" in prompts_seen[1]


def test_detect_topics_no_retry_when_already_has_results(monkeypatch):
    """1 回目で 1 件以上返ったらリトライしない。"""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")

    call_count = {"n": 0}

    def fake_call(text, system_prompt=None):
        call_count["n"] += 1
        return '{"topics": [{"index": 1, "start_seg": 0, "label": "メイン"}]}'

    monkeypatch.setattr(llm, "_call_anthropic", fake_call)

    result = llm.detect_topics(["セグ1", "セグ2"])
    assert call_count["n"] == 1  # リトライなし
    assert len(result) == 1


# === チャンク分割（chunked-restatement-detection） ===

def _long_words(total_sec: float, word_sec: float = 1.0) -> list[dict]:
    n = int(total_sec / word_sec)
    return [
        {"start": i * word_sec, "end": (i + 1) * word_sec, "text": f"w{i}"}
        for i in range(n)
    ]


def test_split_words_into_chunks_short_returns_single():
    """総尺 60 秒未満は単一チャンク（後方互換）。"""
    words = _long_words(50.0)
    chunks = llm._split_words_into_chunks(words)
    assert len(chunks) == 1
    assert chunks[0] == words


def test_split_words_into_chunks_long_multiple():
    """総尺 60 秒以上はチャンク分割される。"""
    words = _long_words(250.0)
    chunks = llm._split_words_into_chunks(words)
    # 90s chunk, 15s overlap, step=75s → cursors: 0, 75, 150, 225 で 4 チャンク
    assert len(chunks) == 4


def test_split_words_into_chunks_overlap_words_in_both():
    """オーバーラップ範囲の word は隣接 2 チャンク両方に含まれる。"""
    words = _long_words(250.0)
    chunks = llm._split_words_into_chunks(words)
    # 隣接チャンク間のオーバーラップ範囲（cursor 0 chunk は [0,90), cursor 75 chunk は [75,165)）
    chunk0_starts = {w["start"] for w in chunks[0]}
    chunk1_starts = {w["start"] for w in chunks[1]}
    overlap = chunk0_starts & chunk1_starts
    # 15 秒オーバーラップ、 1 秒/word → 15 word が両方に含まれる
    assert len(overlap) == 15


def test_split_words_into_chunks_no_mid_word_cut():
    """チャンク境界は word の start にスナップ（word の途中で切らない）。"""
    # word 境界が不揃いな word 列で確認
    words = []
    t = 0.0
    while t < 100.0:
        # 各 word は 0.7-1.3 秒のランダムめな長さ
        dur = 0.7 if int(t * 10) % 2 == 0 else 1.3
        words.append({"start": t, "end": t + dur, "text": f"w_{t:.1f}"})
        t += dur

    chunks = llm._split_words_into_chunks(words)
    # 各 word は 1 つ以上のチャンクに含まれる
    # （重要なのは word 自体が分割されないこと）
    all_word_ids = {id(w) for w in words}
    seen_ids: set = set()
    for c in chunks:
        for w in c:
            seen_ids.add(id(w))
    assert seen_ids == all_word_ids


def test_detect_restatements_short_calls_llm_once(monkeypatch):
    """60 秒未満は LLM を 1 回だけ呼ぶ（後方互換）。"""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    call_count = {"n": 0}

    def fake_call(text):
        call_count["n"] += 1
        return '{"ranges": []}'

    monkeypatch.setattr(llm, "_call_openai", fake_call)
    llm.detect_restatements(_long_words(50.0))
    assert call_count["n"] == 1


def test_detect_restatements_long_calls_llm_per_chunk(monkeypatch):
    """60 秒以上はチャンク数だけ LLM が呼ばれる。"""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    call_count = {"n": 0}

    def fake_call(text):
        call_count["n"] += 1
        return '{"ranges": []}'

    monkeypatch.setattr(llm, "_call_openai", fake_call)
    llm.detect_restatements(_long_words(250.0))
    assert call_count["n"] == 4  # 250s 入力で 4 チャンク


def test_detect_restatements_partial_chunk_failure(monkeypatch):
    """1 チャンクが例外でも、他チャンクの結果は返る。"""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    call_count = {"n": 0}

    # チャンク境界: cursor=0,75,150,225 / 各 chunk_min はその cursor
    # 各チャンク内で確実に範囲内となる時刻を返す
    in_range_per_chunk = [
        (10.0, 12.0),    # chunk0 [0, 90)
        (80.0, 82.0),    # chunk1 例外（使われない）
        (160.0, 162.0),  # chunk2 [150, 240)
        (230.0, 232.0),  # chunk3 [225, 250)
    ]

    def fake_call(text):
        idx = call_count["n"]
        call_count["n"] += 1
        if idx == 1:
            raise RuntimeError("chunk 2 fails")
        s, e = in_range_per_chunk[idx]
        return f'{{"ranges": [{{"start": {s}, "end": {e}}}]}}'

    monkeypatch.setattr(llm, "_call_openai", fake_call)
    result = llm.detect_restatements(_long_words(250.0))
    # 4 チャンク中 1 つ失敗 → 3 区間
    assert len(result) == 3


def test_detect_restatements_all_chunks_fail_returns_empty(monkeypatch):
    """全チャンクが例外なら空リストを返す（既存挙動と一致）。"""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setattr(llm, "_call_openai", lambda text: (_ for _ in ()).throw(RuntimeError("boom")))
    assert llm.detect_restatements(_long_words(250.0)) == []


def test_detect_restatements_overlap_merged_by_caller(monkeypatch):
    """オーバーラップ範囲で重複検出されても呼出側の merge_ranges で 1 区間に統合される。"""
    from app.services.jump_cut import merge_ranges

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    def fake_call(text):
        # 各チャンクは「自分の範囲内にある言い直し 80-85 秒」を検出するが、
        # chunk0 は [0,90)、chunk1 は [75,165) なので 80-85 は両方に入る
        # ただし chunk1 の chunk_min は 75 なので 80-85 は有効
        return '{"ranges": [{"start": 80, "end": 85}]}'

    monkeypatch.setattr(llm, "_call_openai", fake_call)
    result = llm.detect_restatements(_long_words(250.0))
    # 4 チャンク呼ばれるが、80-85 が含まれるのは chunk0 と chunk1（オーバーラップ範囲）の 2 つ
    # chunk2, chunk3 は 80-85 が範囲外で drop される
    assert len(result) == 2
    merged = merge_ranges(result)
    assert merged == [{"start": 80.0, "end": 85.0}]
