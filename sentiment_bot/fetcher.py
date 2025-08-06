from __future__ import annotations

import aiohttp
import asyncio
from dataclasses import dataclass
from typing import List

from bs4 import BeautifulSoup

feedparser = None  # placeholder for tests


@dataclass
class ArticleData:
    """Simple container for an article's URL and extracted text."""

    url: str
    title: str
    text: str


async def fetch_and_parse(urls: List[str] | str) -> List[ArticleData]:
    """Fetch URLs and parse article text."""

    if isinstance(urls, str):
        urls = [urls]
    articles: List[ArticleData] = []
    async with aiohttp.ClientSession() as sess:
        for url in urls:
            try:
                async with sess.get(url) as resp:
                    html = await resp.text()
                articles.append(ArticleData(url=url, title="", text=parse_article(html)))
            except Exception:
                continue
    return articles


def parse_article(html: str) -> str:
    """Extract main text from HTML."""

    soup = BeautifulSoup(html, "html.parser")
    paras = soup.find_all("p")
    return "\n\n".join(p.get_text() for p in paras)


async def gather_rss(urls: List[str]) -> List[ArticleData]:
    """Fetch RSS feeds concurrently and return parsed articles."""

    if feedparser is not None:
        entries = []
        for u in urls:
            parsed = feedparser.parse(u)
            entries.extend(parsed.entries)
        links = []
        seen = set()
        for e in entries:
            link = e.get("link")
            if link and link not in seen:
                seen.add(link)
                links.append(link)
        articles: List[ArticleData] = []
        for link in links:
            res = await fetch_and_parse(link)
            if isinstance(res, list):
                articles.extend(res)
            else:
                articles.append(res)
        return articles

    async with aiohttp.ClientSession() as sess:
        responses = await asyncio.gather(*[sess.get(u) for u in urls])
        bodies = [await r.text() for r in responses]
    links: List[str] = []
    for body in bodies:
        soup = BeautifulSoup(body, "xml")
        links.extend([l.text for l in soup.find_all("link")])
    return await fetch_and_parse(links)


async def gather_all_sources(urls: List[str] | None = None) -> List[ArticleData]:
    """Convenience wrapper used by the scheduler."""
    from .config import settings

    feeds = urls or settings.RSS_FEEDS
    return await gather_rss(list(feeds))
