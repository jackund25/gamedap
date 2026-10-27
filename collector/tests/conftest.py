from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from gamedap_collector.config import Game

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture() -> Callable[[str], dict[str, Any]]:
    def _load(name: str) -> dict[str, Any]:
        return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))

    return _load


@pytest.fixture
def vampir() -> Game:
    return Game(id="vampir", name="VAMPIR", discord_channel_id="1564545494984818739")


@pytest.fixture
def sxs() -> Game:
    return Game(id="sxs", name="Sword x Staff", discord_channel_id="1564545523011158127")


@pytest.fixture
def sxs_labels() -> dict[str, str]:
    return {
        "1200000000000000011": "Sword x Staff SEA #announcements",
        "1200000000000000022": "Sword x Staff SEA #secret-code",
    }


def make_message(message_id: str, content: str = "hello", **extra: Any) -> dict[str, Any]:
    message = {
        "id": message_id,
        "type": 0,
        "channel_id": "1564545494984818739",
        "content": content,
        "timestamp": "2026-10-27T08:00:00+00:00",
        "author": {"id": "1", "username": "someone", "global_name": None},
        "embeds": [],
        "attachments": [],
        "flags": 0,
    }
    message.update(copy.deepcopy(extra))
    return message
