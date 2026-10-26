import asyncio
import base64
import hashlib
import hmac
import statistics

import numpy as np

from deadair.audio.broadcast import Broadcaster
from deadair.audio.tts import SR, SynthTTS
from deadair.calls.audio import down_to_phone, mulaw_decode, mulaw_encode, up_to_station
from deadair.calls.bargein import BargeIn
from deadair.calls.manager import CallManager
from deadair.calls.twilio import feed_text_call, valid_signature
from deadair.config import load_config
from deadair.station import Station


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
    cfg = load_config()
    st = Station(cfg, "deadair", db, rival_id="rival", seed=9)
    caster = Broadcaster("deadair", "lo-fi synth", tmp_path, SynthTTS(), realtime=False)
    st.calls, st.caster = CallManager(db, "deadair", tmp_path), caster
    clock = asyncio.create_task(caster.run())

    async def loop():
        while True:
            await st.run_block(caster.emit)

    show = asyncio.create_task(loop())
    for batch in range(5):  # 5 batches x 2 callers x 3 turns = 30 turns
        feeders = []
        for k in range(2):
            caller, status = st.calls.new_call()
            assert status == "queued"
            lines = [f"Caller {batch}-{k} line {n}, what do you think?" for n in range(3)]
            feeders.append(asyncio.create_task(feed_text_call(st.calls, caller, lines, gap=0)))
        await asyncio.wait_for(asyncio.gather(*feeders), timeout=60)
    show.cancel()
    clock.cancel()
    lat = st.calls.latencies_ms
    assert len(lat) == 30, len(lat)
    assert statistics.median(lat) < 1500
    transcript = (tmp_path / "calls").glob("*.txt")
    assert all("host:" in p.read_text() for p in transcript)


async def test_barge_in_stops_playback_fast(db, tmp_path):
    """Step 8 test: playback stops within 300 ms of detected caller speech in >= 95% of trials."""
    caster = Broadcaster("deadair", "lo-fi synth", tmp_path, SynthTTS(), realtime=True)
    cm = CallManager(db, "deadair", tmp_path)
    station = type("S", (), {"interrupt": asyncio.Event()})()
    clock = asyncio.create_task(caster.run())
    caller, _ = cm.new_call()
    cm.take_next()
    barge = BargeIn(station, caster, cm)
    loud = (0.3 * np.sin(2 * np.pi * 200 * np.arange(160) / 8000)).astype(np.float32)
    for _ in range(20):
        caster.enqueue(np.full(SR * 3, 0.1, np.float32), True)  # host talking
        await asyncio.sleep(0.12)
        assert any(barge.feed(caller, loud) for _ in range(4))  # 80 ms of caller speech
        await asyncio.sleep(0.15)
    clock.cancel()
    assert len(caster.stop_ms) == 20
    within = sum(ms < 300 for ms in caster.stop_ms)
    assert within >= 19, caster.stop_ms
    assert station.interrupt.is_set()
