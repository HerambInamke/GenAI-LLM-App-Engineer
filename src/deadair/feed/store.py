"""SQLite store for feed items (FR-1.6). Dedup by PK (url id) and UNIQUE title_key."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from deadair.db import connect
from deadair.feed.models import FeedItem

COLS = ("id", "title", "summary", "source", "published_at", "category", "tone", "url", "title_key")


class FeedStore:
    def __init__(self, db: sqlite3.Connection | str | Path = ":memory:"):
        self.db = db if isinstance(db, sqlite3.Connection) else connect(db)

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
