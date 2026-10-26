"""Rules-first tone tagging (FR-1.5). Serious beats light: a bad joke is worse than a dull read."""

import re
from collections.abc import Callable

from deadair.feed.models import Tone

SERIOUS = re.compile(
    r"\b(dead|dies|died|death|killed|kill(ing|s)?|murder\w*|war|attack\w*|shoot\w*|bomb\w*|"
    r"terror\w*|earthquake|flood\w*|wildfire|hurricane|crash\w*|victim\w*|abuse\w*|"
    r"famine|genocide|hostage\w*|suicide|cancer|pandemic|outbreak|injur\w*|disaster)\b",
    re.I,
)
LIGHT = re.compile(
    r"\b(cat|cats|dog|dogs|puppy|panda|festival|recipe|pizza|celebrity|celebrities|"
    r"quirky|viral|meme|record-breaking|world record|bake\w*|cake|costume|holiday|"
    r"comedy|game show|zoo|giant pumpkin)\b",
    re.I,
)


def rule_tone(text: str) -> Tone | None:
    """Return a tone if the rules are confident, else None (unclear)."""
    if SERIOUS.search(text):
        return "serious"
    if LIGHT.search(text):
        return "light"
    return None


def tag_tone(text: str, fallback: Callable[[str], Tone] | None = None) -> Tone:
    tone = rule_tone(text)
    if tone:
        return tone
    # shortcut: no LLM yet, unclear items default to neutral; wire the Claude fallback in Task 1b
    return fallback(text) if fallback else "neutral"
