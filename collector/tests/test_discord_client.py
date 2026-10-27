from __future__ import annotations

import httpx
import pytest

from gamedap_collector.discord_client import DiscordClient, DiscordError

TOKEN = "test-token-not-real"


def _ids(start: int, count: int) -> list[dict[str, str]]:
    # Discord returns pages newest first.
    return [{"id": str(i)} for i in range(start + count - 1, start - 1, -1)]


def _client(handler, sleeps: list[float] | None = None) -> DiscordClient:
    return DiscordClient(
        TOKEN,
        transport=httpx.MockTransport(handler),
        sleep=(sleeps.append if sleeps is not None else lambda _s: None),
        max_retries=3,
    )


def test_first_run_fetches_latest_50():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_ids(1, 50))

    messages = _client(handler).fetch_new_messages("123", after=None)

    assert len(seen) == 1
    assert seen[0].url.params["limit"] == "50"
    assert "after" not in seen[0].url.params
    assert seen[0].headers["Authorization"] == f"Bot {TOKEN}"
    assert [m["id"] for m in messages][:3] == ["1", "2", "3"]  # oldest first


def test_paginates_until_short_page():
    pages = {"1000": _ids(1001, 100), "1100": _ids(1101, 100), "1200": _ids(1201, 7)}
    afters: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        after = request.url.params["after"]
        afters.append(after)
        assert request.url.params["limit"] == "100"
        return httpx.Response(200, json=pages[after])

    messages = _client(handler).fetch_new_messages("123", after="1000")

    assert afters == ["1000", "1100", "1200"]
    assert len(messages) == 207
    assert messages[0]["id"] == "1001" and messages[-1]["id"] == "1207"


def test_retries_after_429_using_retry_after():
    calls = {"n": 0}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"message": "rate limited", "retry_after": 1.5, "global": False})
        return httpx.Response(200, json=[])

    assert _client(handler, sleeps).fetch_new_messages("123", after="5") == []
    assert calls["n"] == 2
    assert sleeps == [1.5]


def test_waits_when_bucket_exhausted():
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset-After": "0.75"}
        return httpx.Response(200, json=[], headers=headers)

    _client(handler, sleeps).fetch_new_messages("123", after="5")
    assert sleeps == [0.75]


def test_client_error_is_clear_and_never_contains_token():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Missing Access", "code": 50001})

    with pytest.raises(DiscordError) as excinfo:
        _client(handler).fetch_new_messages("123", after=None)

    message = str(excinfo.value)
    assert "403" in message and "Missing Access" in message
    assert TOKEN not in message


def test_gives_up_after_repeated_server_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    with pytest.raises(DiscordError, match="Giving up"):
        _client(handler).fetch_new_messages("123", after="5")


def test_retries_timeouts():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, json=[])

    assert _client(handler).fetch_new_messages("123", after="5") == []
    assert calls["n"] == 2
