"""Bluesky API connector with keyword fan-out."""

import asyncio
import aiohttp
from typing import AsyncIterator, Dict, Any, List
from .base import Connector
from ..ingest.utils import strip_html, make_id, parse_date, clean_text
import logging

logger = logging.getLogger(__name__)


class BlueskyConnector(Connector):
    """Fetch posts from Bluesky with keyword fan-out."""

    name = "bluesky"

    def __init__(
        self,
        queries: List[str] = None,
        limit_per_query: int = 100,
        delay_ms: int = 1000,
        **kwargs,
    ):
        """
        Initialize Bluesky connector.

        Args:
            queries: Search queries for keyword fan-out
            limit_per_query: Max posts per query
            delay_ms: Delay between queries in milliseconds
        """
        super().__init__(**kwargs)
        self.queries = queries or ["crypto", "blockchain", "bitcoin", "ethereum"]
        self.limit_per_query = limit_per_query
        self.delay_ms = delay_ms

    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """Fetch posts from Bluesky - keyword fan-out."""

        headers = {"User-Agent": "BSGBOT/1.0 (+https://github.com/BigMe123/BSGBOT)"}

        async with aiohttp.ClientSession(
            headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            for query in self.queries:
                try:
                    async for item in self._search_posts(session, query):
                        yield item
                except Exception as e:
                    logger.error(f"Failed to fetch Bluesky query '{query}': {e}")
                    continue

                # Rate limiting between queries
                if self.delay_ms > 0:
                    await asyncio.sleep(self.delay_ms / 1000.0)

    async def _search_posts(
        self, session: aiohttp.ClientSession, query: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Search for posts on Bluesky."""

        # Public API endpoint (may change)
        url = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
        params = {"q": query, "limit": min(self.limit_per_query, 100)}

        logger.info(f"Fetching Bluesky posts for '{query}'")

        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"Bluesky API returned {resp.status}")
                    return

                data = await resp.json()
                posts = data.get("posts", [])

                if not posts:
                    logger.warning(f"No posts found for Bluesky query '{query}'")
                    return

                count = 0
                for post in posts[: self.limit_per_query]:
                    try:
                        # Extract post data
                        record = post.get("record", {})
                        author_data = post.get("author", {})

                        # Get text content
                        text = record.get("text", "")

                        # Build URL (approximate)
                        author_handle = author_data.get("handle", "unknown")
                        post_id = (
                            post.get("uri", "").split("/")[-1]
                            if post.get("uri")
                            else ""
                        )
                        url = f"https://bsky.app/profile/{author_handle}/post/{post_id}"

                        yield {
                            "id": make_id(self.name, post.get("uri", query)),
                            "source": self.name,
                            "subsource": query,
                            "author": author_data.get("displayName") or author_handle,
                            "title": text[:100] if text else None,
                            "text": clean_text(text),
                            "url": url,
                            "published_at": parse_date(record.get("createdAt")),
                            "lang": (
                                record.get("langs", ["en"])[0]
                                if record.get("langs")
                                else "en"
                            ),
                            "raw": post,
                        }
                        count += 1

                    except Exception as e:
                        logger.warning(f"Failed to process Bluesky post: {e}")
                        continue

                logger.info(f"Fetched {count} posts from Bluesky query '{query}'")

        except Exception as e:
            logger.error(f"Failed to search Bluesky for '{query}': {e}")
