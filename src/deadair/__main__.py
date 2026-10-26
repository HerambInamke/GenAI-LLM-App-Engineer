"""Dead Air CLI.

python -m deadair text --minutes 20     text-only show printed to the console (Steps 2-4)
python -m deadair serve                 full station: feed, both stations, audio, web (Step 5+)
python -m deadair doctor                which providers are live and whether each key works
python -m deadair record --minutes 15   render one episode per station to recordings/ (Step 13)
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from deadair.config import load_config
from deadair.db import connect
from deadair.feed.pollers import poll_all
from deadair.feed.store import FeedStore
from deadair.hosts.memory import repetition_violations
from deadair.logs import setup_logging
from deadair.providers.llm import get_llm
from deadair.station import Event, Station

WORDS_PER_SECOND = 2.6


async def text_show(minutes: float, db_path: str, poll: bool) -> list[str]:
    cfg = load_config()
    db = connect(db_path)
    llm = get_llm()
    if poll:
        FeedStore(db).add(await poll_all(cfg.feeds.sources, llm, cfg.llm.fast_model))
    station = Station(cfg, "deadair", db, llm, rival_id="rival")
    airtime, jokey_log = 0.0, []

    async def emit(ev: Event) -> None:
        nonlocal airtime
        if ev.kind == "line":
            name = cfg.personas[ev.host].name
            print(f"  {name:>13}: {ev.text}")
            airtime += len(ev.text.split()) / WORDS_PER_SECOND
            if ev.segment in {"banter", "feud"}:
                jokey_log.append((ev.host, ev.text))
        elif ev.kind == "segment":
            print(f"[{ev.segment}]")
        elif ev.kind == "music":
            print(f"  ~ music {ev.seconds:.0f}s ~")
            airtime += ev.seconds

    while airtime < minutes * 60:
        await station.run_block(emit)
    catch = {h: cfg.personas[h].catchphrases for h in station.hosts}
    problems = repetition_violations(jokey_log, catch)
    print(
        f"\n{airtime / 60:.1f} min of airtime, {len(jokey_log)} banter/feud lines, "
        f"{len(problems)} repetition violations (NFR-5)"
    )
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(prog="deadair")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("text", help="print a text-only show")
    t.add_argument("--minutes", type=float, default=20)
    t.add_argument("--no-poll", action="store_true", help="use what is already in the DB")
    t.add_argument("-v", "--verbose", action="store_true", help="log plans and gate decisions")
    sub.add_parser("doctor", help="check config, feed and every provider key")
    r = sub.add_parser("record", help="render a whole episode to MP3 + transcript")
    r.add_argument("--minutes", type=float, default=15)
    r.add_argument("--no-call", action="store_true", help="skip the scripted caller")
    s = sub.add_parser("serve", help="run the full station and web app")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    args = ap.parse_args()
    quiet = args.cmd == "text" and not args.verbose
    setup_logging(logging.WARNING if quiet else logging.INFO)
    db_path = os.environ.get("DEADAIR_DB", "data/deadair.db")
    if args.cmd == "record":
        import json

        from deadair.record import record_episode

        out = asyncio.run(
            record_episode(args.minutes, Path("recordings"), db_path, with_call=not args.no_call)
        )
        print(json.dumps(out, indent=2))
        return
    if args.cmd == "doctor":
        from deadair.doctor import render, run

        checks = asyncio.run(run(db_path))
        print(render(checks))
        sys.exit(1 if any(c.status == "FAIL" for c in checks) else 0)
    if args.cmd == "text":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        asyncio.run(text_show(args.minutes, db_path, not args.no_poll))
    else:
        import uvicorn

        from deadair.web.app import create_app

        uvicorn.run(create_app(db_path), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
