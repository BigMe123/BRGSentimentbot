"""Asynchronous utilities for fetching news articles."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable, List

try:  # pragma: no cover - optional dependency
    import feedparser
except Exception:  # pragma: no cover
    feedparser = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover
    class fuzz:  # type: ignore
        @staticmethod
        def token_set_ratio(a: str, b: str) -> int:
            return 100 if a == b else 0

from .config import settings


@dataclass
class ArticleData:
    url: str
    title: str
    text: str
    published: str | None = None


async def fetch_and_parse(url: str) -> ArticleData:
    """Fetch *url* and extract main text using newspaper3k if available."""

    try:  # pragma: no cover - optional dependency
        from newspaper import Article  # type: ignore

        def _parse() -> ArticleData:
            art = Article(url)
            art.download()
            art.parse()
            return ArticleData(
                url=url,
                title=art.title,
                text=art.text,
                published=art.publish_date.isoformat() if art.publish_date else None,
            )

        return await asyncio.to_thread(_parse)
    except Exception:
        try:
            import aiohttp  # type: ignore

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    text = await resp.text()
        except Exception:
            from urllib.request import urlopen

            with urlopen(url) as resp:  # type: ignore
                text = resp.read().decode()
        return ArticleData(url=url, title="", text=text, published=None)


async def gather_rss(feeds: Iterable[str] | None = None) -> List[ArticleData]:
    """Gather and deduplicate articles from RSS/Atom feeds."""

    feeds = list(feeds or settings.RSS_FEEDS)
    entries: list[tuple[str, str, str | None]] = []
    for feed_url in feeds:
        parser = getattr(feedparser, "parse", lambda u: type("obj", (), {"entries": []})())
        parsed = await asyncio.to_thread(parser, feed_url)
        for e in parsed.entries:
            url = e.get("link")
            title = e.get("title", "")
            published = e.get("published")
            if url and title:
                entries.append((url, title, published))

    unique: list[tuple[str, str, str | None]] = []
    seen_urls: set[str] = set()
    for url, title, published in entries:
        if url in seen_urls:
            continue
        if any(fuzz.token_set_ratio(title, u[1]) >= 95 for u in unique):
            continue
        seen_urls.add(url)
        unique.append((url, title, published))

    sem = asyncio.Semaphore(10)
    results: list[ArticleData] = []

    async def _worker(u: str, t: str, p: str | None) -> None:
        async with sem:
            try:
                art = await fetch_and_parse(u)
                art.title = t or art.title
                art.published = p
                results.append(art)
            except Exception:
                pass

    await asyncio.gather(*[_worker(u, t, p) for u, t, p in unique])
    return results


async def gather_newsapi() -> List[ArticleData]:  # pragma: no cover - network
    """Fetch top headlines using :mod:`newsapi` with a simple SQLite TTL cache."""

    from . import newsapi_client

    return await newsapi_client.fetch_top_headlines(settings.TOPICS)


async def gather_all_sources() -> List[ArticleData]:
    """Combine RSS feeds and NewsAPI articles."""

    rss, news = await asyncio.gather(gather_rss(), gather_newsapi())
    return rss + news
