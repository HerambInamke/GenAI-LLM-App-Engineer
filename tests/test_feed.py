import time
from datetime import UTC, datetime, timedelta

import pytest

from deadair.feed.normalize import dedupe, from_newsapi, from_rss_entry, normalize_url, title_key
from deadair.feed.store import FeedStore
from deadair.feed.tone import rule_tone, tag_tone

NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)
TONE_WORDS = {"serious": "earthquake", "light": "giant pumpkin", "neutral": "budget"}


def sample_entries(n=200):
    """Raw RSS-like entries with HTML, entities, tracking params and missing fields."""
    out = []
    for i in range(n):
        tone = list(TONE_WORDS)[i % 3]
        out.append(
            {
                "title": f"  Story {i}: <b>{TONE_WORDS[tone]}</b> &amp; more  ",
                "summary": f"<p>Summary   of story {i}.</p>" if i % 7 else None,
                "link": f"https://News.example.com/a/{i}/?utm_source=rss&id={i}#top",
                "published_parsed": time.gmtime((NOW - timedelta(hours=i % 72)).timestamp()),
            }
        )
    return out


def test_200_items_normalize():
    items = [from_rss_entry(e, "Example", "world") for e in sample_entries()]
    assert len(items) == 200
    for i, it in enumerate(items):
        assert it.title == f"Story {i}: {TONE_WORDS[it.tone]} & more"
        assert "<" not in it.summary and "  " not in it.summary
        assert it.url == f"https://news.example.com/a/{i}?id={i}"
        assert it.tone == list(TONE_WORDS)[i % 3]
        assert it.published_at.tzinfo is not None
        assert len(it.id) == 16
    assert len({it.id for it in items}) == 200


def test_dedupe_by_url_and_title():
    base = sample_entries(3)
    same_url = {**base[0], "title": "Totally different title"}
    same_title = {
        **base[1],
        "link": "https://other.example.com/x",
        "title": "STORY 1: Giant Pumpkin & more!",
    }
    items = [from_rss_entry(e, "Ex", "world") for e in base + [same_url, same_title]]
    assert [it.title for it in dedupe(items)] == [it.title for it in items[:3]]


def test_store_dedups_across_polls_and_drops_old():
    store = FeedStore()
    items = [from_rss_entry(e, "Ex", "world") for e in sample_entries()]
    assert store.add(items) == 200
    assert store.add(items) == 0  # second poll: nothing new
    active = store.active(48, now=NOW)
    assert active and all(NOW - it.published_at <= timedelta(hours=48) for it in active)
    assert len(active) < 200
    assert store.get(items[0].id) == items[0]


def test_newsapi_article():
    it = from_newsapi(
        {
            "title": "Rates held",
            "description": "Central bank holds rates.",
            "url": "https://x.com/r",
            "publishedAt": "2026-10-26T09:00:00Z",
            "source": {"name": "Wire"},
        },
        "business",
    )
    assert it.source == "Wire" and it.published_at == datetime(2026, 10, 26, 9, tzinfo=UTC)
    assert from_newsapi({"title": None}, "x") is None


@pytest.mark.parametrize(
    "text,tone",
    [
        ("Earthquake kills dozens", "serious"),
        ("Cat elected honorary mayor", "light"),
        ("Cat rescued after flood", "serious"),  # serious beats light
        ("Parliament debates budget", None),
    ],
)
def test_rule_tone(text, tone):
    assert rule_tone(text) == tone


def test_unclear_tone_uses_fallback():
    assert tag_tone("Parliament debates budget") == "neutral"
    assert tag_tone("Parliament debates budget", fallback=lambda _: "light") == "light"


def test_helpers():
    assert title_key("  Hello, World!! ") == "hello world"
    assert normalize_url("") == ""
