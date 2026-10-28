"""Listener votes (FR-7). One vote per voter id; results apply at the next block boundary.
Votes, casts and outcomes are stored for the eval report (FR-7.4)."""

import json
import sqlite3
import uuid
from collections import Counter
from datetime import UTC, datetime

from pydantic import BaseModel


class Vote(BaseModel):
    id: str
    station: str
    question: str
    options: list[str]
    result: str | None = None
    open: bool = True


def _now() -> str:
    return datetime.now(UTC).isoformat()


class VoteManager:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def _vote(self, r) -> Vote:
        return Vote(
            id=r["id"],
            station=r["station"],
            question=r["question"],
            options=json.loads(r["options_json"]),
            result=r["result"],
            open=r["closed_at"] is None,
        )

    def open(self, station: str, question: str, options: list[str]) -> Vote:
        if not 2 <= len(options) <= 3:
            raise ValueError("a vote needs 2 or 3 options")  # FR-7.1
        if prev := self.active(station):
            self.close(prev.id)
        vid = uuid.uuid4().hex[:12]
        self.db.execute(
            "INSERT INTO votes (id, station, question, options_json, opened_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (vid, station, question, json.dumps(options), _now()),
        )
        self.db.commit()
        return self.get(vid)

    def get(self, vid: str) -> Vote | None:
        r = self.db.execute("SELECT * FROM votes WHERE id = ?", (vid,)).fetchone()
        return self._vote(r) if r else None

    def active(self, station: str) -> Vote | None:
        r = self.db.execute(
            "SELECT * FROM votes WHERE station = ? AND closed_at IS NULL ORDER BY opened_at DESC",
            (station,),
        ).fetchone()
        return self._vote(r) if r else None

    def cast(self, vid: str, voter_id: str, option: str | int) -> bool:
        """Record a vote. `option` may be the text or a 1-based keypad digit. False if rejected."""
        v = self.get(vid)
        if not v or not v.open:
            return False
        if isinstance(option, int) or str(option).isdigit():
            idx = int(option) - 1
            if not 0 <= idx < len(v.options):
                return False
            option = v.options[idx]
        if option not in v.options:
            return False
        cur = self.db.execute(
            "INSERT OR IGNORE INTO vote_casts VALUES (?, ?, ?, ?)", (vid, voter_id, option, _now())
        )
        self.db.commit()
        return cur.rowcount == 1

    def tally(self, vid: str) -> dict[str, int]:
        v = self.get(vid)
        counts = Counter(
            r[0] for r in self.db.execute("SELECT option FROM vote_casts WHERE vote_id = ?", (vid,))
        )
        return {o: counts.get(o, 0) for o in v.options} if v else {}

    def close(self, vid: str) -> str | None:
        """Close and store the winner (ties go to the earlier option)."""
        v = self.get(vid)
        if not v or not v.open:
            return v.result if v else None
        t = self.tally(vid)
        winner = max(v.options, key=lambda o: (t[o], -v.options.index(o)))
        self.db.execute(
            "UPDATE votes SET closed_at = ?, result = ? WHERE id = ?", (_now(), winner, vid)
        )
        self.db.commit()
        return winner
