from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Tone = Literal["light", "neutral", "serious"]


class FeedItem(BaseModel):
    """Normalized news item (FR-1.2). `id` is what claims cite (FR-1.6)."""

    id: str
    title: str
    summary: str
    source: str
    published_at: datetime
    category: str
    tone: Tone
    url: str
    title_key: str
