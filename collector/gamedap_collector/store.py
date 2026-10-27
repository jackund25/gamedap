"""Supabase persistence for news items and per-channel collector state."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Protocol

from .config import ConfigError
from .models import NewsItem

NEWS_TABLE = "news_items"
STATE_TABLE = "collector_state"
PUBLIC_COLUMNS = (
    "id,game_id,source,source_ref,channel_id,origin,item_type,title,body,url,"
    "image_urls,published_at,tier,region,content_hash,fetched_at"
)


class StateStore(Protocol):
    def get_last_message_id(self, channel_id: str) -> str | None: ...
    def set_last_message_id(self, channel_id: str, message_id: str) -> None: ...
    def upsert_items(self, items: list[NewsItem]) -> None: ...


class SupabaseStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    @classmethod
    def from_env(cls) -> SupabaseStore:
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
        if not url or not key:
            raise ConfigError("SUPABASE_URL and SUPABASE_SECRET_KEY must be set")
        from supabase import create_client  # deferred: heavy import

        return cls(create_client(url, key))

    def get_last_message_id(self, channel_id: str) -> str | None:
        response = (
            self._client.table(STATE_TABLE)
            .select("last_message_id")
            .eq("channel_id", channel_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0].get("last_message_id") if rows else None

    def set_last_message_id(self, channel_id: str, message_id: str) -> None:
        row = {
            "channel_id": channel_id,
            "last_message_id": message_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._client.table(STATE_TABLE).upsert(row, on_conflict="channel_id").execute()

    def upsert_items(self, items: list[NewsItem]) -> None:
        """Insert new items; existing content_hash rows are left untouched."""
        if not items:
            return
        rows = [item.to_row() for item in items]
        (
            self._client.table(NEWS_TABLE)
            .upsert(rows, on_conflict="content_hash", ignore_duplicates=True)
            .execute()
        )

    def fetch_recent(self, since: datetime) -> list[dict[str, Any]]:
        response = (
            self._client.table(NEWS_TABLE)
            .select(PUBLIC_COLUMNS)
            .gte("published_at", since.isoformat())
            .order("published_at", desc=True)
            .limit(1000)
            .execute()
        )
        return list(response.data or [])
