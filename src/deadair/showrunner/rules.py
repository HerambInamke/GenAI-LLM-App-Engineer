"""Hard programming rules, enforced in code on every plan (FR-2.3, FR-2.5, FR-8.3)."""

from deadair.feed.models import FeedItem
from deadair.showrunner.models import JOKEY, BlockPlan


def enforce(
    plan: BlockPlan, items: dict[str, FeedItem], hosts: list[str], storyline_ids: set[str]
) -> tuple[BlockPlan, list[str]]:
    """Repair a plan so it obeys the rules. Returns the fixed plan and what was changed."""
    fixes, out = [], []
    advanced: set[str] = set()
    feuds = 0
    for i, seg in enumerate(plan.segments):
        seg = seg.model_copy(deep=True)
        if seg.type != "music" and seg.host not in hosts:
            fixes.append(f"seg {i}: unknown host {seg.host!r} -> {hosts[i % len(hosts)]}")
            seg.host = hosts[i % len(hosts)]
        unknown = [x for x in seg.item_ids if x not in items]
        if unknown:
            fixes.append(f"seg {i}: dropped unknown items {unknown}")
            seg.item_ids = [x for x in seg.item_ids if x in items]
        if seg.type in JOKEY:
            serious = [x for x in seg.item_ids if items[x].tone == "serious"]
            if serious:
                fixes.append(f"seg {i}: serious items removed from {seg.type} {serious}")
                seg.item_ids = [x for x in seg.item_ids if x not in serious]
        if seg.type == "feud":
            feuds += 1
            if feuds > 1:
                fixes.append(f"seg {i}: second feud jab in block -> banter")
                seg.type = "banter"
        if seg.storyline_id:
            if seg.storyline_id not in storyline_ids or seg.storyline_id in advanced:
                fixes.append(f"seg {i}: storyline {seg.storyline_id} beat dropped")
                seg.storyline_id = None
            else:
                advanced.add(seg.storyline_id)
        if seg.type == "news" and not seg.item_ids:
            fixes.append(f"seg {i}: news without items -> station_id")
            seg.type = "station_id"
        out.append(seg)
    return BlockPlan(segments=out), fixes


def violations(plan: BlockPlan, items: dict[str, FeedItem]) -> list[str]:
    """Checker used by tests and eval: an empty list means the plan is legal."""
    v = []
    if sum(s.type == "feud" for s in plan.segments) > 1:
        v.append("more than one feud jab")
    beats = [s.storyline_id for s in plan.segments if s.storyline_id]
    if len(beats) != len(set(beats)):
        v.append("storyline advanced twice")
    for s in plan.segments:
        if s.type in JOKEY and any(items[x].tone == "serious" for x in s.item_ids if x in items):
            v.append(f"serious item in {s.type}")
    return v
