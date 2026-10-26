"""Episode memory and the 24 h repetition guard (FR-3.4, FR-3.5, NFR-5).

shortcut: similarity is word-overlap Jaccard in SQLite, not embeddings; swap in sqlite-vec when an
embedding provider is chosen.
"""

import re
import sqlite3
import uuid
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

    def add(self, station: str, host: str, text: str, tags: str = "line") -> None:
        self.db.execute(
            "INSERT INTO memory_items VALUES (?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, station, host, text, datetime.now(UTC).isoformat(), tags),
        )
        self.db.commit()

    def recent(self, host: str, hours: float, tags: str = "line") -> list[str]:
        rows = self.db.execute(
            "SELECT text FROM memory_items WHERE host = ? AND tags = ? AND created_at >= ? "
            "ORDER BY created_at DESC",
            (host, tags, _ago(hours)),
        )
        return [r[0] for r in rows]

    def similar(self, host: str, text: str, k: int = 5) -> list[str]:
        q = ngrams(text, 1)
        scored = []
        for t in self.recent(host, self.retention_days * 24):
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
        grams = ngrams(sentence, self.REPEAT_N)
        if grams and any(grams & ngrams(t, self.REPEAT_N) for t in self.recent(host, 24)):
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
