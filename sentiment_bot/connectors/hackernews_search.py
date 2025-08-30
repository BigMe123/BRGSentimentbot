"""HackerNews search connector using Algolia API."""

import asyncio
import aiohttp
from typing import AsyncIterator, Dict, Any, List
from datetime import datetime, timezone
from .base import Connector
from ..ingest.utils import make_id, parse_date, clean_text
import logging

logger = logging.getLogger(__name__)


class HackerNewsSearch(Connector):
    """Search Hacker News stories using Algolia API with keyword matching."""

    name = "hackernews_search"

    def __init__(
        self,
        queries: List[str] = None,
        hits_per_page: int = 100,
        pages: int = 3,
        tags: str = "story",
        delay_ms: int = 100,
        **kwargs,
    ):
        """
        Initialize HackerNews search connector.

        Args:
            queries: Search queries (keywords)
            hits_per_page: Results per page (max 1000)
            pages: Number of pages to fetch per query
            tags: Filter by type ("story", "comment", "poll", "job", "show_hn", "ask_hn")
            delay_ms: Delay between requests in milliseconds
        """
        super().__init__(**kwargs)
        self.queries = queries or []
        self.hits_per_page = min(hits_per_page, 1000)  # Algolia max
        self.pages = pages
        self.tags = tags
        self.delay_ms = delay_ms

    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """Search HackerNews stories via Algolia API."""

        if not self.queries:
            logger.warning("No queries provided for HackerNews search")
            return

        headers = {"User-Agent": "BSGBOT/1.0 (+https://github.com/BigMe123/BSGBOT)"}

        async with aiohttp.ClientSession(
            headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            for query in self.queries:
                try:
                    async for item in self._search_query(session, query):
                        yield item
                except Exception as e:
                    logger.error(f"Failed to search HN for '{query}': {e}")
                    continue

                # Rate limiting between queries
                if self.delay_ms > 0:
                    await asyncio.sleep(self.delay_ms / 1000.0)

    async def _search_query(
        self, session: aiohttp.ClientSession, query: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Search for a specific query across multiple pages."""

        base_url = "https://hn.algolia.com/api/v1/search"

        for page in range(self.pages):
            try:
                params = {
                    "query": query,
                    "tags": self.tags,
                    "hitsPerPage": self.hits_per_page,
                    "page": page,
                }

                logger.info(
                    f"Searching HN Algolia: '{query}' page {page + 1}/{self.pages}"
                )

                async with session.get(base_url, params=params) as resp:
                    if resp.status == 429:
                        logger.warning(f"HN Algolia rate limited, waiting...")
                        await asyncio.sleep(2.0)
                        continue
                    elif resp.status != 200:
                        logger.warning(f"HN Algolia returned {resp.status}")
                        break

                    data = await resp.json()
                    hits = data.get("hits", [])

                    if not hits:
                        logger.info(f"No more results for '{query}' at page {page + 1}")
                        break

                    for hit in hits:
                        try:
                            yield self._process_hit(hit, query)
                        except Exception as e:
                            logger.warning(f"Failed to process HN search hit: {e}")
                            continue

                # Rate limiting between pages
                if self.delay_ms > 0 and page < self.pages - 1:
                    await asyncio.sleep(self.delay_ms / 1000.0)

            except Exception as e:
                logger.error(f"Failed to fetch page {page} for query '{query}': {e}")
                continue

    def _process_hit(self, hit: dict, query: str) -> Dict[str, Any]:
        """Process a single search hit from Algolia."""

        # Extract basic fields
        title = hit.get("title", "")
        story_text = hit.get("story_text", "")
        comment_text = hit.get("comment_text", "")
        url = hit.get("url", "")

        # Build text content
        text_parts = [title] if title else []
        if story_text:
            text_parts.append(story_text)
        if comment_text:
            text_parts.append(comment_text)

        # Determine final URL
        object_id = hit.get("objectID", "")
        if not url and object_id:
            url = f"https://news.ycombinator.com/item?id={object_id}"

        # Parse timestamp
        created_at = hit.get("created_at")
        published_at = None
        if created_at:
            try:
                # Algolia returns ISO format
                published_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except Exception:
                published_at = parse_date(created_at)

        return {
            "id": make_id(self.name, object_id or url or title),
            "source": self.name,
            "subsource": query,
            "author": hit.get("author"),
            "title": title,
            "text": clean_text("\n\n".join(text_parts)),
            "url": url,
            "published_at": published_at,
            "lang": "en",
            "raw": hit,
        }
