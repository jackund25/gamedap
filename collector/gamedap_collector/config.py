"""Load collector configuration from config.yaml."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

COLLECTOR_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = COLLECTOR_DIR.parent
DEFAULT_CONFIG_PATH = COLLECTOR_DIR / "config.yaml"
DEFAULT_EXPORT_PATH = REPO_ROOT / "exports" / "news-latest.json"

_PLACEHOLDER_RE = re.compile(r"^<.*>$")
_SNOWFLAKE_RE = re.compile(r"^\d{15,22}$")


class ConfigError(Exception):
    """Raised when configuration or required environment is invalid."""


@dataclass(frozen=True)
class Game:
    id: str
    name: str
    discord_channel_id: str


@dataclass(frozen=True)
class Config:
    games: list[Game]
    origin_labels: dict[str, str] = field(default_factory=dict)

    def select_games(self, game_id: str | None) -> list[Game]:
        if game_id is None:
            return list(self.games)
        selected = [g for g in self.games if g.id == game_id]
        if not selected:
            known = ", ".join(g.id for g in self.games)
            raise ConfigError(f"Unknown game '{game_id}'. Known games: {known}")
        return selected


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return Config(
        games=_parse_games(data.get("games") or []),
        origin_labels=parse_origin_labels(data.get("origin_labels") or {}),
    )


def _parse_games(raw_games: list[dict[str, Any]]) -> list[Game]:
    games: list[Game] = []
    for raw in raw_games:
        try:
            games.append(
                Game(
                    id=str(raw["id"]),
                    name=str(raw["name"]),
                    discord_channel_id=str(raw["discord_channel_id"]),
                )
            )
        except KeyError as exc:
            raise ConfigError(f"Game entry missing field {exc}: {raw!r}") from exc
    if not games:
        raise ConfigError("config.yaml defines no games")
    return games


def parse_origin_labels(raw: dict[Any, Any]) -> dict[str, str]:
    """Keep only entries keyed by a real channel id; skip placeholders."""
    labels: dict[str, str] = {}
    for key, label in raw.items():
        channel_id = str(key).strip()
        if _PLACEHOLDER_RE.match(channel_id):
            log.debug("Skipping placeholder origin label %s", channel_id)
            continue
        if not _SNOWFLAKE_RE.match(channel_id):
            log.warning("Ignoring origin label with invalid channel id %r", channel_id)
            continue
        labels[channel_id] = str(label)
    return labels
