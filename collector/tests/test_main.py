from __future__ import annotations

import pytest

from conftest import make_message
from gamedap_collector.main import collect_game


class FakeDiscord:
    def __init__(self, messages):
        self.messages = messages
        self.calls = []

    def fetch_new_messages(self, channel_id, after):
        self.calls.append((channel_id, after))
        return self.messages


class FakeStore:
    def __init__(self, last_id=None, fail_upsert=False):
        self.state = {} if last_id is None else {"1564545494984818739": last_id}
        self.fail_upsert = fail_upsert
        self.items = []

    def get_last_message_id(self, channel_id):
        return self.state.get(channel_id)

    def set_last_message_id(self, channel_id, message_id):
        self.state[channel_id] = message_id

    def upsert_items(self, items):
        if self.fail_upsert:
            raise RuntimeError("supabase down")
        self.items.extend(items)


def test_state_advances_to_newest_message_after_write(vampir):
    # Message 12 is a system message: skipped, but still advances the cursor.
    messages = [make_message("10", "a"), make_message("11", "b"), make_message("12", "", type=7)]
    discord, store = FakeDiscord(messages), FakeStore(last_id="9")

    result = collect_game(vampir, discord, store, {}, dry_run=False)

    assert discord.calls == [("1564545494984818739", "9")]
    assert len(result.items) == 2 and len(store.items) == 2
    assert store.state["1564545494984818739"] == "12"


def test_state_not_advanced_when_write_fails(vampir):
    store = FakeStore(last_id="9", fail_upsert=True)
    with pytest.raises(RuntimeError):
        collect_game(vampir, FakeDiscord([make_message("10", "a")]), store, {}, dry_run=False)
    assert store.state["1564545494984818739"] == "9"


def test_dry_run_writes_nothing(vampir):
    store = FakeStore(last_id="9")
    result = collect_game(vampir, FakeDiscord([make_message("10", "a")]), store, {}, dry_run=True)
    assert len(result.items) == 1
    assert store.items == [] and store.state["1564545494984818739"] == "9"


def test_dry_run_without_store_fetches_latest(vampir):
    discord = FakeDiscord([make_message("10", "a")])
    collect_game(vampir, discord, None, {}, dry_run=True)
    assert discord.calls == [("1564545494984818739", None)]
