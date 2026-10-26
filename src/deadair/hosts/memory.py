"""Episode memory and the 24 h repetition guard (FR-3.4, FR-3.5, NFR-5).

shortcut: similarity is word-overlap Jaccard in SQLite, not embeddings; swap in sqlite-vec when an
embedding provider is chosen.
"""

import re
import sqlite3
import uuid
from collections import Counter, deque
from datetime import UTC, datetime, timedelta

_W = re.compile(r"[a-z0-9']+")


def words(text: str) -> list[str]:
    return _W.findall(text.lower())


def ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    w = words(text)
    return {tuple(w[i : i + n]) for i in range(len(w) - n + 1)}


def _ago(hours: float) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


class EpisodeMemory:
    REPEAT_N = 5  # a shared 5-word run counts as a reused line

    def __init__(self, db: sqlite3.Connection, retention_days: int = 7):
        self.db, self.retention_days = db, retention_days
        # Per-host index of 5-grams aired in the last 24 h, so a repeat check is a set lookup
        # instead of re-reading and re-tokenising a whole day of lines (24/7 operation).
        self._lines: dict[str, deque[tuple[datetime, set]]] = {}
        self._grams: dict[str, Counter] = {}

    def _index(self, host: str) -> Counter:
        if host not in self._grams:
            self._lines[host], self._grams[host] = deque(), Counter()
            rows = self.db.execute(
                "SELECT text, created_at FROM memory_items WHERE host = ? AND tags = 'line' "
                "AND created_at >= ? ORDER BY created_at",
                (host, _ago(24)),
            )
            for text, created in rows:
                self._push(host, datetime.fromisoformat(created), text)
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        lines, grams = self._lines[host], self._grams[host]
        while lines and lines[0][0] < cutoff:
            for g in lines.popleft()[1]:
                grams[g] -= 1
                if grams[g] <= 0:
                    del grams[g]  # Counter.subtract would keep zero keys and grow forever
        return grams

    def _push(self, host: str, at: datetime, text: str) -> None:
        g = ngrams(text, self.REPEAT_N)
        self._lines[host].append((at, g))
        self._grams[host].update(g)

    def add(self, station: str, host: str, text: str, tags: str = "line") -> None:
        now = datetime.now(UTC)
        self.db.execute(
            "INSERT INTO memory_items VALUES (?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, station, host, text, now.isoformat(), tags),
        )
        self.db.commit()
        if tags == "line" and host in self._grams:
            self._push(host, now, text)

    def recent(self, host: str, hours: float, tags: str = "line", limit: int = 10_000) -> list[str]:
        rows = self.db.execute(
            "SELECT text FROM memory_items WHERE host = ? AND tags = ? AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT ?",
            (host, tags, _ago(hours), limit),
        )
        return [r[0] for r in rows]

    def similar(self, host: str, text: str, k: int = 5) -> list[str]:
        q = ngrams(text, 1)
        scored = []
        for t in self.recent(host, self.retention_days * 24, limit=500):
            g = ngrams(t, 1)
            if q and g:
                scored.append((len(q & g) / len(q | g), t))
        return [t for s, t in sorted(scored, reverse=True)[:k] if s > 0]

    def used_catchphrases(self, host: str, hours: float = 24) -> set[str]:
        return set(self.recent(host, hours, tags="catchphrase"))

    def available_catchphrases(self, host: str, catchphrases: list[str]) -> list[str]:
        used = self.used_catchphrases(host)
        return [c for c in catchphrases if c not in used]

    def repeat_reason(self, host: str, sentence: str, catchphrases: list[str]) -> str | None:
        """Why this sentence would break NFR-5, or None."""
        low = " ".join(words(sentence))
        for c in self.used_catchphrases(host) & set(catchphrases):
            if " ".join(words(c)) in low:
                return f"catchphrase reused within 24h: {c}"
        index = self._index(host)
        if any(index[g] > 0 for g in ngrams(sentence, self.REPEAT_N)):
            return "line repeated within 24h"
        return None

    def remember(self, station: str, host: str, text: str, catchphrases: list[str]) -> None:
        """Store an aired line and any catchphrases it used."""
        self.add(station, host, text)
        low = " ".join(words(text))
        for c in catchphrases:
            if " ".join(words(c)) in low:
                self.add(station, host, c, tags="catchphrase")

    def prune(self) -> None:
        self.db.execute(
            "DELETE FROM memory_items WHERE created_at < ?", (_ago(self.retention_days * 24),)
        )
        self.db.commit()


def repetition_violations(
    log: list[tuple[str, str]], catchphrases: dict[str, list[str]]
) -> list[str]:
    """NFR-5 checker over an aired (host, text) log covering 24 h. Empty list means pass."""
    out, seen = [], {}
    for host, text in log:
        mine = seen.setdefault(host, {"grams": set(), "phrases": set()})
        low = " ".join(words(text))
        for c in catchphrases.get(host, []):
            if " ".join(words(c)) in low:
                if c in mine["phrases"]:
                    out.append(f"{host} reused catchphrase: {c}")
                mine["phrases"].add(c)
        grams = ngrams(text, EpisodeMemory.REPEAT_N)
        if grams & mine["grams"]:
            out.append(f"{host} repeated: {text[:60]}")
        mine["grams"] |= grams
    return out
