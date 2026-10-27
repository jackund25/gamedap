from __future__ import annotations

import pytest

from gamedap_collector.config import ConfigError, load_config, parse_origin_labels


def test_placeholder_origin_labels_are_skipped():
    labels = parse_origin_labels(
        {
            "<SXS_ANNOUNCEMENTS_CHANNEL_ID>": "Sword x Staff SEA #announcements",
            "1200000000000000022": "Sword x Staff SEA #secret-code",
            "not-a-channel": "ignored",
        }
    )
    assert labels == {"1200000000000000022": "Sword x Staff SEA #secret-code"}


def test_repo_config_loads():
    config = load_config()
    assert [g.id for g in config.games] == ["vampir", "sxs"]
    assert config.games[0].discord_channel_id == "1564545494984818739"


def test_select_unknown_game_raises():
    with pytest.raises(ConfigError, match="Unknown game"):
        load_config().select_games("nope")
