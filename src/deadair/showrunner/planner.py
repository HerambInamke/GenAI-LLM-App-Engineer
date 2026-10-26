"""Block planner (FR-2.1). Claude proposes a JSON plan; rules.enforce() has the final say."""

import logging

from deadair.feed.models import FeedItem
from deadair.showrunner.models import BlockPlan, Segment, Storyline
from deadair.showrunner.rules import enforce

log = logging.getLogger(__name__)

PLAN_SYSTEM = """You are the showrunner of {station}, a fictional 24/7 AI radio station.
Plan the next ~10-minute block as 10 to 14 segments.
Segment types: news (1-2 item_ids), banter (may use light items only), song_intro, music,
feud (one jab at the rival station {rival}, at most one per block), station_id.
Hosts (persona ids): {hosts}. Alternate hosts so both talk.
Never put serious items in banter or feud. Advance each storyline at most once (storyline_id).
Use only item ids from the list. Give each segment a one-line note for the host."""


class Planner:
    def __init__(
        self,
        station_id: str,
        station_name: str,
        hosts: list[str],
        rival: str = "",
        llm=None,
        model: str = "claude-haiku-5-5",
    ):
        self.station_id, self.station_name, self.hosts = station_id, station_name, hosts
        self.rival, self.llm, self.model = rival, llm, model
        self.recently_used: list[str] = []

    def _fresh(self, items: list[FeedItem], n: int) -> list[FeedItem]:
        """Prefer items not read in the last few blocks; fall back to the newest."""
        unused = [i for i in items if i.id not in self.recently_used]
        picked = (unused or items)[:n]
        self.recently_used = (self.recently_used + [i.id for i in picked])[-60:]
        return picked

    def default(self, items: list[FeedItem], storylines: list[Storyline]) -> BlockPlan:
        a, b = self.hosts[0], self.hosts[1]
        news = self._fresh(items, 6)
        light = [i for i in news if i.tone == "light"]
        joke_story = next((s for s in storylines if s.station == self.station_id), None)
        feud_story = next((s for s in storylines if s.station == "shared"), None)

        def ids(k: int) -> list[str]:
            return [i.id for i in news[k : k + 2]]

        segs = [
            Segment(type="station_id", host=a),
            Segment(type="news", host=a, item_ids=ids(0), note="lead headlines"),
            Segment(
                type="banter",
                host=b,
                item_ids=[light[0].id] if light else [],
                storyline_id=joke_story.id if joke_story else None,
                note="react, have fun",
            ),
            Segment(type="news", host=b, item_ids=ids(2)),
            Segment(type="song_intro", host=a),
            Segment(type="music", host=""),
            Segment(type="news", host=a, item_ids=ids(4)),
            Segment(type="banter", host=a, note="riff with your co-host"),
            Segment(type="song_intro", host=b),
            Segment(type="music", host=""),
            Segment(type="station_id", host=b),
        ]
        if self.rival:
            segs.insert(
                7,
                Segment(
                    type="feud",
                    host=b,
                    storyline_id=feud_story.id if feud_story else None,
                    note=f"one jab at {self.rival}",
                ),
            )
        return BlockPlan(segments=segs)

    async def plan(
        self, items: list[FeedItem], storylines: list[Storyline]
    ) -> tuple[BlockPlan, list[str]]:
        plan = None
        if self.llm:
            prompt = "Items:\n" + "\n".join(f"{i.id} ({i.tone}) {i.title}" for i in items[:30])
            prompt += "\n\nStorylines:\n" + "\n".join(
                f"{s.id}: {s.name} - {s.summary}" for s in storylines
            )
            system = PLAN_SYSTEM.format(
                station=self.station_name, rival=self.rival or "none", hosts=", ".join(self.hosts)
            )
            try:
                plan = await self.llm.parse(self.model, system, prompt, BlockPlan)
            except Exception as e:  # noqa: BLE001 - deterministic plan keeps the station on air
                log.warning("LLM planning failed, using default plan: %s", e)
        plan = plan or self.default(items, storylines)
        return enforce(plan, {i.id: i for i in items}, self.hosts, {s.id for s in storylines})
