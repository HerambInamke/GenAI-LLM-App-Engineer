"""Measurement runs shared by the tests and the eval report (NFR-1, NFR-2, NFR-3, NFR-4)."""

import asyncio
import sqlite3
from pathlib import Path

import numpy as np

from deadair.audio.broadcast import Broadcaster
from deadair.audio.tts import SR, SynthTTS
from deadair.calls.bargein import BargeIn
from deadair.calls.manager import CallManager
from deadair.calls.twilio import feed_text_call
from deadair.config import load_config
from deadair.eval.planted import planted_claims
from deadair.feed.store import FeedStore
from deadair.gate.gate import FactGate
from deadair.station import Station


async def call_latency(
    db: sqlite3.Connection,
    workdir: Path,
    turns: int = 30,
    llm=None,
    tts=None,
    realtime: bool = False,
) -> list[float]:
    """Scripted caller turns through the real station path. Returns ms per turn (NFR-1)."""
    st = Station(load_config(), "deadair", db, llm, rival_id="rival", seed=9)
    caster = Broadcaster("deadair", "lo-fi synth", workdir, tts or SynthTTS(), realtime=realtime)
    st.calls, st.caster = CallManager(db, "deadair", workdir), caster
    tasks = [asyncio.create_task(caster.run())]

    async def show():
        while True:
            await st.run_block(caster.emit)

    tasks.append(asyncio.create_task(show()))
    try:
        n = 0
        while n < turns:  # two callers at a time, three turns each
            feeders = []
            for k in range(2):
                caller, _ = st.calls.new_call()
                lines = [f"Caller {n}-{k} turn {t}, what do you make of that?" for t in range(3)]
                feeders.append(
                    feed_text_call(st.calls, caller, lines, gap=0 if not realtime else 0.5)
                )
            await asyncio.wait_for(asyncio.gather(*feeders), timeout=600)
            n = len(st.calls.latencies_ms)
    finally:
        for t in tasks:
            t.cancel()
    return st.calls.latencies_ms[:turns]


async def bargein_stop(db: sqlite3.Connection, workdir: Path, trials: int = 20) -> list[float]:
    """Real-time clock; caller speech while the host talks. Returns ms to silence (NFR-2)."""
    caster = Broadcaster("deadair", "lo-fi synth", workdir, SynthTTS(), realtime=True)
    cm = CallManager(db, "deadair", workdir)
    station = type("S", (), {"interrupt": asyncio.Event()})()
    clock = asyncio.create_task(caster.run())
    caller, _ = cm.new_call()
    cm.take_next()
    barge = BargeIn(station, caster, cm)
    loud = (0.3 * np.sin(2 * np.pi * 200 * np.arange(160) / 8000)).astype(np.float32)
    try:
        for _ in range(trials):
            caster.enqueue(np.full(SR * 3, 0.1, np.float32), True)  # host talking
            await asyncio.sleep(0.12)
            for _ in range(4):  # 80 ms of caller speech
                if barge.feed(caller, loud):
                    break
            await asyncio.sleep(0.15)
    finally:
        clock.cancel()
    return caster.stop_ms


async def gate_accuracy(db: sqlite3.Connection, items, llm=None, n: int = 100) -> dict:
    """Planted-error set (NFR-3): caught false claims and blocked true claims."""
    FeedStore(db).add(items)
    gate = FactGate(db, {"max", "juniper", "dead", "air"}, llm)
    caught = blocked = 0
    for c in planted_claims(items, n, n):
        passed = (await gate.check(c["text"], segment_id="eval", host="eval")).result == "pass"
        caught += (not c["expect_ok"]) and not passed
        blocked += c["expect_ok"] and not passed
    return {"false_caught": caught, "false_total": n, "true_blocked": blocked, "true_total": n}
