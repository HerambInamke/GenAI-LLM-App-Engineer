import json

from deadair.config import CONFIG_DIR, load_config
from deadair.showrunner.models import BlockPlan, Segment
from deadair.showrunner.planner import Planner
from deadair.showrunner.rules import enforce, violations
from deadair.showrunner.storylines import StorylineRegistry
from deadair.showrunner.votes import VoteManager
from deadair.station import Station


def test_rules_repair_bad_plan(items):
    by_id = {i.id: i for i in items}
    serious = next(i for i in items if i.tone == "serious")
    bad = BlockPlan(
        segments=[
            Segment(type="banter", host="max", item_ids=[serious.id], storyline_id="jw"),
            Segment(type="feud", host="juniper", storyline_id="jw"),
            Segment(type="feud", host="ghost"),
            Segment(type="news", host="max", item_ids=["nope"]),
        ]
    )
    assert violations(bad, by_id)
    fixed, fixes = enforce(bad, by_id, ["max", "juniper"], {"jw"})
    assert violations(fixed, by_id) == []
    assert [s.type for s in fixed.segments] == ["banter", "feud", "banter", "station_id"]
    assert fixed.segments[2].host in {"max", "juniper"} and len(fixes) >= 4


async def test_llm_plan_is_enforced(items):
    from conftest import FakeLLM

    serious = next(i for i in items if i.tone == "serious")
    llm = FakeLLM(
        parsed=[{"segments": [{"type": "banter", "host": "max", "item_ids": [serious.id]}]}]
    )
    plan, fixes = await Planner("deadair", "Dead Air", ["max", "juniper"], llm=llm).plan(items, [])
    assert plan.segments[0].item_ids == [] and fixes


async def test_planner_falls_back_without_llm(items):
    plan, _ = await Planner("deadair", "Dead Air", ["max", "juniper"], rival="KRVL").plan(items, [])
    assert 10 <= len(plan.segments) <= 14 and sum(s.type == "feud" for s in plan.segments) == 1


def test_storyline_one_beat_per_block(db):
    reg = StorylineRegistry(db)
    reg.seed(CONFIG_DIR / "storylines.yaml")
    assert reg.advance("jingle-war", "Max hums the jingle", 1)
    assert not reg.advance("jingle-war", "Max hums it again", 1)
    assert reg.advance("jingle-war", "Juniper objects", 2)
    assert reg.get("jingle-war").summary.endswith("Max hums the jingle | Juniper objects")


def test_50_simulated_votes(db):
    """Step 7 test: 50 votes, one per voter, expected winner."""
    vm = VoteManager(db)
    v = vm.open("deadair", "Apologize or double down?", ["Apologize", "Double down"])
    for i in range(50):
        assert vm.cast(v.id, f"voter-{i}", "Double down" if i % 5 else 1)  # 1 = keypad digit
    assert not vm.cast(v.id, "voter-0", "Apologize")  # one vote per voter
    assert not vm.cast(v.id, "voter-x", 9)  # invalid digit
    assert vm.tally(v.id) == {"Apologize": 10, "Double down": 40}
    assert vm.close(v.id) == "Double down" and not vm.cast(v.id, "late", 1)


async def test_three_block_station_run(db):
    """Step 6 test: 3 simulated blocks respect rules, advance storylines once per block,
    apply the vote at a boundary and never air an unsourced claim."""
    cfg = load_config()
    cfg.vote_blocks = 2  # close the vote inside this 3-block run
    st = Station(cfg, "deadair", db, rival_id="rival", seed=3)
    lines = []

    async def emit(ev):
        if ev.kind == "line":
            lines.append(ev)

    items = {i.id: i for i in st.feed.active(48)}
    for n in range(3):
        if n == 1:  # listeners vote during block 2
            vote = st.votes.active("deadair")
            for i in range(5):
                st.votes.cast(vote.id, f"web-{i}", vote.options[-1])
        await st.run_block(emit)
        assert violations(st.current_plan, items) == []
    assert lines
    plans = [
        BlockPlan.model_validate_json(r[0]) for r in db.execute("SELECT plan_json FROM blocks")
    ]
    assert any(s.type == "vote_announce" for s in plans[2].segments)  # applied at the boundary
    announce = [ev.text for ev in lines if ev.segment == "vote_announce"]
    assert announce and vote.options[-1] in announce[0]
    rows = db.execute("SELECT claims_json, gate_result FROM chunks").fetchall()
    aired_claims = [c for r in rows if r[1] != "fallback" for c in json.loads(r[0]) if c["ok"]]
    assert all(c["citations"] for c in aired_claims if c.get("numbers") or c.get("entities"))
    assert db.execute("SELECT COUNT(*) FROM blocks WHERE station='deadair'").fetchone()[0] == 3


async def test_twenty_minute_text_run(tmp_path, monkeypatch, capsys):
    """Step 4 test: 20 minutes of two-host text with no catchphrase or joke repeated."""
    from deadair.__main__ import text_show
    from deadair.eval.planted import fixture_items
    from deadair.feed.store import FeedStore

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    path = tmp_path / "t.db"
    FeedStore(path).add(fixture_items())
    assert await text_show(20, str(path), poll=False) == []
    out = capsys.readouterr().out
    assert "Max Static" in out and "Juniper Vale" in out


async def test_dual_station_run_has_no_unsourced_claims(db):
    """Step 9 test: both stations on the same feed for ~30 min of airtime; one jab per block
    each; the rival only quotes stored transcripts; no unsourced claim reaches the air."""
    cfg = load_config()
    stations = [
        Station(cfg, "deadair", db, rival_id="rival", seed=1),
        Station(cfg, "rival", db, rival_id="deadair", seed=2),
    ]
    aired = []

    async def emit(ev):
        if ev.kind == "line":
            aired.append(ev)

    items = {i.id: i for i in stations[0].feed.active(48)}
    for _ in range(4):
        for st in stations:
            await st.run_block(emit)
            assert violations(st.current_plan, items) == []
    assert {e.station for e in aired} == {"deadair", "rival"}
    for (claims_json,) in db.execute("SELECT claims_json FROM chunks"):
        for c in json.loads(claims_json):
            if c["ok"] and (c.get("numbers") or c.get("entities")):
                assert c["citations"], c
