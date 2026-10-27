"""Data types shared across the collector."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class NewsItem:
    game_id: str
    source_ref: str
    channel_id: str
    origin: str
    item_type: str
    title: str
    body: str
    url: str | None
    image_urls: list[str]
    published_at: datetime
    tier: str
    region: str
    content_hash: str
    source: str = "discord"
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_row(self) -> dict[str, Any]:
        """Row for news_items (id and fetched_at use database defaults)."""
        row = self.to_public_dict()
        row["raw"] = self.raw
        return row

    def to_public_dict(self) -> dict[str, Any]:
        """Serializable fields without the raw Discord payload."""
        return {
            "game_id": self.game_id,
            "source": self.source,
            "source_ref": self.source_ref,
            "channel_id": self.channel_id,
            "origin": self.origin,
            "item_type": self.item_type,
            "title": self.title,
            "body": self.body,
            "url": self.url,
            "image_urls": list(self.image_urls),
            "published_at": self.published_at.isoformat(),
            "tier": self.tier,
            "region": self.region,
            "content_hash": self.content_hash,
        }
