"""CLI entry point: python -m gamedap_collector.main [--dry-run] [--game ID]."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

from .config import DEFAULT_EXPORT_PATH, REPO_ROOT, ConfigError, Game, load_config
from .discord_client import DiscordClient, DiscordError, max_message_id
from .export import export_since, write_export
from .models import NewsItem
from .normalize import normalize_messages
from .store import StateStore, SupabaseStore

log = logging.getLogger("gamedap_collector")


@dataclass(frozen=True)
class GameResult:
    game: Game
    fetched: int
    items: list[NewsItem]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect game news from Discord into Supabase.")
    parser.add_argument("--dry-run", action="store_true", help="print normalized items, write nothing")
    parser.add_argument("--game", help="only collect this game id (e.g. vampir)")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser.parse_args(argv)


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx logs every request URL at INFO; keep it quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def collect_game(
    game: Game,
    discord: DiscordClient,
    store: StateStore | None,
    origin_labels: dict[str, str],
    *,
    dry_run: bool,
) -> GameResult:
    """Fetch, normalize and (unless dry-run) store one game's new messages."""
    channel_id = game.discord_channel_id
    after = store.get_last_message_id(channel_id) if store else None
    log.info("[%s] fetching channel %s after=%s", game.id, channel_id, after or "<latest 50>")

    messages = discord.fetch_new_messages(channel_id, after)
    items = normalize_messages(messages, game, origin_labels)
    log.info("[%s] %d messages -> %d items", game.id, len(messages), len(items))

    if not dry_run and store and messages:
        store.upsert_items(items)
        # Advance state only after the write succeeded.
        store.set_last_message_id(channel_id, max_message_id(messages))
    return GameResult(game=game, fetched=len(messages), items=items)


def run(args: argparse.Namespace) -> int:
    config = load_config()
    games = config.select_games(args.game)
    store = _open_store(dry_run=args.dry_run)
    failures = 0

    with DiscordClient(_require_env("DISCORD_BOT_TOKEN")) as discord:
        for game in games:
            try:
                result = collect_game(
                    game, discord, store, config.origin_labels, dry_run=args.dry_run
                )
            except DiscordError as exc:
                failures += 1
                log.error("[%s] Discord error: %s", game.id, exc)
                continue
            except Exception:  # noqa: BLE001 - keep other games running
                failures += 1
                log.exception("[%s] failed", game.id)
                continue
            if args.dry_run:
                _print_items(result.items)

    if not args.dry_run and isinstance(store, SupabaseStore):
        write_export(DEFAULT_EXPORT_PATH, store.fetch_recent(export_since()))
    return 1 if failures else 0


def _open_store(*, dry_run: bool) -> StateStore | None:
    """Real runs need Supabase. Dry runs use it read-only if configured."""
    try:
        return SupabaseStore.from_env()
    except ConfigError:
        if dry_run:
            log.info("Supabase not configured; dry run starts from the latest 50 messages")
            return None
        raise


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} must be set")
    return value


def _print_items(items: list[NewsItem]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    for item in items:
        print(json.dumps(item.to_public_dict(), ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)
    load_dotenv(REPO_ROOT / ".env")
    try:
        return run(args)
    except ConfigError as exc:
        log.error("Configuration error: %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
