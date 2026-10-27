"""Turn raw Discord message payloads into NewsItem records."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from .config import Game
from .models import NewsItem

TITLE_MAX = 140
TIER_OFFICIAL = "resmi"
DEFAULT_REGION = "Global"
FORWARD_FALLBACK_ORIGIN = "Forwarded"

# Discord message types that carry real posts (DEFAULT, REPLY).
_CONTENT_MESSAGE_TYPES = {0, 19}
_FLAG_IS_CROSSPOST = 1 << 1
_REFERENCE_TYPE_FORWARD = 1

_MENTION_RE = re.compile(r"(?:@everyone|@here|<@&\d+>)[ \t]*")
_CUSTOM_EMOJI_RE = re.compile(r"<a?:(\w+):\d+>")
_TIMESTAMP_RE = re.compile(r"<t:(-?\d+)(?::[tTdDfFR])?>")
_URL_RE = re.compile(r"https?://[^\s<>()\[\]\"']+")
_IMAGE_EXT_RE = re.compile(r"\.(png|jpe?g|gif|webp|avif)$", re.IGNORECASE)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((?:<)?https?://[^)]+\)")
_MD_LINE_PREFIX_RE = re.compile(r"^(?:#{1,6}\s+|>{1,3}\s+|[-*]\s+|-#\s+)+")
_MD_INLINE_RE = re.compile(r"\*\*|__|~~|\|\||`")

# item_type rules. Each list is checked in order; first match wins.
_ORIGIN_CHANNEL_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("code", re.compile(r"code|coupon|redeem")),
    ("maintenance", re.compile(r"maintenance|server-?status|downtime")),
    ("dev-notes", re.compile(r"dev-?notes?|developer-?notes?")),
    ("ama", re.compile(r"(?:^|[-_])ama(?:$|[-_])")),
    ("contents", re.compile(r"contents?")),
    ("announcements", re.compile(r"announce|news")),
]
_KEYWORD_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "maintenance",
        re.compile(r"\bmaintenance\b|\bservers?\s+(?:is\s+|are\s+)?down\b|\bdowntime\b", re.I),
    ),
    ("code", re.compile(r"\b(?:codes?|coupons?|redeem(?:ed|ing)?)\b", re.I)),
    ("dev-notes", re.compile(r"\bdev(?:eloper)?['’]?s?\s*notes?\b", re.I)),
    ("ama", re.compile(r"\bama\b|\bask\s+me\s+anything\b", re.I)),
]


def normalize_messages(
    messages: Iterable[dict[str, Any]],
    game: Game,
    origin_labels: dict[str, str] | None = None,
) -> list[NewsItem]:
    """Normalize messages, dropping skipped ones and duplicates (first wins)."""
    items: list[NewsItem] = []
    seen: set[str] = set()
    for message in messages:
        item = normalize_message(message, game, origin_labels)
        if item is None or item.content_hash in seen:
            continue
        seen.add(item.content_hash)
        items.append(item)
    return items


def normalize_message(
    message: dict[str, Any],
    game: Game,
    origin_labels: dict[str, str] | None = None,
) -> NewsItem | None:
    """Return a NewsItem, or None for system/empty messages."""
    if message.get("type", 0) not in _CONTENT_MESSAGE_TYPES:
        return None

    parts = _message_parts(message)
    title_embed = _first_titled_embed(parts)
    body = build_body(parts, skip_title_of=title_embed)
    image_urls = collect_image_urls(parts)
    if not body and not image_urls:
        return None

    origin = resolve_origin(message, origin_labels or {})
    title = build_title(title_embed, body) or origin
    return NewsItem(
        game_id=game.id,
        source_ref=str(message["id"]),
        channel_id=str(message.get("channel_id") or game.discord_channel_id),
        origin=origin,
        item_type=classify_item_type(origin, title, body),
        title=title,
        body=body,
        url=find_url(parts, body),
        image_urls=image_urls,
        published_at=published_at(message),
        tier=TIER_OFFICIAL,
        region=DEFAULT_REGION,
        content_hash=content_hash(game.id, body, image_urls),
        raw=message,
    )


# --- message structure -------------------------------------------------------


def _message_parts(message: dict[str, Any]) -> list[dict[str, Any]]:
    """The message itself followed by any forwarded snapshot messages."""
    parts = [message]
    for snapshot in message.get("message_snapshots") or []:
        inner = snapshot.get("message")
        if isinstance(inner, dict):
            parts.append(inner)
    return parts


def _embeds(parts: list[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for part in parts:
        yield from part.get("embeds") or []


def _first_titled_embed(parts: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((e for e in _embeds(parts) if (e.get("title") or "").strip()), None)


def is_crosspost(message: dict[str, Any]) -> bool:
    return bool(int(message.get("flags") or 0) & _FLAG_IS_CROSSPOST) or bool(
        message.get("webhook_id")
    )


def is_forward(message: dict[str, Any]) -> bool:
    reference = message.get("message_reference") or {}
    return reference.get("type") == _REFERENCE_TYPE_FORWARD or bool(
        message.get("message_snapshots")
    )


# --- text --------------------------------------------------------------------


def clean_text(text: str) -> str:
    """Strip mass/role mentions and render Discord markup as plain markdown."""
    text = _MENTION_RE.sub("", text)
    text = _CUSTOM_EMOJI_RE.sub(r":\1:", text)
    text = _TIMESTAMP_RE.sub(_format_discord_timestamp, text)
    return tidy_whitespace(text)


def tidy_whitespace(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _format_discord_timestamp(match: re.Match[str]) -> str:
    moment = datetime.fromtimestamp(int(match.group(1)), tz=timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M UTC")


def build_body(parts: list[dict[str, Any]], skip_title_of: dict[str, Any] | None) -> str:
    blocks: list[str] = []
    for part in parts:
        blocks.append(part.get("content") or "")
        for embed in part.get("embeds") or []:
            blocks.extend(_embed_blocks(embed, include_title=embed is not skip_title_of))
    return clean_text("\n\n".join(b.strip() for b in blocks if b and b.strip()))


def _embed_blocks(embed: dict[str, Any], include_title: bool) -> list[str]:
    blocks: list[str] = []
    title = (embed.get("title") or "").strip()
    if include_title and title:
        blocks.append(f"**{title}**")
    if embed.get("description"):
        blocks.append(embed["description"])
    for field in embed.get("fields") or []:
        name = (field.get("name") or "").strip()
        value = (field.get("value") or "").strip()
        if name and value:
            blocks.append(f"**{name}**\n{value}")
        elif name or value:
            blocks.append(name or value)
    return blocks


def build_title(title_embed: dict[str, Any] | None, body: str) -> str:
    if title_embed is not None:
        candidate = clean_text(title_embed["title"])
    else:
        candidate = next((line for line in body.split("\n") if line.strip()), "")
    return truncate(strip_inline_markdown(candidate), TITLE_MAX)


def strip_inline_markdown(text: str) -> str:
    text = _MD_LINK_RE.sub(r"\1", text.strip())
    text = _MD_LINE_PREFIX_RE.sub("", text)
    return _MD_INLINE_RE.sub("", text).strip()


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


# --- links and images --------------------------------------------------------


def find_url(parts: list[dict[str, Any]], body: str) -> str | None:
    for embed in _embeds(parts):
        url = embed.get("url") or ""
        if url.startswith(("http://", "https://")):
            return url
    match = _URL_RE.search(body)
    return match.group(0).rstrip(".,!?;:*_~") if match else None


def collect_image_urls(parts: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for part in parts:
        for embed in part.get("embeds") or []:
            for key in ("image", "thumbnail"):
                url = (embed.get(key) or {}).get("url")
                if url:
                    urls.append(url)
        for attachment in part.get("attachments") or []:
            if _is_image_attachment(attachment):
                urls.append(attachment["url"])
    return list(dict.fromkeys(urls))


def _is_image_attachment(attachment: dict[str, Any]) -> bool:
    if not attachment.get("url"):
        return False
    content_type = attachment.get("content_type") or ""
    if content_type.startswith("image/"):
        return True
    return bool(_IMAGE_EXT_RE.search(attachment.get("filename") or ""))


# --- origin and type ---------------------------------------------------------


def resolve_origin(message: dict[str, Any], origin_labels: dict[str, str]) -> str:
    author = message.get("author") or {}
    if is_crosspost(message):
        return author.get("username") or FORWARD_FALLBACK_ORIGIN
    if is_forward(message):
        source_channel = str((message.get("message_reference") or {}).get("channel_id") or "")
        return origin_labels.get(source_channel, FORWARD_FALLBACK_ORIGIN)
    return author.get("global_name") or author.get("username") or "Discord"


def classify_item_type(origin: str, title: str, body: str) -> str:
    """Origin channel name wins; then keywords in the title, then the body."""
    channel = _origin_channel(origin)
    if channel:
        for item_type, pattern in _ORIGIN_CHANNEL_RULES:
            if pattern.search(channel):
                return item_type
    for text in (title, body):
        for item_type, pattern in _KEYWORD_RULES:
            if pattern.search(text):
                return item_type
    return "other"


def _origin_channel(origin: str) -> str:
    """'VAMPIR Official Discord #dev-notes' -> 'dev-notes'."""
    if "#" not in origin:
        return ""
    return origin.rsplit("#", 1)[1].strip().lower()


# --- identity and time -------------------------------------------------------


def content_hash(game_id: str, body: str, image_urls: list[str]) -> str:
    """Stable hash of game + normalized body (image paths if there is no text)."""
    basis = " ".join(body.lower().split())
    if not basis:
        # Discord CDN query strings are signed and expire, so hash paths only.
        basis = " ".join(url.split("?", 1)[0] for url in image_urls)
    return hashlib.sha256(f"{game_id}\n{basis}".encode("utf-8")).hexdigest()


def published_at(message: dict[str, Any]) -> datetime:
    """Original post time for forwards, otherwise the message timestamp (UTC)."""
    timestamp = message["timestamp"]
    for snapshot in message.get("message_snapshots") or []:
        inner_ts = (snapshot.get("message") or {}).get("timestamp")
        if inner_ts:
            timestamp = inner_ts
            break
    return parse_timestamp(timestamp)


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
