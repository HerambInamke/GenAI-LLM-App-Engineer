"""Turn raw RSS entries / API articles into FeedItems (FR-1.2, FR-1.3)."""

import calendar
import hashlib
import html
import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from deadair.feed.models import FeedItem
from deadair.feed.tone import tag_tone

_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^a-z0-9 ]+")


def clean(text: str | None) -> str:
    return _SPACE.sub(" ", html.unescape(_TAGS.sub(" ", text or ""))).strip()


def title_key(title: str) -> str:
    """Dedup key: lowercase, punctuation stripped, whitespace collapsed."""
    return _SPACE.sub(" ", _NON_WORD.sub(" ", title.lower())).strip()


def normalize_url(url: str) -> str:
    """Drop fragment and utm_* tracking params so the same story dedups."""
    if not url:
        return ""
    p = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith("utm_")])
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), query, ""))


def item_id(url: str, tkey: str) -> str:
    return hashlib.sha1((url or tkey).encode()).hexdigest()[:16]


def make_item(
    *,
    title: str,
    summary: str,
    source: str,
    url: str,
    category: str,
    published_at: datetime | None,
    now: datetime | None = None,
) -> FeedItem | None:
    title, summary = clean(title), clean(summary)
    if not title:
        return None
    url, tkey = normalize_url(url), title_key(title)
    return FeedItem(
        id=item_id(url, tkey),
        title=title,
        summary=summary,
        source=source,
        published_at=published_at or now or datetime.now(UTC),
        category=category,
        tone=tag_tone(f"{title}. {summary}"),
        url=url,
        title_key=tkey,
    )


def from_rss_entry(entry: dict, source: str, category: str) -> FeedItem | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    published = datetime.fromtimestamp(calendar.timegm(parsed), UTC) if parsed else None
    return make_item(
        title=entry.get("title", ""),
        summary=entry.get("summary", ""),
        source=source,
        url=entry.get("link", ""),
        category=category,
        published_at=published,
    )


def from_newsapi(article: dict, category: str) -> FeedItem | None:
    ts = article.get("publishedAt")
    published = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
    return make_item(
        title=article.get("title") or "",
        summary=article.get("description") or "",
        source=(article.get("source") or {}).get("name") or "NewsAPI",
        url=article.get("url") or "",
        category=category,
        published_at=published,
    )


def dedupe(items: list[FeedItem]) -> list[FeedItem]:
    """Keep the first item per id (URL) and per normalized title (FR-1.3)."""
    seen: set[str] = set()
    out = []
    for it in items:
        if it.id in seen or it.title_key in seen:
            continue
        seen.update((it.id, it.title_key))
        out.append(it)
    return out
