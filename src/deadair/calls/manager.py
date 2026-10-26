"""Caller queue and lifecycle (FR-6.3, FR-6.6, FR-6.7, NFR-8, NFR-9).

Callers are only ever a random uuid. Phone numbers never reach this module.
"""

import asyncio
import logging
import sqlite3
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from deadair.gate.moderation import is_clean

log = logging.getLogger(__name__)
MAX_WAITING = 3


@dataclass
class Turn:
    text: str
    ended_at: float  # monotonic time the caller finished speaking


@dataclass
class Caller:
    id: str
    station: str
    turns: asyncio.Queue = field(default_factory=asyncio.Queue)
    hung_up: bool = False
    transcript: list[str] = field(default_factory=list)
    barge_in: asyncio.Event = field(default_factory=asyncio.Event)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class CallManager:
    def __init__(self, db: sqlite3.Connection, station: str, transcripts: Path):
        self.db, self.station, self.dir = db, station, transcripts / "calls"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.waiting: deque[Caller] = deque()
        self.on_air: Caller | None = None
        self.callers: dict[str, Caller] = {}
        self.latencies_ms: list[float] = []  # NFR-1 samples
        self.bargein_ms: list[float] = []  # NFR-2 samples

    def _status(self, c: Caller, status: str) -> None:
        log.info("[%s] call %s -> %s", self.station, c.id[:8], status)  # NFR-9 lifecycle
        ended = _now() if status in {"done", "rejected", "dropped"} else None
        self.db.execute(
            "UPDATE calls SET status = ?, ended_at = COALESCE(?, ended_at), transcript_path = ? "
            "WHERE id = ?",
            (status, ended, str(self.dir / f"{c.id}.txt"), c.id),
        )
        self.db.commit()

    def new_call(self) -> tuple[Caller, str]:
        """Showrunner decision (FR-6.3): queue unless the line is full."""
        c = Caller(uuid.uuid4().hex, self.station)
        self.callers[c.id] = c
        self.db.execute(
            "INSERT INTO calls (id, station, started_at, status) VALUES (?, ?, ?, 'new')",
            (c.id, self.station, _now()),
        )
        if len(self.waiting) >= MAX_WAITING:
            self._status(c, "rejected")
            return c, "rejected"
        self.waiting.append(c)
        self._status(c, "queued")
        return c, "queued"

    def hear(self, caller_id: str, text: str, ended_at: float | None = None) -> bool:
        """A transcribed utterance from a caller. False if the caller was dropped (FR-6.7)."""
        c = self.callers.get(caller_id)
        if not c or c.hung_up or not text.strip():
            return False
        self._log(c, f"caller: {text}")
        if not is_clean(text):
            self.drop(caller_id, "blocklist")
            return False
        if c is self.on_air:
            c.turns.put_nowait(Turn(text.strip(), ended_at or time.monotonic()))
        return True

    def take_next(self) -> Caller | None:
        while self.waiting:
            c = self.waiting.popleft()
            if not c.hung_up:
                self.on_air = c
                self._status(c, "on_air")
                return c
        return None

    def hang_up(self, caller_id: str) -> None:
        c = self.callers.get(caller_id)
        if not c or c.hung_up:
            return
        c.hung_up = True
        c.turns.put_nowait(None)  # wake a session waiting on this caller
        if c in self.waiting:
            self.waiting.remove(c)
        self._status(c, "done")

    def drop(self, caller_id: str, reason: str) -> None:
        c = self.callers[caller_id]
        log.warning("[%s] dropping call %s: %s", self.station, caller_id[:8], reason)
        self.hang_up(caller_id)
        self._status(c, "dropped")

    def finish(self) -> None:
        if self.on_air:
            self.hang_up(self.on_air.id)
            self.on_air = None

    def _log(self, c: Caller, line: str) -> None:
        c.transcript.append(line)
        with open(self.dir / f"{c.id}.txt", "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def host_said(self, caller_id: str, text: str) -> None:
        if c := self.callers.get(caller_id):
            self._log(c, f"host: {text}")
