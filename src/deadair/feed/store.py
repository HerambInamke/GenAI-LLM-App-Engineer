"""SQLite store for feed items (FR-1.6). Dedup by PK (url id) and UNIQUE title_key."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from deadair.feed.models import FeedItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS feed_items (
  id           TEXT PRIMARY KEY,
  title        TEXT NOT NULL,
  summary      TEXT NOT NULL DEFAULT '',
  source       TEXT NOT NULL,
  published_at TEXT NOT NULL,
  category     TEXT NOT NULL DEFAULT 'general',
  tone         TEXT NOT NULL CHECK (tone IN ('light','neutral','serious')),
  url          TEXT NOT NULL DEFAULT '',
  title_key    TEXT NOT NULL UNIQUE,
  fetched_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS feed_items_published ON feed_items(published_at);
"""

COLS = ("id", "title", "summary", "source", "published_at", "category", "tone", "url", "title_key")


class FeedStore:
    def __init__(self, path: str | Path = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def add(self, items: list[FeedItem]) -> int:
        """Insert new items; returns how many were actually new."""
        now = datetime.now(UTC).isoformat()
        rows = [
            (
                *(
                    getattr(i, c).isoformat() if c == "published_at" else getattr(i, c)
                    for c in COLS
                ),
                now,
            )
            for i in items
        ]
        before = self.db.total_changes
        with self.db:
            self.db.executemany(
                f"INSERT OR IGNORE INTO feed_items ({', '.join(COLS)}, fetched_at) "
                f"VALUES ({', '.join('?' * (len(COLS) + 1))})",
                rows,
            )
        return self.db.total_changes - before

    def get(self, item_id: str) -> FeedItem | None:
        row = self.db.execute("SELECT * FROM feed_items WHERE id = ?", (item_id,)).fetchone()
        return FeedItem(**{c: row[c] for c in COLS}) if row else None

    def active(self, max_age_hours: int = 48, now: datetime | None = None) -> list[FeedItem]:
        """Items young enough for programming (FR-1.4), newest first."""
        cutoff = ((now or datetime.now(UTC)) - timedelta(hours=max_age_hours)).isoformat()
        rows = self.db.execute(
            "SELECT * FROM feed_items WHERE published_at >= ? ORDER BY published_at DESC", (cutoff,)
        )
        return [FeedItem(**{c: r[c] for c in COLS}) for r in rows]
