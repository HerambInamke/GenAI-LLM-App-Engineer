import base64
import hashlib
import hmac
import statistics

import numpy as np

from deadair.calls.audio import down_to_phone, mulaw_decode, mulaw_encode, up_to_station
from deadair.calls.manager import CallManager
from deadair.calls.twilio import valid_signature
from deadair.eval.measure import bargein_stop, call_latency


def test_mulaw_roundtrip_and_resample():
    t = np.arange(800) / 8000
    x = (0.5 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    y = mulaw_decode(mulaw_encode(x))
    assert np.max(np.abs(x - y)) < 0.02
    assert len(up_to_station(x)) == 2400 and len(down_to_phone(up_to_station(x))) == 800


def test_queue_max_three_and_privacy(db, tmp_path):
    cm = CallManager(db, "deadair", tmp_path)
    results = [cm.new_call()[1] for _ in range(4)]
    assert results == ["queued"] * 3 + ["rejected"]  # FR-6.3
    cols = [r[1] for r in db.execute("PRAGMA table_info(calls)")]
    assert not any("phone" in c or "from" in c or "number" in c for c in cols)  # FR-6.6
    for (cid,) in db.execute("SELECT id FROM calls"):
        assert len(cid) == 32 and int(cid, 16) >= 0  # random uuid hex only


def test_blocklist_drops_caller(db, tmp_path):
    cm = CallManager(db, "deadair", tmp_path)
    c, _ = cm.new_call()
    cm.take_next()
    assert not cm.hear(c.id, "you are all shit")
    assert c.hung_up
    assert db.execute("SELECT status FROM calls WHERE id = ?", (c.id,)).fetchone()[0] == "dropped"


def test_twilio_signature():
    token, url = "tok", "https://example.com/twilio/voice/deadair"
    params = {"CallSid": "CA1", "Digits": "1"}
    payload = url + "CallSid" + "CA1" + "Digits" + "1"
    sig = base64.b64encode(hmac.new(b"tok", payload.encode(), hashlib.sha1).digest()).decode()
    assert valid_signature(url, params, sig, token)
    assert not valid_signature(url, {**params, "Digits": "2"}, sig, token)


async def test_thirty_scripted_call_turns(db, tmp_path):
    """Step 8 test: 30 caller turns through queue -> on air -> reply. Median latency < 1.5 s.

    Offline providers, so this measures the pipeline, not real LLM/TTS speed.
    """
    lat = await call_latency(db, tmp_path, turns=30)
    assert len(lat) == 30 and statistics.median(lat) < 1500
    assert all("host:" in p.read_text() for p in (tmp_path / "calls").glob("*.txt"))


async def test_barge_in_stops_playback_fast(db, tmp_path):
    """Step 8 test: playback stops within 300 ms of detected caller speech in >= 95% of trials."""
    stops = await bargein_stop(db, tmp_path, trials=20)
    assert len(stops) == 20 and sum(ms < 300 for ms in stops) >= 19, stops
