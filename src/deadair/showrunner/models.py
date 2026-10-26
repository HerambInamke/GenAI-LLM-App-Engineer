from typing import Literal

from pydantic import BaseModel, Field

SegmentType = Literal[
    "news", "banter", "song_intro", "feud", "caller", "vote_announce", "station_id", "music"
]
JOKEY = {"banter", "feud"}  # segment types where serious items are banned (FR-2.5)


class Segment(BaseModel):
    type: SegmentType
    host: str = Field(description="persona id of the host who speaks, or '' for music")
    item_ids: list[str] = Field(default_factory=list, description="feed item ids this may use")
    storyline_id: str | None = Field(None, description="storyline this segment advances")
    note: str = Field("", description="one-line direction for the host")


class BlockPlan(BaseModel):
    segments: list[Segment]


class Storyline(BaseModel):
    id: str
    station: str
    name: str
    status: Literal["active", "resolved", "dormant"] = "active"
    participants: list[str] = Field(default_factory=list)
    summary: str = ""
    last_episode: int | None = None
