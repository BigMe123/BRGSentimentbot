"""Hacker News API connector."""

import asyncio
import aiohttp
from typing import AsyncIterator, Dict, Any, Optional
from .base import Connector
from ..ingest.utils import strip_html, make_id, parse_date, clean_text
import logging

logger = logging.getLogger(__name__)

BASE_URL = "https://hacker-news.firebaseio.com/v0"


class HackerNews(Connector):
    """Fetch items from Hacker News via official Firebase API."""

    name = "hackernews"

    def __init__(
        self,
        categories: list = None,
        max_stories: int = 100,
        fetch_comments: bool = False,
        **kwargs,
    ):
        """
        Initialize Hacker News connector.

        Args:
            categories: List of categories ["top", "new", "best", "ask", "show", "job"]
            max_stories: Total number of items to fetch
            fetch_comments: Whether to include top comments in text
        """
        super().__init__(**kwargs)
        # Support both old and new param names for compatibility
        if categories:
            self.categories = [
                c
                for c in categories
                if c in {"top", "new", "best", "ask", "show", "job"}
            ]
        else:
            self.categories = ["top"]
        self.max_stories = min(max_stories, 500)  # HN limit
        self.fetch_comments = fetch_comments
        # For backward compatibility
        self.mode = self.categories[0] if self.categories else "top"
        self.top_n = self.max_stories

    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """Fetch items from Hacker News - category fan-out."""

        headers = {"User-Agent": "BSGBOT/1.0 (+https://github.com/BigMe123/BSGBOT)"}
        async with aiohttp.ClientSession(
            headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            items_fetched = 0

            for category in self.categories:
                if items_fetched >= self.max_stories:
                    break

                try:
                    # Get story IDs for this category
                    stories_url = f"{BASE_URL}/{category}stories.json"
                    async with session.get(stories_url) as resp:
                        if resp.status != 200:
                            logger.warning(
                                f"HN API returned {resp.status} for {category}"
                            )
                            continue
                        story_ids = await resp.json()

                    # Calculate how many to fetch from this category
                    remaining = self.max_stories - items_fetched
                    category_limit = min(len(story_ids) if story_ids else 0, remaining)
                    story_ids = story_ids[:category_limit] if story_ids else []

                    logger.info(f"Fetching {category_limit} items from HN {category}")

                    # Fetch each story
                    for story_id in story_ids:
                        if items_fetched >= self.max_stories:
                            break

                        try:
                            item = await self._fetch_item(session, story_id, category)
                            if item:
                                yield item
                                items_fetched += 1
                        except Exception as e:
                            logger.warning(f"Failed to fetch HN item {story_id}: {e}")
                            continue

                        # Rate limiting
                        await asyncio.sleep(0.1)

                except Exception as e:
                    logger.error(f"Failed to fetch HN {category} stories: {e}")
                    continue

            logger.info(
                f"Fetched total {items_fetched} items from HackerNews across all categories"
            )

    async def _fetch_item(
        self, session: aiohttp.ClientSession, item_id: int, category: str = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single HN item."""

        item_url = f"{BASE_URL}/item/{item_id}.json"

        async with session.get(item_url) as resp:
            if resp.status != 200:
                return None

            item = await resp.json()
            if not item or item.get("deleted") or item.get("dead"):
                return None

            # Build text content
            text_parts = []

            # Add title
            if item.get("title"):
                text_parts.append(item["title"])

            # Add text/description if present
            if item.get("text"):
                text_parts.append(strip_html(item["text"]))

            # Fetch top comments if requested
            if self.fetch_comments and item.get("kids"):
                comments = await self._fetch_top_comments(session, item["kids"][:3])
                if comments:
                    text_parts.append("\n\nTop Comments:\n" + "\n".join(comments))

            # Determine URL
            url = item.get("url") or f"https://news.ycombinator.com/item?id={item_id}"

            return {
                "id": make_id(self.name, str(item_id)),
                "source": self.name,
                "subsource": category or self.mode,
                "author": item.get("by"),
                "title": item.get("title"),
                "text": clean_text("\n\n".join(text_parts)),
                "url": url,
                "published_at": parse_date(item.get("time")),
                "lang": "en",
                "raw": item,
            }

    async def _fetch_top_comments(
        self, session: aiohttp.ClientSession, comment_ids: list
    ) -> list:
        """Fetch top-level comments."""

        comments = []
        for cid in comment_ids[:3]:  # Limit to top 3
            try:
                url = f"{BASE_URL}/item/{cid}.json"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        comment = await resp.json()
                        if comment and not comment.get("deleted"):
                            text = strip_html(comment.get("text", ""))
                            if text:
                                author = comment.get("by", "unknown")
                                comments.append(f"[{author}]: {text[:500]}")
            except Exception as e:
                logger.debug(f"Failed to fetch comment {cid}: {e}")
                continue

        return comments
