"""Claim extraction and deterministic citation checks (FR-4.1 to FR-4.3)."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher

CITE = re.compile(r"\s*\[(f|s|t):([A-Za-z0-9_-]+)\]")
_SENT_END = re.compile(r"(?<=[.!?])\s+")
_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
MONTHS_DAYS = {
    m.lower()
    for m in "January February March April May June July August September October November "
    "December Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split()
}
# Capitalized words that are not real-world entities on their own.
COMMON = {
    "i",
    "i'm",
    "i've",
    "i'd",
    "i'll",
    "ok",
    "okay",
    "yes",
    "no",
    "folks",
    "listeners",
    "you",
    "we",
    "it",
    "the",
    "a",
    "and",
    "but",
    "so",
    "now",
    "well",
    "oh",
    "hey",
    "this",
    "that",
    "here",
    "there",
    "today",
    "tonight",
    "tomorrow",
    "up",
    "next",
    "meanwhile",
    "also",
    "breaking",
    # common sentence openers, so they are not mistaken for names at the start of a claim
    "according",
    "big",
    "from",
    "news",
    "our",
    "thanks",
    "somebody",
    "every",
    "fun",
    "if",
    "in",
    "on",
    "at",
    "after",
    "before",
    "over",
    "for",
    "with",
    "they",
    "he",
    "she",
    "his",
    "her",
    "its",
    "their",
    "my",
    "your",
    "what",
    "when",
    "where",
    "why",
    "how",
    "that's",
    "there's",
    "it's",
    "apparently",
    "reportedly",
    "officials",
    "authorities",
    "experts",
    "latest",
    "quick",
    "update",
    "plus",
    "just",
    "honestly",
    "look",
    "listen",
    "remember",
    "speaking",
    "elsewhere",
    "finally",
}


@dataclass
class Claim:
    text: str
    citations: list[str] = field(default_factory=list)  # "f:<id>" or "s:<id>"
    entities: list[str] = field(default_factory=list)
    numbers: list[str] = field(default_factory=list)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_END.split(text.strip()) if s.strip()]


def strip_citations(text: str) -> str:
    return CITE.sub("", text).strip()


def norm_num(n: str) -> str:
    return n.replace(",", "")


def rule_claim(sentence: str, allow: set[str]) -> Claim | None:
    """A sentence is a claim if it names a number, a date word, or a capitalized entity."""
    citations = [f"{k}:{v}" for k, v in CITE.findall(sentence)]
    bare = strip_citations(sentence)
    numbers = [norm_num(n) for n in _NUM.findall(bare)]
    words = _WORD.findall(bare)

    def entity(w: str) -> bool:
        return (w[0].isupper() or w.lower() in MONTHS_DAYS) and w.lower() not in COMMON | allow

    entities = [w for w in words[1:] if entity(w)]
    if not numbers and not entities and not citations:
        return None
    # The first word is capitalized anyway; count it only once the sentence is clearly a claim.
    if words and entity(words[0]):
        entities.insert(0, words[0])
    return Claim(bare, citations, entities, numbers)


def _fuzzy_in(word: str, tokens: set[str]) -> bool:
    w = word.lower().strip("'’")
    if w in tokens or w.rstrip("s") in tokens:
        return True
    return any(
        SequenceMatcher(None, w, t).ratio() >= 0.85 for t in tokens if abs(len(t) - len(w)) <= 2
    )


def verify(claim: Claim, lookup: Callable[[str], str | None]) -> str | None:
    """Return None if supported, else the reason it fails (FR-4.3)."""
    if not claim.citations:
        return "no citation"
    texts = [t for t in (lookup(c) for c in claim.citations) if t]
    if not texts:
        return "cited row not found"
    source = " ".join(texts)
    src_nums = {norm_num(n) for n in _NUM.findall(source)}
    src_words = {w.lower().strip("'’") for w in _WORD.findall(source)}
    for n in claim.numbers:
        if n not in src_nums:
            return f"number {n} not in source"
    for e in claim.entities:
        if not _fuzzy_in(e, src_words):
            return f"entity {e} not in source"
    return None
