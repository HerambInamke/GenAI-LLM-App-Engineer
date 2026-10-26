import json

import pytest

from deadair.eval.planted import fixture_items, planted_claims
from deadair.gate.claims import rule_claim, verify
from deadair.gate.gate import FactGate

ALLOW = {"max", "juniper", "dead", "air"}


@pytest.fixture
def gate(db):
    return FactGate(db, ALLOW)


async def test_50_hand_claims(gate, items):
    """Step 3 test: 25 true + 25 false claims, all with the expected result."""
    claims = planted_claims(items, 25, 25)
    wrong = []
    for c in claims:
        d = await gate.check(c["text"], segment_id="s1", host="max")
        if (d.result == "pass") != c["expect_ok"]:
            wrong.append((c, d.reasons))
    assert not wrong, wrong


async def test_nfr3_thresholds(gate, items):
    """NFR-3: >=90% of 100 false claims caught, <10% of 100 true claims blocked."""
    claims = planted_claims(items, 100, 100)
    results = [
        (c, (await gate.check(c["text"], segment_id="s", host="max")).result) for c in claims
    ]
    caught = sum(r != "pass" for c, r in results if not c["expect_ok"])
    false_pos = sum(r != "pass" for c, r in results if c["expect_ok"])
    assert caught >= 90 and false_pos < 10, (caught, false_pos)


async def test_banter_needs_no_citation(gate):
    d = await gate.check(
        "I love this job. The coffee here is terrible.", segment_id="s", host="max"
    )
    assert d.result == "pass" and d.text == "I love this job. The coffee here is terrible."


async def test_bad_sentence_stripped_rest_kept(gate, items):
    it = items[0]
    text = f"{it.title} [f:{it.id}]. Paris says 99 trains were cancelled. What a day."
    d = await gate.check(text, segment_id="s", host="max")
    assert d.result == "stripped"
    assert "Paris" not in d.text and it.title in d.text and "[f:" not in d.text


async def test_regen_once_then_fallback(gate):
    calls = []

    async def regen(text, reasons):
        calls.append(reasons)
        return "Rome reports 7 new bridges."  # still unsourced

    d = await gate.check("Berlin has 4 moons.", segment_id="s", host="max", regen=regen)
    assert len(calls) == 1 and d.result == "fallback" and d.text == ""


async def test_regen_pass(gate, items):
    it = items[1]

    async def regen(text, reasons):
        return f"{it.title} [f:{it.id}]."

    d = await gate.check("Kenya plants 41 million trees.", segment_id="s", host="max", regen=regen)
    assert d.result == "regen_pass"


async def test_every_decision_logged(gate, db, items):
    await gate.check(f"{items[2].title} [f:{items[2].id}].", segment_id="seg-9", host="juniper")
    row = db.execute("SELECT * FROM chunks WHERE segment_id = 'seg-9'").fetchone()
    assert row["gate_result"] == "pass" and json.loads(row["claims_json"])[0]["ok"]


async def test_moderation_blocks(gate):
    d = await gate.check("That was some shit radio.", segment_id="s", host="max")
    assert d.result == "fallback"


async def test_storyline_citation(gate, db):
    db.execute(
        "INSERT INTO storylines VALUES ('jw','shared','Jingle War','active','[]',"
        "'KRVL claims Dead Air stole its jingle in March.', NULL)"
    )
    assert (
        await gate.check("KRVL says we stole it in March [s:jw].", segment_id="s", host="max")
    ).result == "pass"
    assert (
        await gate.check("KRVL says we stole it in June [s:jw].", segment_id="s", host="max")
    ).result != "pass"


async def test_llm_flags_lowercase_claims(db):
    from conftest import FakeLLM

    gate = FactGate(db, ALLOW, FakeLLM(parsed=[{"indexes": [0]}]))
    d = await gate.check("the central bank raised rates again.", segment_id="s", host="max")
    assert d.result == "fallback" and d.reasons == ["no citation"]


def test_rule_claim_detection():
    assert rule_claim("I love radio.", ALLOW) is None
    assert rule_claim("Max loves radio.", ALLOW) is None
    c = rule_claim("Kenya planted 40 million trees on Monday [f:abc].", ALLOW)
    assert c.numbers == ["40"] and c.entities == ["Kenya", "Monday"] and c.citations == ["f:abc"]


def test_fuzzy_entity_match():
    c = rule_claim("Grindavík was evacuated [f:x].", set())
    assert verify(c, lambda _: "Authorities evacuated Grindavik") is None


def test_fixture_items_unique():
    assert len({i.id for i in fixture_items()}) == 20


async def test_log_stores_aired_text_after_regen(gate, db, items):
    it = items[1]

    async def regen(text, reasons):
        return f"{it.title} [f:{it.id}]."

    await gate.check("Kenya plants 41 million trees.", segment_id="seg-r", host="max", regen=regen)
    row = db.execute("SELECT text FROM chunks WHERE segment_id = 'seg-r'").fetchone()
    assert row["text"] == f"{it.title} [f:{it.id}]."


async def test_real_people_only_in_news(db):
    """NFR-7: the same sentence naming a public figure passes in news, is stripped elsewhere."""
    from conftest import FakeLLM

    labels = {"indexes": [], "named_people": [0]}
    llm = FakeLLM(parsed=[labels, labels])
    gate = FactGate(db, ALLOW, llm)
    text = "Honestly the prime minister looked tired."
    assert (await gate.check(text, segment_id="s", host="max")).result == "pass"
    d = await gate.check(text, segment_id="s", host="max", people_ok=False)
    assert d.result == "fallback" and "NFR-7" in d.reasons[0]


def test_offline_lines_never_name_people():
    """Offline template lines outside news contain no names, so NFR-7 holds without Claude."""
    from deadair.hosts.writer import BANTER, CALLER_REPLIES, FEUD, LIGHT_QUIPS, SERIOUS_CLOSE

    allow = ALLOW | {"krvl", "dead", "air"}
    for line in BANTER + FEUD + CALLER_REPLIES + LIGHT_QUIPS + [SERIOUS_CLOSE]:
        claim = rule_claim(line, allow)
        assert claim is None or not claim.entities, line
