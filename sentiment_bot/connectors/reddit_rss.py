"""Reddit RSS connector with search support and keyword fan-out."""

import feedparser
import asyncio
import aiohttp
import urllib.parse
from typing import AsyncIterator, Dict, Any, List, Optional
from .base import Connector
from ..ingest.utils import strip_html, make_id, parse_date, clean_text
import logging

logger = logging.getLogger(__name__)


class RedditRSS(Connector):
    """Fetch posts from Reddit via RSS - supports both subreddits and search with keyword fan-out."""

    name = "reddit"

    def __init__(
        self,
        subreddits: List[str] = None,
        queries: List[str] = None,
        limit_per_sub: int = 200,
        sort: str = "new",
        time: str = "week",
        delay_ms: int = 300,
        **kwargs,
    ):
        """
        Initialize Reddit RSS connector.

        Args:
            subreddits: List of subreddit names (without r/)
            queries: Search queries (if present, overrides subreddit mode)
            limit_per_sub: Max posts per subreddit/query
            sort: Sort order (hot, new, top, rising)
            time: Time window for search mode (hour, day, week, month)
            delay_ms: Delay between requests in milliseconds
        """
        super().__init__(**kwargs)
        self.subreddits = subreddits or ["cryptocurrency", "bitcoin", "CryptoCurrency"]
        self.queries = queries or []
        self.limit_per_sub = limit_per_sub
        self.sort = sort if sort in ["hot", "new", "top", "rising"] else "new"
        self.time = (
            time if time in ["hour", "day", "week", "month", "year", "all"] else "week"
        )
        self.delay_ms = delay_ms

    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """Fetch posts from Reddit - keyword fan-out or subreddit mode."""

        headers = {"User-Agent": "BSGBOT/1.0 (+https://github.com/BigMe123/BSGBOT)"}

        async with aiohttp.ClientSession(
            headers=headers, timeout=aiohttp.ClientTimeout(total=20)
        ) as session:
            if self.queries:
                # Search mode - one request per query (keyword fan-out)
                for query in self.queries:
                    try:
                        async for item in self._fetch_search(session, query):
                            yield item
                    except Exception as e:
                        logger.error(f"Failed to search Reddit for '{query}': {e}")
                        continue

                    # Rate limiting between queries
                    if self.delay_ms > 0:
                        await asyncio.sleep(self.delay_ms / 1000.0)
            else:
                # Subreddit mode
                for subreddit in self.subreddits:
                    try:
                        async for item in self._fetch_subreddit(session, subreddit):
                            yield item
                    except Exception as e:
                        logger.error(f"Failed to fetch r/{subreddit}: {e}")
                        continue

                    # Rate limiting between subreddits
                    if self.delay_ms > 0:
                        await asyncio.sleep(self.delay_ms / 1000.0)

    async def _fetch_search(
        self, session: aiohttp.ClientSession, query: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Fetch posts from Reddit search for a specific query."""

        # Build search RSS URL with time window
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.reddit.com/search.rss?q={encoded_query}&sort={self.sort}&t={self.time}&restrict_sr=off"

        context = f"search: {query}"
        logger.info(f"Fetching Reddit RSS: {context}")

        try:
            async with session.get(url) as resp:
                if resp.status == 429:
                    logger.warning(f"Reddit rate limited (429) for {context}")
                    await asyncio.sleep(5.0)
                    return
                elif resp.status != 200:
                    logger.warning(f"Reddit returned {resp.status} for {context}")
                    return

                content = await resp.text()

            # Parse RSS feed
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
                if count >= self.limit_per_sub:
                    break

                try:
                    item = self._process_entry(entry, context)
                    if item:
                        yield item
                        count += 1
                except Exception as e:
                    logger.warning(f"Failed to process Reddit entry: {e}")
                    continue

            logger.info(f"Fetched {count} items from {context}")

        except Exception as e:
            logger.error(f"Failed to fetch Reddit RSS for {context}: {e}")

    async def _fetch_subreddit(
        self, session: aiohttp.ClientSession, subreddit: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Fetch posts from a specific subreddit."""

        # Build subreddit RSS URL
        if self.sort == "hot":
            url = f"https://www.reddit.com/r/{subreddit}/.rss"
        else:
            url = f"https://www.reddit.com/r/{subreddit}/{self.sort}/.rss"

        context = f"r/{subreddit}"
        logger.info(f"Fetching Reddit RSS: {context}")

        try:
            async with session.get(url) as resp:
                if resp.status == 429:
                    logger.warning(f"Reddit rate limited (429) for {context}")
                    await asyncio.sleep(5.0)
                    return
                elif resp.status != 200:
                    logger.warning(f"Reddit returned {resp.status} for {context}")
                    return

                content = await resp.text()

            # Parse RSS feed
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
                if count >= self.limit_per_sub:
                    break

                try:
                    item = self._process_entry(entry, context)
                    if item:
                        yield item
                        count += 1
                except Exception as e:
                    logger.warning(f"Failed to process Reddit entry: {e}")
                    continue

            logger.info(f"Fetched {count} items from {context}")

        except Exception as e:
            logger.error(f"Failed to fetch Reddit RSS for {context}: {e}")

    def _process_entry(self, entry: dict, context: str) -> Optional[Dict[str, Any]]:
        """Process a single RSS entry."""

        # Extract text from content
        text_parts = [entry.get("title", "")]

        # Get selftext or description
        if hasattr(entry, "content") and entry.content:
            content_html = entry.content[0].get("value", "")
            text_parts.append(strip_html(content_html))
        elif entry.get("summary"):
            text_parts.append(strip_html(entry.summary))

        # Extract author from entry
        author = entry.get("author")
        if author and author.startswith("/u/"):
            author = author[3:]  # Remove /u/ prefix

        return {
            "id": make_id(self.name, context, entry.get("id", entry.get("link", ""))),
            "source": self.name,
            "subsource": context,
            "author": author,
            "title": entry.get("title"),
            "text": clean_text("\n\n".join(text_parts)),
            "url": entry.get("link", ""),
            "published_at": parse_date(entry.get("published") or entry.get("updated")),
            "lang": "en",
            "raw": dict(entry) if hasattr(entry, "__dict__") else None,
        }
