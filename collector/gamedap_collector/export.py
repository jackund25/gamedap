"""Write recent news items to a JSON file in the repo."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .normalize import parse_timestamp

log = logging.getLogger(__name__)

EXPORT_WINDOW = timedelta(days=30)
_TIMESTAMP_FIELDS = ("published_at", "fetched_at")


def export_since(now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)) - EXPORT_WINDOW


def prepare_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop raw, normalize timestamps to UTC ISO strings, newest first."""
    items = []
    for row in rows:
        item = {k: v for k, v in row.items() if k != "raw"}
        for key in _TIMESTAMP_FIELDS:
            if item.get(key):
                item[key] = parse_timestamp(item[key]).isoformat()
        item["image_urls"] = list(item.get("image_urls") or [])
        items.append(item)
    items.sort(key=lambda i: (i["published_at"], i.get("source_ref") or ""), reverse=True)
    return items


def write_export(path: Path, rows: list[dict[str, Any]], now: datetime | None = None) -> bool:
    """Write the export if its items differ from the file on disk. Returns True if written."""
    items = prepare_items(rows)
    if _existing_items(path) == items:
        log.info("Export unchanged (%d items); not writing %s", len(items), path.name)
        return False

    payload = {
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "count": len(items),
        "items": items,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.info("Wrote %d items to %s", len(items), path.name)
    return True


def _existing_items(path: Path) -> list[dict[str, Any]] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("items")
    except (FileNotFoundError, ValueError, AttributeError):
        return None
