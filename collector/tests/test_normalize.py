from __future__ import annotations

from datetime import datetime, timezone

import pytest

from conftest import make_message
from gamedap_collector.normalize import (
    TITLE_MAX,
    classify_item_type,
    content_hash,
    normalize_message,
    normalize_messages,
)


class TestCrosspostWithEmbeds:
    @pytest.fixture
    def item(self, load_fixture, vampir):
        return normalize_message(load_fixture("crosspost_embeds"), vampir)

    def test_title_comes_from_embed(self, item):
        assert item.title == "Dev Notes #12: Guild War Rework"

    def test_body_combines_content_description_and_fields(self, item):
        assert item.body.startswith("New dev notes are up!")
        assert "We're reworking **Guild War**" in item.body
        assert "**Matchmaking**\nGuilds are now matched by power tier." in item.body
        assert "**Rewards**\nSeason rewards increased by 20%." in item.body
        # The embed title is the item title, so it is not repeated in the body.
        assert "Dev Notes #12" not in item.body

    def test_discord_timestamp_markup_is_rendered(self, item):
        assert "Season starts 2026-10-30 04:00 UTC." in item.body

    def test_url_prefers_embed_url(self, item):
        assert item.url == "https://vampir.example.com/news/dev-notes-12"

    def test_images_from_embed_and_image_attachments_only(self, item):
        assert item.image_urls == [
            "https://vampir.example.com/img/dev-notes-12-banner.jpg",
            "https://vampir.example.com/img/logo.png",
            "https://cdn.discordapp.com/attachments/1100000000000000001/1300000000000000901/"
            "guild_war_preview.png?ex=671f2a10&is=671dd890&hm=abc123",
        ]

    def test_origin_and_type_from_crosspost_author(self, item):
        assert item.origin == "VAMPIR Official Discord #dev-notes"
        assert item.item_type == "dev-notes"

    def test_metadata(self, item):
        assert item.game_id == "vampir"
        assert item.source == "discord"
        assert item.source_ref == "1300000000000000900"
        assert item.channel_id == "1564545494984818739"
        assert item.tier == "resmi"
        assert item.region == "Global"
        assert item.published_at == datetime(2026, 10, 27, 8, 0, 12, 345000, tzinfo=timezone.utc)
        assert item.raw["id"] == "1300000000000000900"


class TestForwardedSnapshot:
    @pytest.fixture
    def item(self, load_fixture, sxs, sxs_labels):
        return normalize_message(load_fixture("forwarded_snapshot"), sxs, sxs_labels)

    def test_body_from_snapshot_content(self, item):
        assert item.body.startswith("# Sword x Staff v1.4 Update")
        assert "New class **Spellblade** is here! :sxs_star:" in item.body
        assert "- New dungeon: Frost Hollow" in item.body

    def test_title_is_first_line_without_markdown(self, item):
        assert item.title == "Sword x Staff v1.4 Update"

    def test_url_from_text_without_trailing_punctuation(self, item):
        assert item.url == "https://sxs.example.com/news/v1-4"

    def test_image_attachment_detected_by_extension(self, item):
        assert len(item.image_urls) == 1
        assert "v14_key_art.webp" in item.image_urls[0]

    def test_origin_from_labels(self, item):
        assert item.origin == "Sword x Staff SEA #announcements"
        assert item.item_type == "announcements"

    def test_published_at_is_original_post_time(self, item):
        assert item.published_at == datetime(2026, 10, 26, 2, 0, tzinfo=timezone.utc)

    def test_source_ref_is_forward_message(self, item):
        assert item.source_ref == "1300000000000001900"
        assert item.tier == "resmi"

    def test_unknown_source_channel_falls_back(self, load_fixture, sxs):
        item = normalize_message(load_fixture("forwarded_snapshot"), sxs, {})
        assert item.origin == "Forwarded"
        # No origin channel, so keywords decide; nothing matches here.
        assert item.item_type == "other"


class TestPlainText:
    @pytest.fixture
    def item(self, load_fixture, vampir):
        return normalize_message(load_fixture("plain_text"), vampir)

    def test_mentions_are_stripped(self, item):
        assert "@here" not in item.body
        assert "@everyone" not in item.body
        assert "<@&" not in item.body

    def test_title_is_first_line(self, item):
        assert item.title == "Scheduled maintenance on 2026-10-31 01:00 UTC"

    def test_origin_is_author_and_type_from_keywords(self, item):
        assert item.origin == "Jack"
        assert item.item_type == "maintenance"

    def test_no_url_or_images(self, item):
        assert item.url is None
        assert item.image_urls == []


