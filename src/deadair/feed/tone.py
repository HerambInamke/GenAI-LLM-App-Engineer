"""Rules-first tone tagging (FR-1.5). Serious beats light: a bad joke is worse than a dull read."""

import logging
import re
from collections.abc import Callable

from pydantic import BaseModel

from deadair.feed.models import FeedItem, Tone

log = logging.getLogger(__name__)

SERIOUS = re.compile(
    r"\b(dead|dies|died|death|killed|kill(ing|s)?|murder\w*|war|attack\w*|shoot\w*|bomb\w*|"
    r"terror\w*|earthquake|flood\w*|wildfire|hurricane|crash\w*|victim\w*|abuse\w*|"
    r"famine|genocide|hostage\w*|suicide|cancer|pandemic|outbreak|injur\w*|disaster|"
    r"hospital\w*|a&e|ambulance|arrest\w*|charged|court|jail\w*|prison\w*|sentenced|fraud|"
    r"lawsuit|layoffs?|missing|evacuat\w*|collapse\w*|explosion|fatal\w*|wounded|refugee\w*)\b",
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
    # unclear items start neutral; llm_tones() re-tags them in one batch when Claude is configured
    return fallback(text) if fallback else "neutral"


class _Tones(BaseModel):
    tones: list[Tone]


TONE_SYSTEM = (
    "Classify each numbered news headline as light (fun, quirky, safe to joke about), "
    "neutral (ordinary news), or serious (harm, death, crime, disaster, suffering). "
    "When unsure between neutral and serious, pick serious. Return one tone per headline, in order."
)


async def llm_tones(items: list[FeedItem], llm, model: str) -> list[FeedItem]:
    """FR-1.5 fallback: re-tag items the rules could not decide, in one batched call."""
    unclear = [i for i, it in enumerate(items) if rule_tone(f"{it.title}. {it.summary}") is None]
    if not llm or not unclear:
        return items
    prompt = "\n".join(f"{n}. {items[i].title}" for n, i in enumerate(unclear))
    try:
        out = await llm.parse(model, TONE_SYSTEM, prompt, _Tones)
    except Exception as e:  # noqa: BLE001 - rules-only tags are still usable
        log.warning("LLM tone fallback failed: %s", e)
        return items
    if len(out.tones) != len(unclear):
        return items
    items = list(items)
    for i, tone in zip(unclear, out.tones, strict=True):
        items[i] = items[i].model_copy(update={"tone": tone})
    return items
