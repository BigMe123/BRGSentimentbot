"""GDELT v2 events connector with keyword fan-out."""

import asyncio
import aiohttp
from typing import AsyncIterator, Dict, Any, List, Optional
from .base import Connector
from ..ingest.utils import strip_html, make_id, parse_date, clean_text
import logging

logger = logging.getLogger(__name__)


class GDELTConnector(Connector):
    """Fetch events from GDELT v2 with keyword fan-out."""

    name = "gdelt"

    def __init__(
        self,
        queries: List[str] = None,
        max_per_query: int = 250,
        mode: str = "artlist",
        delay_ms: int = 500,
        **kwargs,
    ):
        """
        Initialize GDELT connector.

        Args:
            queries: GDELT query strings for keyword fan-out (empty list for latest)
            max_per_query: Maximum items per query
            mode: "artlist" for articles, "timeline" for timeline
            delay_ms: Delay between queries in milliseconds
        """
        super().__init__(**kwargs)
        self.queries = queries or [""]
        self.max_per_query = max_per_query
        self.mode = mode
        self.delay_ms = delay_ms

    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """Fetch events from GDELT - keyword fan-out."""

        headers = {"User-Agent": "BSGBOT/1.0 (+https://github.com/BigMe123/BSGBOT)"}

        async with aiohttp.ClientSession(
            headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            for query in self.queries:
                try:
                    async for item in self._fetch_query(session, query):
                        yield item
                except Exception as e:
                    context = query if query else "latest"
                    logger.error(f"Failed to fetch GDELT query '{context}': {e}")
                    continue

                # Rate limiting between queries
                if self.delay_ms > 0:
                    await asyncio.sleep(self.delay_ms / 1000.0)

    async def _fetch_query(
        self, session: aiohttp.ClientSession, query: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Fetch GDELT events for a specific query."""

        # GDELT API endpoint
        url = "http://api.gdeltproject.org/api/v2/doc/doc"

        params = {
            "format": "json",
            "maxrecords": min(self.max_per_query, 250),  # GDELT limit
            "mode": self.mode,
        }

        if query:
            params["query"] = query

        context = query if query else "latest"
        logger.info(f"Fetching GDELT events: {context}")

        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"GDELT API returned {resp.status}")
                    return

                data = await resp.json()
                articles = data.get("articles", [])

                logger.info(f"Got {len(articles)} GDELT articles for '{context}'")

                count = 0
                for article in articles[: self.max_per_query]:
                    try:
                        # Extract text content
                        text_parts = []

                        if article.get("title"):
                            text_parts.append(article["title"])

                        # GDELT provides limited text, mainly title and sometimes snippet
                        if article.get("seendate"):
                            # Could fetch full article here if needed
                            pass

                        yield {
                            "id": make_id(self.name, context, article.get("url", "")),
                            "source": self.name,
                            "subsource": context,
                            "author": article.get("sourcecountry"),
                            "title": article.get("title"),
                            "text": clean_text("\n\n".join(text_parts)),
                            "url": article.get("url", ""),
                            "published_at": parse_date(article.get("seendate")),
                            "lang": article.get("language", "en").lower()[:2],
                            "raw": article,
                        }
                        count += 1

                    except Exception as e:
                        logger.warning(f"Failed to process GDELT article: {e}")
                        continue

                logger.info(f"Fetched {count} articles from GDELT query '{context}'")

        except Exception as e:
            logger.error(f"Failed to fetch GDELT events for '{context}': {e}")
