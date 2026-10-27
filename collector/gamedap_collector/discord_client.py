"""Minimal Discord REST client for reading channel history."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import httpx

log = logging.getLogger(__name__)

API_BASE = "https://discord.com/api/v10"
PAGE_LIMIT = 100
FIRST_RUN_LIMIT = 50
USER_AGENT = "DiscordBot (https://github.com/jackund25/gamedap, 0.1)"

_STATUS_HINTS = {
    401: "invalid DISCORD_BOT_TOKEN",
    403: "bot lacks View Channel / Read Message History on this channel",
    404: "channel not found or bot is not in the server",
}


class DiscordError(Exception):
    """A Discord API request failed. Never includes the token."""


class DiscordClient:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = API_BASE,
        timeout: float = 15.0,
        max_retries: int = 5,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not token:
            raise DiscordError("DISCORD_BOT_TOKEN is empty")
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bot {token}", "User-Agent": USER_AGENT},
            timeout=timeout,
            transport=transport,
        )
        self._max_retries = max_retries
        self._sleep = sleep

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> DiscordClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch_new_messages(self, channel_id: str, after: str | None) -> list[dict[str, Any]]:
        """Messages newer than `after`, oldest first. Without `after`, the latest 50."""
        if after is None:
            return sort_by_id(self._get_messages(channel_id, {"limit": FIRST_RUN_LIMIT}))

        collected: list[dict[str, Any]] = []
        cursor = after
        while True:
            page = self._get_messages(channel_id, {"after": cursor, "limit": PAGE_LIMIT})
            collected.extend(page)
            if len(page) < PAGE_LIMIT:
                break
            cursor = max_message_id(page)
            log.debug("Channel %s: paging after %s", channel_id, cursor)
        return sort_by_id(collected)

    def _get_messages(self, channel_id: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        data = self._request("GET", f"/channels/{channel_id}/messages", params)
        if not isinstance(data, list):
            raise DiscordError(f"Unexpected response for channel {channel_id}: not a list")
        return data

    def _request(self, method: str, path: str, params: dict[str, Any]) -> Any:
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._http.request(method, path, params=params)
            except httpx.TransportError as exc:
                self._backoff(attempt, f"{type(exc).__name__} on {path}")
                continue

            if response.status_code == 429:
                delay = _retry_after(response)
                log.warning("Rate limited on %s; retrying in %.2fs", path, delay)
                self._sleep_or_fail(attempt, delay, f"rate limit on {path}")
                continue
            if response.status_code >= 500:
                self._backoff(attempt, f"HTTP {response.status_code} on {path}")
                continue
            if response.status_code >= 400:
                raise DiscordError(_describe_error(response, path))

            self._respect_bucket(response)
            return response.json()
        raise DiscordError(f"Giving up on {path} after {self._max_retries} attempts")

    def _backoff(self, attempt: int, reason: str) -> None:
        delay = min(2 ** (attempt - 1), 30)
        log.warning("%s (attempt %d/%d); retrying in %ds", reason, attempt, self._max_retries, delay)
        self._sleep_or_fail(attempt, delay, reason)

    def _sleep_or_fail(self, attempt: int, delay: float, reason: str) -> None:
        if attempt >= self._max_retries:
            raise DiscordError(f"Giving up after {attempt} attempts: {reason}")
        self._sleep(delay)

    def _respect_bucket(self, response: httpx.Response) -> None:
        """Pause before the next call if this rate-limit bucket is exhausted."""
        if response.headers.get("X-RateLimit-Remaining") == "0":
            delay = float(response.headers.get("X-RateLimit-Reset-After") or 1.0)
            log.info("Rate-limit bucket exhausted; waiting %.2fs", delay)
            self._sleep(delay)


def _retry_after(response: httpx.Response) -> float:
    try:
        return float(response.json().get("retry_after"))
    except (ValueError, TypeError, AttributeError):
        return float(response.headers.get("Retry-After") or 1.0)


def _describe_error(response: httpx.Response, path: str) -> str:
    try:
        detail = response.json().get("message", "")
    except ValueError:
        detail = response.text[:200]
    hint = _STATUS_HINTS.get(response.status_code)
    suffix = f" ({hint})" if hint else ""
    return f"Discord HTTP {response.status_code} on {path}: {detail}{suffix}"


def sort_by_id(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(messages, key=lambda m: int(m["id"]))


def max_message_id(messages: list[dict[str, Any]]) -> str:
    return str(max(int(m["id"]) for m in messages))
