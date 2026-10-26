"""Fetch sources (FR-1.1). One failing source never stops the others."""

import logging
import os

import feedparser
import httpx

from deadair.config import FeedSource
from deadair.feed.models import FeedItem
from deadair.feed.normalize import dedupe, from_newsapi, from_rss_entry

log = logging.getLogger(__name__)
UA = {"User-Agent": "DeadAirBot/0.1 (+https://github.com/HerambInamke)"}


async def fetch_source(client: httpx.AsyncClient, src: FeedSource) -> list[FeedItem]:
    if src.kind == "rss":
        resp = await client.get(str(src.url))
        resp.raise_for_status()
        entries = feedparser.parse(resp.content).entries
        items = [from_rss_entry(e, src.name, src.category) for e in entries]
    else:
        key = os.environ.get("NEWSAPI_KEY")
        if not key:
            return []
        resp = await client.get(str(src.url), headers={"X-Api-Key": key})
        resp.raise_for_status()
        items = [from_newsapi(a, src.category) for a in resp.json().get("articles", [])]
    return [i for i in items if i]


async def poll_all(sources: list[FeedSource]) -> list[FeedItem]:
    items: list[FeedItem] = []
    async with httpx.AsyncClient(timeout=15, headers=UA, follow_redirects=True) as client:
        for src in sources:
            try:
                items += await fetch_source(client, src)
            except Exception as e:  # noqa: BLE001 - isolate per-source failures (NFR-4)
                log.warning("feed source %s failed: %s", src.name, e)
    return dedupe(items)
