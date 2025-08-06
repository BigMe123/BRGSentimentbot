# sentiment_bot/fetcher.py
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional, Iterable

import aiohttp
import feedparser
from bs4 import BeautifulSoup

from .config import settings


@dataclass
class ArticleData:
    """Holds URL, title, text, and optional published timestamp."""

    url: str
    title: str
    text: str
    published: Optional[str] = None


async def _fetch_and_parse_url(url: str) -> ArticleData:
    """
    Fetch a single URL and extract its main text.
    Prefer newspaper3k if available, else simple HTML <p> parse.
    """
    # Try newspaper3k
    try:
        from newspaper import Article  # type: ignore

        def _parse() -> ArticleData:
            art = Article(url)
            art.download()
            art.parse()
            return ArticleData(
                url=url,
                title=art.title or "",
                text=art.text or "",
                published=art.publish_date.isoformat() if art.publish_date else None,
            )

        return await asyncio.to_thread(_parse)
    except Exception:
        # Fallback to aiohttp + BeautifulSoup
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    html = await resp.text()
        except Exception as e:
            logging.warning(
                "Failed HTTP fetch, falling back to urllib for %s: %s", url, e
            )
            from urllib.error import URLError  # noqa: E402
            from urllib.request import urlopen  # noqa: E402
            import socket  # noqa: E402

            try:
                with urlopen(url, timeout=10) as resp:
                    html = resp.read().decode(errors="ignore")
            except (URLError, socket.timeout) as e_url:
                logging.warning("Failed urllib fetch for %s: %s", url, e_url)
                raise

        soup = BeautifulSoup(html, "html.parser")
        paras = soup.find_all("p")
        text = "\n\n".join(p.get_text() for p in paras)
        title_tag = soup.find("title")
        return ArticleData(
            url=url,
            title=title_tag.get_text() if title_tag else "",
            text=text,
            published=None,
        )


async def gather_rss(feeds: Iterable[str] | None = None) -> List[ArticleData]:
    """
    Parse each RSS/Atom feed URL in `feeds`, extract all <link> entries,
    dedupe by URL, then fetch & parse them concurrently.
    """
    feed_urls = list(feeds or settings.RSS_FEEDS)
    entries: List[str] = []
    for feed_url in feed_urls:
        parsed = await asyncio.to_thread(feedparser.parse, feed_url)
        for e in parsed.entries:
            link = e.get("link")
            if link:
                entries.append(link)

    # Deduplicate
    unique_links = list(dict.fromkeys(entries))  # preserve order

    # Concurrently fetch & parse
    sem = asyncio.Semaphore(10)
    results: List[ArticleData] = []

    async def _worker(link: str):
        async with sem:
            try:
                art = await _fetch_and_parse_url(link)
                results.append(art)
            except Exception:
                logging.exception("Failed to fetch or parse %s", link)

    await asyncio.gather(*[_worker(link) for link in unique_links])
    return results


async def gather_all_sources(feeds: Iterable[str] | None = None) -> List[ArticleData]:
    """
    Convenience wrapper for scheduler: pulls RSS feeds via `gather_rss()`.
    Later you can extend this to include NewsAPI or other sources.
    """
    return await gather_rss(feeds)
