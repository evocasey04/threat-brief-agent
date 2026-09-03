"""Fetch RSS/Atom feeds, normalise entries, and drop duplicates.

Feeds are fetched in parallel because a single slow or dead source shouldn't
hold up the morning run. Any feed that fails is logged and skipped — a partial
brief beats no brief.
"""

from __future__ import annotations

import concurrent.futures
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from html import unescape
from urllib.parse import urlparse, urlunparse

import feedparser
import requests

from .config import Feed

log = logging.getLogger(__name__)

USER_AGENT = "threat-brief-agent/1.0 (+https://github.com/topics/rss)"
FETCH_TIMEOUT = 20
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_TRACKING_PARAMS = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid")


@dataclass
class Item:
    """One normalised news story."""

    title: str
    link: str
    source: str
    category: str
    published: datetime
    summary: str = ""
    source_weight: float = 1.0
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    @property
    def age_hours(self) -> float:
        delta = datetime.now(UTC) - self.published
        return max(delta.total_seconds() / 3600.0, 0.0)


def clean_text(raw: str | None, limit: int = 400) -> str:
    """Strip HTML tags and collapse whitespace from a feed summary."""
    if not raw:
        return ""
    text = _WS_RE.sub(" ", unescape(_TAG_RE.sub(" ", raw))).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def canonical_url(url: str) -> str:
    """Normalise a URL for dedupe: drop tracking params, fragments, trailing slash."""
    if not url:
        return ""
    parsed = urlparse(url.strip())
    query = "&".join(
        part
        for part in parsed.query.split("&")
        if part and not part.lower().startswith(_TRACKING_PARAMS)
    )
    path = parsed.path.rstrip("/") or "/"
    netloc = parsed.netloc.lower().removeprefix("www.")
    return urlunparse((parsed.scheme.lower(), netloc, path, "", query, ""))


def title_key(title: str) -> str:
    """A loose fingerprint so the same story from two outlets collapses to one."""
    words = re.findall(r"[a-z0-9]+", title.lower())
    stop = {"the", "a", "an", "of", "in", "to", "for", "on", "and", "is", "as", "new"}
    keep = [w for w in words if w not in stop]
    return " ".join(keep[:8])


def _parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=UTC)
            except (TypeError, ValueError):
                continue
    return None


def fetch_feed(feed: Feed) -> list[Item]:
    """Fetch and normalise a single feed. Never raises.

    We fetch with `requests` rather than letting feedparser do it: feedparser's
    built-in fetcher has no timeout (a hang would stall the whole cron job) and
    some publishers — CISA among them — reject its default request, returning an
    error page that then fails to parse.
    """
    try:
        response = requests.get(
            feed.url,
            timeout=FETCH_TIMEOUT,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml, application/atom+xml, application/xml, */*",
            },
        )
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
    except Exception as exc:
        log.warning("%s: fetch failed (%s)", feed.name, exc)
        return []

    if getattr(parsed, "bozo", 0) and not parsed.entries:
        log.warning("%s: unparseable feed (%s)", feed.name, getattr(parsed, "bozo_exception", "?"))
        return []

    items: list[Item] = []
    for entry in parsed.entries:
        title = clean_text(getattr(entry, "title", ""), limit=200)
        link = getattr(entry, "link", "") or ""
        if not title or not link:
            continue

        published = _parse_date(entry)
        if published is None:
            # Undated entries are treated as "just now" so they still compete,
            # but the recency bonus can't be gamed beyond the current hour.
            published = datetime.now(UTC)

        items.append(
            Item(
                title=title,
                link=link,
                source=feed.name,
                category=feed.category,
                published=published,
                summary=clean_text(
                    getattr(entry, "summary", "") or getattr(entry, "description", "")
                ),
                source_weight=feed.weight,
            )
        )

    log.info("%s: %d entries", feed.name, len(items))
    return items


def fetch_all(feeds: list[Feed], max_workers: int = 8) -> list[Item]:
    """Fetch every feed concurrently and return the combined items."""
    if not feeds:
        return []

    items: list[Item] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        for result in pool.map(fetch_feed, feeds):
            items.extend(result)
    return items


def within_window(items: list[Item], hours: int) -> list[Item]:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    return [item for item in items if item.published >= cutoff]


def dedupe(items: list[Item]) -> list[Item]:
    """Collapse repeats by canonical URL, then by title fingerprint.

    The first occurrence wins, so callers should sort by preference (score or
    source weight) before deduping if they care which copy survives.
    """
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[Item] = []

    for item in items:
        url_key = canonical_url(item.link)
        t_key = title_key(item.title)
        if url_key and url_key in seen_urls:
            continue
        if t_key and t_key in seen_titles:
            continue
        seen_urls.add(url_key)
        if t_key:
            seen_titles.add(t_key)
        unique.append(item)

    return unique


def collect(feeds: list[Feed], hours: int) -> list[Item]:
    """Full ingest pipeline: fetch → window → dedupe."""
    items = fetch_all(feeds)
    log.info("fetched %d items from %d feeds", len(items), len(feeds))
    recent = within_window(items, hours)
    log.info("%d items within the last %dh", len(recent), hours)
    unique = dedupe(sorted(recent, key=lambda i: (-i.source_weight, i.published)))
    log.info("%d items after dedupe", len(unique))
    return unique