class TestItemTypeCode:
    def test_code_from_origin_label(self, load_fixture, sxs, sxs_labels):
        item = normalize_message(load_fixture("forwarded_code"), sxs, sxs_labels)
        assert item.origin == "Sword x Staff SEA #secret-code"
        assert item.item_type == "code"
        assert item.title == "🎁 SXSHALLOWEEN 🎁"

    @pytest.mark.parametrize(
        "content",
        [
            "Redeem code: VAMP2026",
            "New coupon for all players: NIGHT50",
            "Use this to redeem a free summon: XYZ123",
        ],
    )
    def test_code_from_keywords(self, vampir, content):
        item = normalize_message(make_message("1", content), vampir)
        assert item.item_type == "code"


class TestItemTypeMaintenance:
    def test_maintenance_from_origin_label(self):
        assert classify_item_type("SXS SEA #maintenance", "Notice", "Patch 1.4") == "maintenance"

    @pytest.mark.parametrize(
        "content",
        [
            "Emergency maintenance tonight",
            "Server down: we are investigating",
            "Planned downtime on Friday",
            "Servers are down in SEA",
        ],
    )
    def test_maintenance_from_keywords(self, vampir, content):
        item = normalize_message(make_message("1", content), vampir)
        assert item.item_type == "maintenance"


class TestItemTypePrecedence:
    def test_origin_label_beats_keywords(self):
        body = "After maintenance, redeem code SORRY for compensation."
        assert classify_item_type("VAMPIR Official Discord #dev-notes", "Notes", body) == "dev-notes"

    def test_title_keywords_beat_body_keywords(self):
        title = "Coupon code giveaway"
        body = "Available after maintenance ends."
        assert classify_item_type("Forwarded", title, body) == "code"

    @pytest.mark.parametrize(
        ("origin", "expected"),
        [
            ("VAMPIR Official Discord #announcements", "announcements"),
            ("VAMPIR Official Discord #contents", "contents"),
            ("VAMPIR Official Discord #ama", "ama"),
            ("VAMPIR Official Discord #dev-notes", "dev-notes"),
            ("Sword x Staff SEA #secret-code", "code"),
            ("VAMPIR Official Discord #general", "other"),
            ("Forwarded", "other"),
        ],
    )
    def test_origin_channel_mapping(self, origin, expected):
        assert classify_item_type(origin, "Hello", "Hello world") == expected


class TestSkipping:
    def test_system_messages_are_skipped(self, vampir):
        assert normalize_message(make_message("1", "pinned a message", type=6), vampir) is None

    def test_empty_messages_are_skipped(self, vampir):
        assert normalize_message(make_message("1", "@everyone"), vampir) is None

    def test_long_title_is_truncated(self, vampir):
        item = normalize_message(make_message("1", "A" * 300), vampir)
        assert len(item.title) == TITLE_MAX
        assert item.title.endswith("…")


class TestContentHash:
    def test_stable_across_runs(self, load_fixture, vampir):
        first = normalize_message(load_fixture("crosspost_embeds"), vampir)
        second = normalize_message(load_fixture("crosspost_embeds"), vampir)
        assert first.content_hash == second.content_hash
        assert len(first.content_hash) == 64

    def test_ignores_case_whitespace_and_mentions(self, vampir):
        a = normalize_message(make_message("1", "@everyone Patch  notes\n\nare UP"), vampir)
        b = normalize_message(make_message("2", "patch notes are up"), vampir)
        assert a.content_hash == b.content_hash

    def test_differs_per_game(self, vampir, sxs):
        a = normalize_message(make_message("1", "same text"), vampir)
        b = normalize_message(make_message("1", "same text"), sxs)
        assert a.content_hash != b.content_hash

    def test_image_only_hash_ignores_signed_query(self):
        url = "https://cdn.discordapp.com/attachments/1/2/a.png"
        assert content_hash("vampir", "", [url + "?ex=1&hm=a"]) == content_hash(
            "vampir", "", [url + "?ex=2&hm=b"]
        )

    def test_duplicates_in_a_batch_keep_first(self, vampir):
        items = normalize_messages(
            [make_message("1", "Same news"), make_message("2", "same   NEWS")], vampir
        )
        assert [i.source_ref for i in items] == ["1"]
