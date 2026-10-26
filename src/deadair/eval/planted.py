"""Planted-error claim set for the fact gate (NFR-3, Step 3 and Step 10).

True claims restate a stored item with its citation. False claims change a number, swap in an
entity from another item, drop the citation, or cite the wrong item.
"""

import random
import re
from datetime import UTC, datetime

from deadair.feed.models import FeedItem
from deadair.feed.normalize import make_item

FIXTURE_HEADLINES = [
    (
        "Tokyo opens 12 new night train routes",
        "The new routes connect Tokyo with Osaka and Sendai.",
        "light",
    ),
    (
        "Kenya plants 40 million trees in national drive",
        "The campaign covered 15 counties in Kenya.",
        "light",
    ),
    (
        "Brazil central bank holds rates at 10.5 percent",
        "Brazil kept its benchmark rate unchanged.",
        "neutral",
    ),
    (
        "Norway reports record 92 percent electric car sales",
        "Electric models made up 92 percent of Norway sales.",
        "neutral",
    ),
    (
        "Iceland volcano erupts near Grindavik for the 7th time",
        "Authorities in Iceland evacuated Grindavik.",
        "serious",
    ),
    (
        "Canada wildfire season burns 18 million hectares",
        "Officials in Canada called it the worst season on record.",
        "serious",
    ),
    (
        "Giant pumpkin weighing 1,247 kilograms wins Ohio fair",
        "The pumpkin set a new record at the Ohio fair.",
        "light",
    ),
    (
        "Germany approves 3 billion euro rail upgrade",
        "Germany will modernise 2,000 kilometres of track.",
        "neutral",
    ),
    (
        "NASA delays Artemis launch to September",
        "NASA cited heat shield checks for the Artemis delay.",
        "neutral",
    ),
    (
        "India monsoon rainfall 8 percent above average",
        "India recorded heavy rain across 20 states.",
        "neutral",
    ),
    (
        "Australia zoo welcomes 2 rare panda cubs",
        "The Adelaide zoo in Australia announced the cubs.",
        "light",
    ),
    (
        "Mexico City marathon draws 30,000 runners",
        "Runners crossed Mexico City in the annual race.",
        "light",
    ),
    ("Chile copper output falls 4 percent", "Chile is the largest copper producer.", "neutral"),
    (
        "France bans short domestic flights under 150 minutes",
        "France said trains can replace the routes.",
        "neutral",
    ),
    (
        "Spain heatwave pushes temperatures to 44 degrees",
        "Spain issued red alerts in 6 regions.",
        "serious",
    ),
    (
        "Finland tops happiness ranking for 7th year",
        "Finland again ranked first in the report.",
        "light",
    ),
    (
        "Egypt reopens Cairo museum after 5 year renovation",
        "The museum in Cairo holds 50,000 artefacts.",
        "light",
    ),
    (
        "Vietnam exports rise 14 percent in third quarter",
        "Vietnam shipped more electronics abroad.",
        "neutral",
    ),
    (
        "Scotland opens 3 new offshore wind farms",
        "The farms off Scotland will power 2 million homes.",
        "neutral",
    ),
    (
        "Peru discovers 1,000 year old temple near Lima",
        "Archaeologists in Peru found murals inside.",
        "light",
    ),
]


def fixture_items() -> list[FeedItem]:
    now = datetime.now(UTC)
    out = []
    for i, (title, summary, tone) in enumerate(FIXTURE_HEADLINES):
        it = make_item(
            title=title,
            summary=summary,
            source="Fixture Wire",
            url=f"https://fixture.example/{i}",
            category="world",
            published_at=now,
        )
        out.append(it.model_copy(update={"tone": tone}))
    return out


_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_CAP = re.compile(r"\b[A-Z][a-z]+\b")


def _bump(n: str) -> str:
    v = float(n.replace(",", ""))
    out = v + max(1, round(v * 0.37))
    return str(int(out)) if out.is_integer() else f"{out:.1f}"


def planted_claims(items: list[FeedItem], n_true: int, n_false: int, seed: int = 7) -> list[dict]:
    """Return [{"text", "expect_ok", "kind"}]. Each text is one host sentence with citations."""
    rng = random.Random(seed)
    trues, falses = [], []
    k = -1
    while len(trues) < n_true or len(falses) < n_false:
        k += 1
        it = items[k % len(items)]
        other = items[(k + 1 + rng.randrange(len(items) - 1)) % len(items)]
        title = it.title.rstrip(".")
        true_forms = [
            f"{title} [f:{it.id}].",
            f"According to {it.source}, {title} [f:{it.id}].",
            f"{it.summary.rstrip('.')} [f:{it.id}].",
            f"Big news: {title} [f:{it.id}].",
        ]
        trues.append({"text": true_forms[k % 4], "expect_ok": True, "kind": "true"})
        nums = _NUM.findall(title)
        caps = [c for c in _CAP.findall(title) if c not in {"The", "Giant"}]
        other_caps = [c for c in _CAP.findall(other.title) if c not in caps]
        kind = k % 4
        if kind == 0 and nums:
            bad = title.replace(nums[0], _bump(nums[0]), 1)
            falses.append({"text": f"{bad} [f:{it.id}].", "kind": "number"})
        elif kind == 1 and caps and other_caps:
            bad = title.replace(caps[0], other_caps[0], 1)
            falses.append({"text": f"{bad} [f:{it.id}].", "kind": "entity"})
        elif kind == 2:
            falses.append({"text": f"{title}.", "kind": "uncited"})
        else:
            falses.append({"text": f"{title} [f:{other.id}].", "kind": "wrong_citation"})
    for f in falses:
        f["expect_ok"] = False
    return trues[:n_true] + falses[:n_false]
