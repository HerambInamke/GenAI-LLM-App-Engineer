"""Blocklist moderation for generated text and caller transcripts (NFR-7, FR-6.7)."""

import re
from functools import cache
from pathlib import Path

from deadair.config import CONFIG_DIR


@cache
def _pattern(path: Path = CONFIG_DIR / "blocklist.txt") -> re.Pattern | None:
    words = (
        [
            w.strip().lower()
            for w in path.read_text(encoding="utf-8").splitlines()
            if w.strip() and not w.startswith("#")
        ]
        if path.exists()
        else []
    )
    return re.compile(r"\b(" + "|".join(map(re.escape, words)) + r")\b", re.I) if words else None


def is_clean(text: str) -> bool:
    p = _pattern()
    return not (p and p.search(text))
