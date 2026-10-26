"""One station's programming loop: plan block -> write chunks -> gate -> emit (docs/Appflow.md).

`emit` is any async callable taking an Event. The audio pipeline is one emitter (it returns once
the line has been played); the text runner just prints.
"""

import asyncio
import json
import logging
import re
import sqlite3
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from deadair.config import CONFIG_DIR, Config
from deadair.feed.store import FeedStore
from deadair.gate.claims import strip_citations
from deadair.gate.gate import FactGate
from deadair.hosts.memory import EpisodeMemory
from deadair.hosts.writer import HostWriter
from deadair.providers.llm import CostMeter
from deadair.showrunner.models import JOKEY, BlockPlan, Segment
from deadair.showrunner.planner import Planner
from deadair.showrunner.storylines import StorylineRegistry
from deadair.showrunner.votes import VoteManager

log = logging.getLogger(__name__)
VOTE_BLOCKS = 2  # a vote stays open this many blocks, then applies at the next boundary


@dataclass
class Event:
    kind: str  # block | segment | line | music | sting
    station: str
    host: str = ""
    text: str = ""
    voice_id: str = ""
    segment: str = ""
    seconds: float = 0.0
    data: dict = field(default_factory=dict)


Emit = Callable[[Event], Awaitable[None]]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Station:
    def __init__(
        self,
        cfg: Config,
        station_id: str,
        db: sqlite3.Connection,
        llm=None,
        rival_id: str = "",
        seed: int | None = None,
    ):
        self.cfg, self.db, self.llm, self.id = cfg, db, llm, station_id
        st = next(s for s in cfg.stations if s.id == station_id)
        self.name, self.hosts = st.name, st.hosts
        self.rival_id = rival_id
        rival_name = next((s.name for s in cfg.stations if s.id == rival_id), "")
        self.meter = llm.meter if llm else CostMeter()
        self.feed = FeedStore(db)
        self.storylines = StorylineRegistry(db)
        self.vote_specs = {
            s["id"]: s.get("vote") for s in self.storylines.seed(CONFIG_DIR / "storylines.yaml")
        }
        self.votes = VoteManager(db)
        self.memory = EpisodeMemory(db)
        allow = {w.lower() for s in cfg.stations for w in re.findall(r"[A-Za-z]+", s.name)}
        allow |= {w.lower() for p in cfg.personas.values() for w in p.name.split()}
        allow |= {w.lower() for s in self.storylines.list(status=None) for w in s.name.split()}
        allow |= {"krvl", "dead", "air", "max", "juniper", "dex", "velma"}
        self.gate = FactGate(
            db, allow, llm, cfg.llm.fast_model, tuple(s.name for s in cfg.stations)
        )
        self.writers = {
            h: HostWriter(h, cfg.personas[h], self.name, self.memory, llm, cfg.llm.host_model, seed)
            for h in self.hosts
        }
        self.planner = Planner(
            station_id, self.name, self.hosts, rival_name, llm, cfg.llm.fast_model
        )
        self.block_no = 0
        self.vote_opened_block = 0
        self.recent: deque[str] = deque(maxlen=6)
        self.now: dict = {"station": station_id, "name": self.name, "segment": "", "hosts": []}
        self.skip = asyncio.Event()  # admin "skip segment" (FR-9.3)
        self.interrupt = asyncio.Event()  # caller barge-in (FR-6.5)
        self.current_plan: BlockPlan | None = None

    # ---------- votes at block boundaries (FR-2.4, FR-7.3) ----------
    def _boundary_votes(self) -> list[Segment]:
        """Close a due vote, apply it to its storyline, announce it, and open the next one."""
        active = self.votes.active(self.id)
        if active and self.block_no - self.vote_opened_block < VOTE_BLOCKS:
            return []
        out = []
        if active:
            winner = self.votes.close(active.id)
            story = next(
                (
                    s
                    for s in self.storylines.list(self.id)
                    if (self.vote_specs.get(s.id) or {}).get("question") == active.question
                ),
                None,
            )
            cite = ""
            if story and self.storylines.advance(
                story.id, f"Listeners voted: {winner}", self.block_no
            ):
                cite = f" [s:{story.id}]"
            out.append(
                Segment(
                    type="vote_announce",
                    host=self.hosts[0],
                    note=f"The votes are in, and you chose: {winner}{cite}.",
                )
            )
        self._open_vote()
        return out

    def _open_vote(self) -> None:
        candidates = [s for s in self.storylines.list(self.id) if self.vote_specs.get(s.id)]
        if not candidates:
            return
        story = candidates[self.block_no % len(candidates)]
        spec = self.vote_specs[story.id]
        self.votes.open(self.id, spec["question"], spec["options"])
        self.vote_opened_block = self.block_no

    # ---------- planning ----------
    async def plan_block(self) -> tuple[str, BlockPlan]:
        self.block_no += 1
        pre = self._boundary_votes()
        items = self.feed.active(self.cfg.feeds.max_age_hours)
        plan, fixes = await self.planner.plan(items, self.storylines.list(self.id))
        if fixes:
            log.info("[%s] plan fixed by rules: %s", self.id, fixes)
        plan = BlockPlan(segments=pre + plan.segments)
        block_id = f"{self.id}-{uuid.uuid4().hex[:10]}"
        self.db.execute(
            "INSERT INTO blocks VALUES (?, ?, ?, ?, ?)",
            (block_id, self.id, _now(), plan.model_dump_json(), 0.0),
        )
        self.db.commit()
        log.info(
            "[%s] block %s planned: %s", self.id, block_id, [s.type for s in plan.segments]
        )  # NFR-9
        self.current_plan = plan
        return block_id, plan

    # ---------- running ----------
    def _rival_quotes(self) -> str:
        if not self.rival_id:
            return ""
        rows = self.db.execute(
            "SELECT c.id, c.text FROM chunks c JOIN segments s ON c.segment_id = s.id "
            "JOIN blocks b ON s.block_id = b.id WHERE b.station = ? "
            "AND c.gate_result IN ('pass','regen_pass') ORDER BY c.created_at DESC LIMIT 3",
            (self.rival_id,),
        ).fetchall()
        return "\n".join(f'[t:{r["id"]}] "{strip_citations(r["text"])}"' for r in rows)

    async def run_segment(self, seg: Segment, block_id: str, emit: Emit, index: int = 0) -> None:
        seg_id = f"{block_id}-{index}"
        self.db.execute(
            "INSERT OR REPLACE INTO segments VALUES (?, ?, ?, ?, ?, ?, NULL)",
            (seg_id, block_id, seg.type, seg.host, "on_air", _now()),
        )
        self.now.update(segment=seg.type, hosts=[seg.host] if seg.host else [])
        await emit(Event("segment", self.id, seg.host, segment=seg.type, data={"note": seg.note}))
        status = "done"
        if seg.type == "music":
            await emit(Event("music", self.id, seconds=20.0))
        else:
            status = await self._speak(seg, seg_id, emit)
        self.db.execute(
            "UPDATE segments SET status = ?, ended_at = ? WHERE id = ?", (status, _now(), seg_id)
        )
        self.db.commit()

    async def _speak(self, seg: Segment, seg_id: str, emit: Emit) -> str:
        writer, persona = self.writers[seg.host], self.cfg.personas[seg.host]
        items = [i for i in (self.feed.get(x) for x in seg.item_ids) if i]
        story = self.storylines.get(seg.storyline_id) if seg.storyline_id else None
        context = "\n".join(self.recent)
        if seg.type == "feud":
            quotes = self._rival_quotes()
            context += (
                ("\nRival said (quote only these, cite [t:id]):\n" + quotes) if quotes else ""
            )

        def repeat(sentence: str) -> str | None:
            return self.memory.repeat_reason(seg.host, sentence, persona.catchphrases)

        aired = []
        async for raw in writer.chunks(seg, items, story, context):
            if self.skip.is_set() or self.interrupt.is_set():
                self.skip.clear()
                return "skipped"
            d = await self.gate.check(
                raw,
                segment_id=seg_id,
                host=seg.host,
                regen=writer.regen,
                extra=repeat if seg.type in JOKEY else None,
            )
            if d.result != "pass":
                log.info("[%s] gate %s on %r: %s", self.id, d.result, raw[:80], d.reasons)
            if d.result == "fallback":  # FR-4.4: safe fallback replaces the rest of the segment
                await emit(
                    Event(
                        "line",
                        self.id,
                        seg.host,
                        f"You are listening to {self.name}.",
                        persona.voice_id,
                        "station_id",
                    )
                )
                await emit(Event("music", self.id, seconds=8.0))
                return "fallback"
            if not d.text:
                continue
            aired.append(d.text)
            self.recent.append(f"{persona.name}: {d.text}")
            self.memory.remember(
                self.id, seg.host, d.text, persona.catchphrases if seg.type in JOKEY else []
            )
            await emit(
                Event(
                    "line",
                    self.id,
                    seg.host,
                    d.text,
                    persona.voice_id,
                    seg.type,
                    data={"gate": d.result, "chunk_id": d.chunk_id},
                )
            )
        if story and aired:
            self.storylines.advance(story.id, aired[0][:160], self.block_no)
        return "done"

    async def run_block(self, emit: Emit) -> str:
        block_id, plan = await self.plan_block()
        await emit(
            Event(
                "block",
                self.id,
                data={"block_id": block_id, "segments": [s.type for s in plan.segments]},
            )
        )
        for i, seg in enumerate(plan.segments):
            await self.run_segment(seg, block_id, emit, i)
            await emit(Event("sting", self.id))
        cost = self.meter.take()
        self.db.execute("UPDATE blocks SET cost_usd = ? WHERE id = ?", (cost, block_id))
        self.db.commit()
        log.info("[%s] block %s done, cost $%.4f", self.id, block_id, cost)  # NFR-6
        return block_id


def plan_summary(plan: BlockPlan) -> str:
    return json.dumps([s.model_dump(exclude_defaults=True) for s in plan.segments])
