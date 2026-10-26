"""Run the newsroom: `python -m deadair.feed [--once]`."""

import argparse
import asyncio
import logging
import os

from deadair.config import load_config
from deadair.feed.pollers import poll_all
from deadair.feed.store import FeedStore
from deadair.providers.llm import get_llm

log = logging.getLogger("deadair.feed")


async def main(once: bool) -> None:
    full = load_config()
    cfg, llm = full.feeds, get_llm()
    store = FeedStore(os.environ.get("DEADAIR_DB", "data/deadair.db"))
    while True:
        new = store.add(await poll_all(cfg.sources, llm, full.llm.fast_model))
        active = len(store.active(cfg.max_age_hours))
        log.info("poll done: %d new, %d in active pool", new, active)
        if once:
            return
        await asyncio.sleep(cfg.poll_minutes * 60)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="poll once and exit")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    asyncio.run(main(ap.parse_args().once))
