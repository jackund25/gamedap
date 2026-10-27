from __future__ import annotations

import json
from datetime import datetime, timezone

from gamedap_collector.export import prepare_items, write_export

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


def _row(ref: str, published_at: str) -> dict:
    return {
        "id": f"uuid-{ref}",
        "game_id": "vampir",
        "source_ref": ref,
        "title": f"Item {ref}",
        "image_urls": None,
        "published_at": published_at,
        "fetched_at": "2026-10-27T11:00:00+00:00",
        "raw": {"secret": "should not be exported"},
    }


def test_prepare_items_sorts_newest_first_and_drops_raw():
    items = prepare_items(
        [_row("1", "2026-10-20T08:00:00+00:00"), _row("2", "2026-10-25T08:00:00.123+00:00")]
    )
    assert [i["source_ref"] for i in items] == ["2", "1"]
    assert all("raw" not in i for i in items)
    assert items[0]["published_at"] == "2026-10-25T08:00:00.123000+00:00"
    assert items[0]["image_urls"] == []


def test_writes_only_when_items_change(tmp_path):
    path = tmp_path / "exports" / "news-latest.json"
    rows = [_row("1", "2026-10-20T08:00:00+00:00")]

    assert write_export(path, rows, now=NOW) is True
    first = path.read_text(encoding="utf-8")
    assert json.loads(first)["count"] == 1

    later = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)
    assert write_export(path, rows, now=later) is False
    assert path.read_text(encoding="utf-8") == first  # generated_at untouched

    rows.append(_row("2", "2026-10-26T08:00:00+00:00"))
    assert write_export(path, rows, now=later) is True
    assert json.loads(path.read_text(encoding="utf-8"))["count"] == 2


def test_empty_export_matches_initial_file(tmp_path):
    path = tmp_path / "news-latest.json"
    path.write_text('{"generated_at": null, "count": 0, "items": []}\n', encoding="utf-8")
    assert write_export(path, [], now=NOW) is False
