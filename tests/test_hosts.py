from deadair.config import load_config
from deadair.hosts.memory import EpisodeMemory, repetition_violations
from deadair.hosts.writer import HostWriter, chunk_stream
from deadair.showrunner.models import Segment


async def _collect(agen):
    return [x async for x in agen]


async def _pieces(text, n=5):
    for i in range(0, len(text), n):
        yield text[i : i + n]


async def test_chunk_stream_one_then_two_sentences():
    text = "First one. Second one! Third one? Fourth. Fifth"
    assert await _collect(chunk_stream(_pieces(text))) == [
        "First one.",
        "Second one! Third one?",
        "Fourth. Fifth",
    ]


def test_catchphrase_blocked_for_24h(db):
    mem = EpisodeMemory(db)
    phrases = ["Stay tuned, stay confused."]
    assert mem.repeat_reason("max", "Stay tuned, stay confused!", phrases) is None
    mem.remember("deadair", "max", "Well folks, stay tuned, stay confused.", phrases)
    assert "catchphrase" in mem.repeat_reason("max", "Stay tuned, stay confused!", phrases)
    assert mem.available_catchphrases("max", phrases) == []
    assert mem.repeat_reason("juniper", "Stay tuned, stay confused!", phrases) is None


def test_repeated_joke_detected(db):
    mem = EpisodeMemory(db)
    mem.remember("deadair", "max", "My plant has more listeners than my podcast ever did.", [])
    assert mem.repeat_reason("max", "Honestly my plant has more listeners than my podcast.", [])
    assert mem.repeat_reason("max", "The weather is lovely.", []) is None
    assert mem.similar("max", "plant listeners podcast")


def test_repetition_checker():
    log = [
        ("max", "Stay tuned, stay confused."),
        ("max", "Something new."),
        ("max", "Stay tuned, stay confused."),
    ]
    v = repetition_violations(log, {"max": ["Stay tuned, stay confused."]})
    assert any("catchphrase" in x for x in v)
    assert repetition_violations(log[:2], {"max": ["Stay tuned, stay confused."]}) == []


async def test_offline_news_cites_every_item(db, items):
    """Step 2 test: every factual sentence the host writes cites a feed id."""
    from deadair.gate.claims import rule_claim

    cfg = load_config()
    w = HostWriter("max", cfg.personas["max"], "Dead Air", EpisodeMemory(db), seed=1)
    lines = await _collect(
        w.chunks(Segment(type="news", host="max", item_ids=[i.id for i in items[:5]]), items[:5])
    )
    claims = [rule_claim(s, {"max"}) for s in lines]
    assert sum(c is not None for c in claims) == 5
    assert all(c.citations for c in claims if c)


async def test_llm_writer_prompt_has_items_and_rules(db, items):
    from conftest import FakeLLM

    cfg = load_config()
    llm = FakeLLM(streams=[f"Wow. {items[0].title} [f:{items[0].id}]. Crazy times."])
    w = HostWriter("max", cfg.personas["max"], "Dead Air", EpisodeMemory(db), llm)
    out = await _collect(
        w.chunks(Segment(type="news", host="max", item_ids=[items[0].id]), [items[0]])
    )
    assert out[0] == "Wow." and items[0].id in out[1]
    assert f"[f:{items[0].id}]" in llm.prompts[0]
    assert "citation" in w.system()


def test_repeat_check_scales_and_expires(db):
    import time
    from datetime import UTC, datetime, timedelta

    mem = EpisodeMemory(db)
    rows = [
        (
            f"id{i}",
            "deadair",
            "max",
            f"line number {i} about topic {i * 7} today",
            datetime.now(UTC).isoformat(),
            "line",
        )
        for i in range(10_000)
    ]
    db.executemany("INSERT INTO memory_items VALUES (?, ?, ?, ?, ?, ?)", rows)
    old = (datetime.now(UTC) - timedelta(hours=30)).isoformat()
    db.execute(
        "INSERT INTO memory_items VALUES ('old','deadair','max',"
        "'an ancient joke nobody remembers anymore',?,'line')",
        (old,),
    )
    start = time.perf_counter()
    for i in range(200):
        assert mem.repeat_reason("max", f"line number {i} about topic {i * 7} today", [])
        assert mem.repeat_reason("max", f"a brand new sentence {i} for the show", []) is None
    assert time.perf_counter() - start < 2.0  # one-time load, then set lookups
    assert mem.repeat_reason("max", "an ancient joke nobody remembers anymore", []) is None
    mem.remember("deadair", "max", "a fresh joke about the studio fridge tonight", [])
    assert mem.repeat_reason("max", "a fresh joke about the studio fridge tonight", [])


def test_prune_keeps_seven_days(db):
    from datetime import UTC, datetime, timedelta

    mem = EpisodeMemory(db)
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    db.execute("INSERT INTO memory_items VALUES ('x','deadair','max','old line',?,'line')", (old,))
    mem.add("deadair", "max", "new line")
    mem.prune()
    assert [r[0] for r in db.execute("SELECT text FROM memory_items")] == ["new line"]


def test_expired_grams_leave_the_index(db):
    from datetime import timedelta

    mem = EpisodeMemory(db)
    mem.remember("deadair", "max", "a joke that will age out of the window", [])
    index = mem._index("max")
    lines = mem._lines["max"]
    at, g = lines[0]
    lines[0] = (at - timedelta(hours=25), g)  # pretend it aired yesterday
    assert len(mem._index("max")) == 0 and not index
    assert mem.repeat_reason("max", "a joke that will age out of the window", []) is None
