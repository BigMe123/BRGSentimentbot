"""Wikipedia MediaWiki API connector with keyword fan-out."""

import asyncio
import aiohttp
from typing import AsyncIterator, Dict, Any, List, Optional
from .base import Connector
from ..ingest.utils import strip_html, make_id, parse_date, clean_text
import logging

logger = logging.getLogger(__name__)


class WikipediaConnector(Connector):
    """Fetch articles from Wikipedia with keyword fan-out."""

    name = "wikipedia"

    def __init__(
        self,
        queries: List[str] = None,
        max_per_query: int = 10,
        lang: str = "en",
        delay_ms: int = 200,
        **kwargs,
    ):
        """
        Initialize Wikipedia connector.

        Args:
            queries: Search queries for keyword fan-out
            max_per_query: Max articles per query
            lang: Wikipedia language code
            delay_ms: Delay between queries in milliseconds
        """
        super().__init__(**kwargs)
        self.queries = queries or [
            "cryptocurrency",
            "blockchain",
            "bitcoin",
            "ethereum",
        ]
        self.max_per_query = max_per_query
        self.lang = lang
        self.delay_ms = delay_ms
        self.base_url = f"https://{lang}.wikipedia.org/w/api.php"

    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """Fetch articles from Wikipedia - keyword fan-out."""

        headers = {"User-Agent": "BSGBOT/1.0 (+https://github.com/BigMe123/BSGBOT)"}

        async with aiohttp.ClientSession(
            headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            for query in self.queries:
                try:
                    async for item in self._search_articles(session, query):
                        yield item
                except Exception as e:
                    logger.error(f"Failed to fetch Wikipedia query '{query}': {e}")
                    continue

                # Rate limiting between queries
                if self.delay_ms > 0:
                    await asyncio.sleep(self.delay_ms / 1000.0)

    async def _search_articles(
        self, session: aiohttp.ClientSession, query: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Search for Wikipedia articles."""

        # First, search for articles
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": self.max_per_query,
            "format": "json",
            "utf8": 1,
        }

        logger.info(f"Searching Wikipedia for '{query}'")

        try:
            async with session.get(self.base_url, params=search_params) as resp:
                if resp.status != 200:
                    logger.warning(f"Wikipedia API returned {resp.status}")
                    return

                data = await resp.json()
                results = data.get("query", {}).get("search", [])

                if not results:
                    logger.warning(f"No Wikipedia articles found for '{query}'")
                    return

                # Fetch extract for each result
                count = 0
                for result in results:
                    try:
                        article = await self._fetch_article(session, result["title"])
                        if article:
                            article["subsource"] = query
                            yield article
                            count += 1
                    except Exception as e:
                        logger.warning(f"Failed to fetch Wikipedia article: {e}")
                        continue

                logger.info(f"Fetched {count} Wikipedia articles for '{query}'")

        except Exception as e:
            logger.error(f"Failed to search Wikipedia: {e}")

    async def _fetch_article(
        self, session: aiohttp.ClientSession, title: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch a Wikipedia article extract."""

        params = {
            "action": "query",
            "prop": "extracts|info|revisions",
            "titles": title,
            "exintro": True,  # Only intro
            "explaintext": True,  # Plain text
            "exsectionformat": "plain",
            "inprop": "url",
            "rvprop": "timestamp",
            "format": "json",
            "utf8": 1,
        }

        try:
            async with session.get(self.base_url, params=params) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json()
                pages = data.get("query", {}).get("pages", {})

                for page_id, page in pages.items():
                    if page_id == "-1":  # Page doesn't exist
                        continue

                    # Get revision timestamp
                    revisions = page.get("revisions", [{}])
                    timestamp = revisions[0].get("timestamp") if revisions else None

                    return {
                        "id": make_id(self.name, str(page_id)),
                        "source": self.name,
                        "subsource": None,  # Will be set by caller
                        "author": "Wikipedia",
                        "title": page.get("title"),
                        "text": clean_text(page.get("extract", "")),
                        "url": page.get(
                            "fullurl", f"https://{self.lang}.wikipedia.org/wiki/{title}"
                        ),
                        "published_at": parse_date(timestamp),
                        "lang": self.lang,
                        "raw": {"pageid": page_id, "title": title},
                    }

        except Exception as e:
            logger.error(f"Failed to fetch Wikipedia article '{title}': {e}")
            return None
