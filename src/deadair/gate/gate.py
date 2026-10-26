"""Gate policy: check, regenerate once, strip, or fall back; log every decision (FR-4.4, FR-4.5)."""

import json
import logging
import sqlite3
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from pydantic import BaseModel

from deadair.gate.claims import CITE, Claim, rule_claim, split_sentences, strip_citations, verify
from deadair.gate.moderation import is_clean

log = logging.getLogger(__name__)

Regen = Callable[[str, list[str]], Awaitable[str]]
SentenceCheck = Callable[[str], str | None]  # returns a failure reason or None


class FactualSentences(BaseModel):
    indexes: list[int]


EXTRACT_SYSTEM = (
    "You label radio-host sentences. A factual claim is any statement about a real-world event, "
    "number, a person's action, or a date. Jokes, opinions, greetings and banter are not claims. "
    "Return the 0-based indexes of sentences that contain at least one factual claim."
)


@dataclass
class Review:
    sentence: str
    claim: Claim | None
    reason: str | None


@dataclass
class GateDecision:
    chunk_id: str
    result: str  # pass | regen_pass | stripped | fallback
    text: str  # what goes to TTS, citations removed
    claims: list[dict] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


class FactGate:
    def __init__(
        self,
        db: sqlite3.Connection,
        allow: set[str],
        llm=None,
        model: str = "claude-haiku-5-5",
        allow_phrases: tuple[str, ...] = (),
    ):
        self.db, self.llm, self.model = db, llm, model
        self.allow = {w.lower() for w in allow}
        # fictional names that contain numbers, like "Dead Air 88.1", are not claims
        self.allow_phrases = sorted(allow_phrases, key=len, reverse=True)

    def lookup(self, ref: str) -> str | None:
        kind, _, rid = ref.partition(":")
        if kind == "f":
            r = self.db.execute(
                "SELECT title, summary, source FROM feed_items WHERE id = ?", (rid,)
            ).fetchone()
            return f"{r['title']}. {r['summary']} {r['source']}" if r else None
        if kind == "s":
            r = self.db.execute(
                "SELECT name, summary FROM storylines WHERE id = ?", (rid,)
            ).fetchone()
            return f"{r['name']}. {r['summary']}" if r else None
        if kind == "t":  # a quote of another station's aired line (FR-8.2)
            r = self.db.execute("SELECT text FROM chunks WHERE id = ?", (rid,)).fetchone()
            return strip_citations(r["text"]) if r else None
        return None

    async def _llm_factual(self, sentences: list[str]) -> set[int]:
        if not self.llm:
            return set()
        prompt = "\n".join(f"{i}: {strip_citations(s)}" for i, s in enumerate(sentences))
        try:
            out = await self.llm.parse(self.model, EXTRACT_SYSTEM, prompt, FactualSentences)
            return set(out.indexes)
        except Exception as e:  # noqa: BLE001 - the rule pass still runs
            log.warning("LLM claim extraction failed: %s", e)
            return set()

    async def review(self, text: str, extra: SentenceCheck | None = None) -> list[Review]:
        sentences = split_sentences(text)
        flagged = await self._llm_factual(sentences)
        out = []
        for i, s in enumerate(sentences):
            probe = s
            for p in self.allow_phrases:
                probe = probe.replace(p, "")
            claim = rule_claim(probe, self.allow)
            if claim is None and i in flagged:
                claim = Claim(strip_citations(s), [f"{k}:{v}" for k, v in CITE.findall(s)])
            reason = None
            if not is_clean(s):
                reason = "moderation"
            elif claim:
                reason = verify(claim, self.lookup)
            if reason is None and extra:
                reason = extra(strip_citations(s))
            out.append(Review(s, claim, reason))
        return out

    async def check(
        self,
        text: str,
        *,
        segment_id: str,
        host: str,
        regen: Regen | None = None,
        extra: SentenceCheck | None = None,
    ) -> GateDecision:
        reviews = await self.review(text, extra)
        result = "pass"
        if any(r.reason for r in reviews) and regen:
            try:
                retry = await self.review(
                    await regen(text, [r.reason for r in reviews if r.reason]), extra
                )
                reviews, result = retry, "regen_pass"
            except Exception as e:  # noqa: BLE001 - fall through to stripping
                log.warning("regeneration failed: %s", e)
        if any(r.reason for r in reviews):
            kept = [r for r in reviews if not r.reason]
            result = "stripped" if kept else "fallback"
        else:
            kept = reviews
        decision = GateDecision(
            chunk_id=uuid.uuid4().hex[:12],
            result=result,
            text=" ".join(strip_citations(r.sentence) for r in kept),
            claims=[
                {
                    **(asdict(r.claim) if r.claim else {"text": strip_citations(r.sentence)}),
                    "ok": r.reason is None,
                    "reason": r.reason,
                }
                for r in reviews
                if r.claim or r.reason
            ],
            reasons=[r.reason for r in reviews if r.reason],
        )
        self.db.execute(
            "INSERT INTO chunks (id, segment_id, host, text, gate_result, claims_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                decision.chunk_id,
                segment_id,
                host,
                text,
                decision.result,
                json.dumps(decision.claims),
                datetime.now(UTC).isoformat(),
            ),
        )
        self.db.commit()
        return decision
