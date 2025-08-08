"""Fetching utilities for RSS feeds and optional NewsAPI integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional

import aiohttp
import asyncio
import feedparser

from .config import (
    NEWSAPI_DOMAINS,
    NEWSAPI_KEY,
    load_rss_sources,
)


@dataclass
class Article:
    """Simple container for an article."""

    title: str
    url: str
    text: str
    published: Optional[datetime]
    source: str


async def _fetch_text(url: str, session: aiohttp.ClientSession) -> str:
    async with session.get(url, timeout=10) as resp:
        return await resp.text()


def _parse_rss(text: str, source: str) -> List[Article]:
    feed = feedparser.parse(text)
    arts: List[Article] = []
    for entry in feed.entries:
        published = None
        if getattr(entry, "published_parsed", None):
            try:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                published = None
        arts.append(
            Article(
                title=getattr(entry, "title", ""),
                url=getattr(entry, "link", ""),
                text=getattr(entry, "summary", ""),
                published=published,
                source=feed.feed.get("title", source),
            )
        )
    return arts


async def gather_rss(
    urls: Iterable[str],
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = 1000,
) -> List[Article]:
    """Fetch RSS feeds concurrently and return parsed articles."""

    urls = list(dict.fromkeys(urls))  # dedupe while preserving order
    articles: List[Article] = []

    async with aiohttp.ClientSession() as session:
        tasks = [_fetch_text(url, session) for url in urls]
        for coro in asyncio.as_completed(tasks):
            try:
                text = await coro
            except Exception:
                continue
            parsed = _parse_rss(text, "rss")
            for art in parsed:
                if since and art.published and art.published < since:
                    continue
                if until and art.published and art.published > until:
                    continue
                articles.append(art)
                if len(articles) >= limit:
                    return articles
    return articles


async def fetch_newsapi(
    query: str,
    since: Optional[datetime],
    until: Optional[datetime],
    limit: int,
) -> List[Article]:
    if not NEWSAPI_KEY or limit <= 0:
        return []

    params = {
        "q": query,
        "pageSize": str(limit),
        "apiKey": NEWSAPI_KEY,
    }
    if since:
        params["from"] = since.isoformat()
    if until:
        params["to"] = until.isoformat()
    if NEWSAPI_DOMAINS:
        params["domains"] = NEWSAPI_DOMAINS

    url = "https://newsapi.org/v2/everything"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params, timeout=10) as resp:
                data = await resp.json()
        except Exception:
            return []

    arts: List[Article] = []
    for entry in data.get("articles", []):
        published = None
        if entry.get("publishedAt"):
            try:
                published = datetime.fromisoformat(
                    entry["publishedAt"].replace("Z", "+00:00")
                )
            except Exception:
                published = None
        arts.append(
            Article(
                title=entry.get("title", ""),
                url=entry.get("url", ""),
                text=entry.get("description", ""),
                published=published,
                source=entry.get("source", {}).get("name", "newsapi"),
            )
        )
        if len(arts) >= limit:
            break
    return arts


async def fetch_all(
    since: Optional[datetime],
    until: Optional[datetime],
    limit: int,
    newsapi_query: Optional[str] = None,
) -> List[Article]:
    """Fetch articles from all configured sources."""

    sources = load_rss_sources()
    articles = await gather_rss(sources, since, until, limit)

    remaining = max(0, limit - len(articles))
    if newsapi_query and remaining > 0:
        articles.extend(await fetch_newsapi(newsapi_query, since, until, remaining))

    # Deduplicate by URL
    deduped: dict[str, Article] = {}
    for art in articles:
        key = art.url.strip().lower()
        if key not in deduped:
            deduped[key] = art
    return list(deduped.values())

