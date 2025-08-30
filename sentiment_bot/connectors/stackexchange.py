"""StackExchange API connector with keyword fan-out."""

import asyncio
import aiohttp
from typing import AsyncIterator, Dict, Any, List
from .base import Connector
from ..ingest.utils import strip_html, make_id, parse_date, clean_text
import logging

logger = logging.getLogger(__name__)

API_BASE = "https://api.stackexchange.com/2.3"


class StackExchange(Connector):
    """Fetch questions from StackExchange sites with keyword fan-out and search."""

    name = "stackexchange"

    def __init__(
        self,
        sites: List[str] = None,
        tagged: List[str] = None,
        queries: List[str] = None,
        pages: int = 3,
        pagesize: int = 50,
        delay_ms: int = 200,
        **kwargs,
    ):
        """
        Initialize StackExchange connector.

        Args:
            sites: List of SE sites (e.g., ["stackoverflow", "politics"])
            tagged: Tags to filter by (legacy)
            queries: Search queries for keyword fan-out (preferred)
            pages: Number of pages to fetch per site/query
            pagesize: Items per page (max 100)
            delay_ms: Delay between requests in milliseconds
        """
        super().__init__(**kwargs)
        self.sites = sites or ["stackoverflow"]
        self.tagged = tagged or []
        self.queries = queries or []
        self.pages = min(pages, 10)
        self.pagesize = min(pagesize, 100)
        self.delay_ms = delay_ms

    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """Fetch questions from StackExchange - keyword fan-out or tagged mode."""

        headers = {"User-Agent": "BSGBOT/1.0 (+https://github.com/BigMe123/BSGBOT)"}

        async with aiohttp.ClientSession(
            headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            for site in self.sites:
                if self.queries:
                    # Keyword fan-out mode - one request per query per site
                    for query in self.queries:
                        try:
                            async for item in self._search_site(session, site, query):
                                yield item
                        except Exception as e:
                            logger.error(
                                f"Failed to search SE site {site} for '{query}': {e}"
                            )
                            continue

                        # Rate limiting between queries
                        if self.delay_ms > 0:
                            await asyncio.sleep(self.delay_ms / 1000.0)
                else:
                    # Tagged mode (legacy)
                    try:
                        async for item in self._fetch_site(session, site):
                            yield item
                    except Exception as e:
                        logger.error(f"Failed to fetch SE site {site}: {e}")
                        continue

                    # Rate limiting between sites
                    if self.delay_ms > 0:
                        await asyncio.sleep(self.delay_ms / 1000.0)

    async def _search_site(
        self, session: aiohttp.ClientSession, site: str, query: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Search for questions on a specific SE site."""

        context = f"{site}: {query}"
        logger.info(f"Searching StackExchange: {context}")

        for page in range(1, self.pages + 1):
            try:
                # Build search API URL
                params = {
                    "order": "desc",
                    "sort": "relevance",
                    "q": query,
                    "site": site,
                    "page": page,
                    "pagesize": self.pagesize,
                    "filter": "withbody",
                }

                url = f"{API_BASE}/search/advanced"

                async with session.get(url, params=params) as resp:
                    if resp.status == 429:
                        logger.warning(f"SE API rate limited for {context}")
                        await asyncio.sleep(2.0)
                        continue
                    elif resp.status != 200:
                        logger.warning(f"SE API returned {resp.status} for {context}")
                        break

                    data = await resp.json()

                    if data.get("error_id"):
                        logger.error(f"SE API error: {data.get('error_message')}")
                        break

                    items = data.get("items", [])
                    if not items:
                        logger.info(f"No more results for {context} at page {page}")
                        break

                    count = 0
                    for item in items:
                        try:
                            yield self._process_item(item, context)
                            count += 1
                        except Exception as e:
                            logger.warning(f"Failed to process SE item: {e}")
                            continue

                    logger.info(f"Fetched {count} items from {context} page {page}")

                    # Check if we have more pages
                    if not data.get("has_more"):
                        break

                    # Respect quota
                    if data.get("quota_remaining", 1) < 10:
                        logger.warning(
                            f"SE API quota low: {data.get('quota_remaining')}"
                        )
                        break

            except Exception as e:
                logger.error(f"Failed to fetch SE page {page} for {context}: {e}")
                break

            # Rate limiting between pages
            if self.delay_ms > 0 and page < self.pages:
                await asyncio.sleep(self.delay_ms / 1000.0)

    async def _fetch_site(
        self, session: aiohttp.ClientSession, site: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Fetch questions from a specific SE site (legacy tagged mode)."""

        logger.info(f"Fetching StackExchange: {site}")

        for page in range(1, self.pages + 1):
            try:
                # Build API URL
                params = {
                    "order": "desc",
                    "sort": "activity",
                    "site": site,
                    "page": page,
                    "pagesize": self.pagesize,
                    "filter": "withbody",  # Include question body
                }

                if self.tagged:
                    params["tagged"] = ";".join(self.tagged)

                url = (
                    f"{API_BASE}/search/advanced"
                    if self.tagged
                    else f"{API_BASE}/questions"
                )

                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        logger.warning(f"SE API returned {resp.status} for {site}")
                        continue

                    data = await resp.json()

                    if data.get("error_id"):
                        logger.error(f"SE API error: {data.get('error_message')}")
                        break

                    for item in data.get("items", []):
                        try:
                            yield self._process_item(item, site)
                        except Exception as e:
                            logger.warning(f"Failed to process SE item: {e}")
                            continue

                    # Check if we have more pages
                    if not data.get("has_more"):
                        break

                    # Respect quota
                    if data.get("quota_remaining", 1) < 10:
                        logger.warning(
                            f"SE API quota low: {data.get('quota_remaining')}"
                        )
                        break

            except Exception as e:
                logger.error(f"Failed to fetch SE page {page} for {site}: {e}")
                break

            # Rate limiting between pages
            if self.delay_ms > 0 and page < self.pages:
                await asyncio.sleep(self.delay_ms / 1000.0)

    def _process_item(self, item: dict, context: str) -> Dict[str, Any]:
        """Process a single StackExchange item."""

        # Build text from title and body
        text_parts = [item.get("title", "")]
        if item.get("body"):
            text_parts.append(strip_html(item["body"]))

        return {
            "id": make_id(self.name, context, str(item.get("question_id"))),
            "source": self.name,
            "subsource": context,
            "author": item.get("owner", {}).get("display_name"),
            "title": item.get("title"),
            "text": clean_text("\n\n".join(text_parts)),
            "url": item.get("link", ""),
            "published_at": parse_date(item.get("creation_date")),
            "lang": "en",
            "raw": item,
        }
