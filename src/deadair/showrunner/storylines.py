"""Storyline registry (FR-2.2). Summaries keep the last few beats so prompts stay short."""

import json
import sqlite3
from pathlib import Path

import yaml

from deadair.showrunner.models import Storyline

MAX_BEATS = 5


class StorylineRegistry:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def seed(self, path: Path) -> list[dict]:
        """Insert storylines from YAML once; existing rows keep their progress. Returns raw rows."""
        if not path.exists():
            return []
        rows = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        for s in rows:
            st = Storyline(**{k: v for k, v in s.items() if k != "vote"})
            self.db.execute(
                "INSERT OR IGNORE INTO storylines VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    st.id,
                    st.station,
                    st.name,
                    st.status,
                    json.dumps(st.participants),
                    st.summary,
                    None,
                ),
            )
        self.db.commit()
        return rows

    def _row(self, r) -> Storyline:
        return Storyline(
            id=r["id"],
            station=r["station"],
            name=r["name"],
            status=r["status"],
            participants=json.loads(r["participants_json"]),
            summary=r["summary"],
            last_episode=r["last_episode"],
        )

    def get(self, sid: str) -> Storyline | None:
        r = self.db.execute("SELECT * FROM storylines WHERE id = ?", (sid,)).fetchone()
        return self._row(r) if r else None

    def list(self, station: str | None = None, status: str | None = "active") -> list[Storyline]:
        q, args = "SELECT * FROM storylines WHERE 1=1", []
        if station:
            q += " AND (station = ? OR station = 'shared')"
            args.append(station)
        if status:
            q += " AND status = ?"
            args.append(status)
        return [self._row(r) for r in self.db.execute(q + " ORDER BY id", args)]

    def advance(self, sid: str, beat: str, block_no: int) -> bool:
        """Add one beat. Refuses a second beat in the same block (FR-2.3)."""
        st = self.get(sid)
        if not st or st.last_episode == block_no:
            return False
        beats = [b for b in st.summary.split(" | ") if b] + [beat.strip()]
        self.db.execute(
            "UPDATE storylines SET summary = ?, last_episode = ? WHERE id = ?",
            (" | ".join(beats[-MAX_BEATS:]), block_no, sid),
        )
        self.db.commit()
        return True
