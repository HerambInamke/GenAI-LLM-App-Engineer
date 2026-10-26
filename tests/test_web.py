import base64

import pytest
from fastapi.testclient import TestClient

from deadair.eval.planted import fixture_items
from deadair.feed.store import FeedStore
from deadair.web.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    app = create_app(str(tmp_path / "t.db"), tmp_path / "rec", start=False)
    FeedStore(app.state.rt.db).add(fixture_items())
    with TestClient(app) as c:
        yield c


def auth(pw="s3cret"):
    return {"Authorization": "Basic " + base64.b64encode(f"admin:{pw}".encode()).decode()}


def test_player_and_now(client):
    assert "Dead Air" in client.get("/").text
    assert client.get("/api/now/deadair").json()["station"] == "deadair"
    assert client.get("/api/now/nope").status_code == 404


def test_web_vote_once_per_session(client):
    rt = client.app.state.rt
    rt.stations["deadair"]._open_vote()
    vote = rt.stations["deadair"].votes.active("deadair")
    r = client.post("/api/vote/deadair", json={"option": vote.options[0]})
    assert r.status_code == 200 and r.json()["tally"][vote.options[0]] == 1
    assert client.post("/api/vote/deadair", json={"option": vote.options[1]}).status_code == 409


def test_admin_requires_password(client):
    assert client.get("/api/admin/deadair").status_code == 401
    assert client.get("/api/admin/deadair", headers=auth("wrong")).status_code == 401
    d = client.get("/api/admin/deadair", headers=auth()).json()
    assert {"plan", "storylines", "gate_log", "calls"} <= d.keys()


def test_admin_force_close_applies_at_next_boundary(client):
    import asyncio

    st = client.app.state.rt.stations["deadair"]
    st._open_vote()
    vote = st.votes.active("deadair")
    st.votes.cast(vote.id, "web-1", vote.options[1])
    r = client.post("/api/admin/deadair/vote/close", headers=auth())
    assert r.json()["winner"] == vote.options[1]
    _, plan = asyncio.run(st.plan_block())
    assert plan.segments[0].type == "vote_announce"
    assert vote.options[1] in plan.segments[0].note


def test_archive_lists_and_blocks_traversal(client):
    rec = client.app.state.rt.recordings / "deadair"
    rec.mkdir(parents=True, exist_ok=True)
    (rec / "20260101-000000_b1.mp3").write_bytes(b"\xff\xf3" * 10)
    (rec / "20260101-000000_b1.txt").write_text("max: hi")
    rows = client.get("/api/archive").json()
    assert rows[0]["file"] == "20260101-000000_b1.mp3"
    assert client.get("/archive/deadair/20260101-000000_b1.mp3").status_code == 200
    assert client.get("/archive/deadair/..%2F..%2Fpyproject.toml").status_code in (400, 404)


def test_rating_one_per_browser(client):
    assert client.post("/api/rating", json={"score": 6}).status_code == 422
    assert client.post("/api/rating", json={"score": 4, "comment": "fun"}).status_code == 200
    assert client.post("/api/rating", json={"score": 5}).status_code == 200
    rows = client.app.state.rt.db.execute("SELECT score FROM ratings").fetchall()
    assert [r[0] for r in rows] == [5]
