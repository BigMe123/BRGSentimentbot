"""Utilities for downloading and parsing news articles."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable, List

import aiohttp
import feedparser
from bs4 import BeautifulSoup
from rapidfuzz import fuzz


@dataclass
class FeedEntry:
    """Minimal representation of an RSS/Atom entry."""

    url: str
    title: str
    published: str | None = None


@dataclass
class ParsedArticle:
    """Text extracted from a fetched article."""

    url: str
    title: str
    text: str
    publish_dt: str | None = None


async def gather_feed_entries(feeds: Iterable[str]) -> List[FeedEntry]:
    """Fetch feeds and return unique entries.

    Deduplication is performed by exact URL match or title similarity of
    95% or greater using :mod:`rapidfuzz`.
    """

    entries: list[FeedEntry] = []
    for feed_url in feeds:
        parsed = await asyncio.to_thread(feedparser.parse, feed_url)
        for e in parsed.entries:
            url = e.get("link")
            title = e.get("title", "")
            published = e.get("published")
            if url and title:
                entries.append(FeedEntry(url=url, title=title, published=published))

    unique: list[FeedEntry] = []
    seen_urls: set[str] = set()
    for entry in entries:
        if entry.url in seen_urls:
            continue
        if any(fuzz.token_set_ratio(entry.title, u.title) >= 95 for u in unique):
            continue
        seen_urls.add(entry.url)
        unique.append(entry)
    return unique


async def download_and_parse(url: str) -> ParsedArticle:
    """Download article HTML and extract text.

    The real project would rely on :mod:`newspaper3k` for sophisticated
    extraction, but for the purposes of this repository we employ a very
    small BeautifulSoup based scraper.  The function is intentionally
    simple so tests can mock out HTTP responses.
    """

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=10) as resp:
            html = await resp.text()
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    return ParsedArticle(url=url, title="", text=text, publish_dt=None)
