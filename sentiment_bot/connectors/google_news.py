"""Google News RSS connector with keyword fan-out."""

import asyncio
import aiohttp
import feedparser
from urllib.parse import quote_plus
from typing import AsyncIterator, Dict, Any, List
from .base import Connector
from ..ingest.utils import strip_html, make_id, parse_date, clean_text
import logging

logger = logging.getLogger(__name__)


class GoogleNewsRSS(Connector):
    """Fetch news from Google News RSS feeds with keyword fan-out."""

    name = "google_news"

    def __init__(
        self,
        queries: List[str] = None,
        editions: List[str] = None,
        per_query_cap: int = 200,
        delay_ms: int = 300,
        **kwargs,
    ):
        """
        Initialize Google News connector.

        Args:
            queries: Search queries for keyword fan-out
            editions: Country/language editions (e.g., ["en-US", "en-GB"])
            per_query_cap: Maximum items per query per edition
            delay_ms: Delay between requests in milliseconds
        """
        super().__init__(**kwargs)
        self.queries = queries or ["(crypto OR blockchain OR bitcoin OR ethereum)"]
        self.editions = editions or ["en-US", "en-GB", "en-CA", "en-AU"]
        self.per_query_cap = per_query_cap
        self.delay_ms = delay_ms

    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """Fetch news from Google News RSS - keyword fan-out across editions."""

        headers = {"User-Agent": "BSGBOT/1.0 (+https://github.com/BigMe123/BSGBOT)"}

        async with aiohttp.ClientSession(
            headers=headers, timeout=aiohttp.ClientTimeout(total=20)
        ) as session:
            for query in self.queries:
                for edition in self.editions:
                    try:
                        async for item in self._fetch_query_edition(
                            session, query, edition
                        ):
                            yield item
                    except Exception as e:
                        logger.error(
                            f"Failed to fetch Google News for '{query}' ({edition}): {e}"
                        )
                        continue

                    # Rate limiting between edition requests
                    if self.delay_ms > 0:
                        await asyncio.sleep(self.delay_ms / 1000.0)

    async def _fetch_query_edition(
        self, session: aiohttp.ClientSession, query: str, edition: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Fetch items for a specific query and edition combination."""

        # Parse edition
        if "-" in edition:
            lang, country = edition.split("-", 1)
        else:
            lang, country = edition, "US"

        # Build RSS URL
        encoded_query = quote_plus(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl={lang}&gl={country}&ceid={country}:{lang}"

        context = f"{edition}: {query}"
        logger.info(f"Fetching Google News RSS: {context}")

        try:
            # Fetch RSS content
            async with session.get(url) as resp:
                if resp.status == 429:
                    logger.warning(f"Google News rate limited (429) for {context}")
                    await asyncio.sleep(2.0)
                    return
                elif resp.status != 200:
                    logger.warning(f"Google News returned {resp.status} for {context}")
                    return

                content = await resp.text()

            # Parse RSS feed (sync operation)
            feed = feedparser.parse(content)

            if feed.bozo:
                logger.warning(
                    f"Feed parsing issue for {context}: {feed.bozo_exception}"
                )

            if not feed.entries:
                logger.warning(f"No entries found for {context}")
                return

            count = 0
            for entry in feed.entries:
                if count >= self.per_query_cap:
                    break

                try:
                    # Extract data
                    item_id = (
                        entry.get("id") or entry.get("guid") or entry.get("link", "")
                    )

                    # Google News often has publisher in title after " - "
                    title = entry.get("title", "")
                    publisher = None
                    if " - " in title:
                        parts = title.rsplit(" - ", 1)
                        if len(parts) == 2:
                            title, publisher = parts

                    yield {
                        "id": make_id(self.name, query, edition, item_id),
                        "source": self.name,
                        "subsource": context,
                        "author": publisher or entry.get("author"),
                        "title": title,
                        "text": clean_text(strip_html(entry.get("summary", ""))),
                        "url": entry.get("link", ""),
                        "published_at": parse_date(
                            entry.get("published") or entry.get("updated")
                        ),
                        "lang": lang,
                        "raw": dict(entry) if hasattr(entry, "__dict__") else None,
                    }
                    count += 1

                except Exception as e:
                    logger.warning(f"Failed to process Google News entry: {e}")
                    continue

            logger.info(f"Fetched {count} items from {context}")

        except Exception as e:
            logger.error(f"Failed to parse Google News feed for {context}: {e}")
