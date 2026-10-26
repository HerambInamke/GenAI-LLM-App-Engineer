"""Render a whole episode to MP3 + transcript, faster than real time (Step 13).

Both stations run so the feud has transcripts to quote. A scripted caller and a vote are
injected so the episode shows the full format. Uses whatever providers are configured.
"""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from deadair.audio.broadcast import FRAME_S, Broadcaster
from deadair.audio.tts import get_tts
from deadair.calls.manager import CallManager
from deadair.calls.twilio import feed_text_call
from deadair.config import load_config
from deadair.db import connect
from deadair.eval.planted import fixture_items
from deadair.feed.pollers import poll_all
from deadair.feed.store import FeedStore
from deadair.providers.llm import get_llm
from deadair.station import Station

log = logging.getLogger(__name__)
CALLER_LINES = [
    "Hi, long time listener. I think KRVL is right about the jingle.",
    "Okay but will you at least admit theirs is catchier?",
]


async def ensure_feed(db, cfg, llm) -> None:
    store = FeedStore(db)
    if store.active(cfg.feeds.max_age_hours):
        return
    try:
        store.add(await poll_all(cfg.feeds.sources, llm, cfg.llm.fast_model))
    except Exception as e:  # noqa: BLE001 - fall back to the bundled fixture headlines
        log.warning("feed poll failed, using fixture headlines: %s", e)
    if not store.active(cfg.feeds.max_age_hours):
        store.add(fixture_items())


async def record_episode(
    minutes: float,
    recordings: Path,
    db_path: str,
    call_at: float = 3.0,
    vote_at: float = 6.0,
    with_call: bool = True,
) -> dict:
    cfg = load_config()
    db = connect(db_path)
    llm, tts = get_llm(), get_tts()
    await ensure_feed(db, cfg, llm)
    ids = [s.id for s in cfg.stations]
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    stations, casters = {}, {}
    for s in cfg.stations:
        rival = next((o for o in ids if o != s.id), "")
        st = Station(cfg, s.id, db, llm, rival_id=rival)
        c = Broadcaster(s.id, s.music_style, recordings, tts, s.name, realtime=False, render=True)
        st.calls, st.caster = CallManager(db, s.id, recordings), c
        c.meter, c.tts_usd_per_1k_chars = st.meter, cfg.pricing.tts_usd_per_1k_chars
        c.rotate(f"episode-{minutes:g}min")
        stations[s.id], casters[s.id] = st, c
    main_id = ids[0]
    lead, main_station = casters[main_id], stations[main_id]

    async def loop(st: Station, c: Broadcaster):
        while True:
            await st.run_block(c.emit)

    tasks = [asyncio.create_task(c.run()) for c in casters.values()]
    tasks += [asyncio.create_task(loop(stations[s], casters[s])) for s in ids]
    target = minutes * 60 / FRAME_S
    called = voted = False
    try:
        while lead.frames < target:
            sim_min = lead.frames * FRAME_S / 60
            if with_call and not called and sim_min >= call_at:
                caller, _ = main_station.calls.new_call()
                tasks.append(
                    asyncio.create_task(
                        feed_text_call(main_station.calls, caller, CALLER_LINES, gap=0.2)
                    )
                )
                called = True
            if not voted and sim_min >= vote_at and (v := main_station.votes.active(main_id)):
                for i in range(7):  # simulated listeners lean towards the last option
                    main_station.votes.cast(v.id, f"sim-{i}", v.options[-1 if i % 3 else 0])
                main_station.force_close_vote()  # applied and announced at the next block
                voted = True
            await asyncio.sleep(0.05)
            if any(t.done() and not t.cancelled() and t.exception() for t in tasks):
                raise next(t.exception() for t in tasks if t.done() and t.exception())
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        files = {sid: str(c.record_mp3.name) for sid, c in casters.items() if c.record_mp3}
        for c in casters.values():
            c.close()
        cost = sum(st.meter.take() for st in stations.values())
        db.close()
    return {"minutes": minutes, "files": files, "stamp": stamp, "cost_usd": round(cost, 4)}
