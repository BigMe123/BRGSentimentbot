"""Mastodon API connector with keyword fan-out."""

import asyncio
import aiohttp
from typing import AsyncIterator, Dict, Any, List, Optional
from .base import Connector
from ..ingest.utils import strip_html, make_id, parse_date, clean_text
import logging

logger = logging.getLogger(__name__)


class MastodonConnector(Connector):
    """Fetch posts from Mastodon instances with hashtag fan-out."""

    name = "mastodon"

    def __init__(
        self,
        instance: str = "mastodon.social",
        hashtags: List[str] = None,
        limit_per_tag: int = 100,
        local: bool = False,
        delay_ms: int = 500,
        **kwargs,
    ):
        """
        Initialize Mastodon connector.

        Args:
            instance: Mastodon instance domain
            hashtags: Hashtags to follow (fan-out)
            limit_per_tag: Max posts per hashtag
            local: Whether to fetch only local posts
            delay_ms: Delay between hashtag requests in milliseconds
        """
        super().__init__(**kwargs)
        self.instance = instance
        self.hashtags = hashtags or ["crypto", "blockchain", "bitcoin", "ethereum"]
        self.limit_per_tag = limit_per_tag
        self.local = local
        self.delay_ms = delay_ms

    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """Fetch posts from Mastodon - hashtag fan-out."""

        headers = {"User-Agent": "BSGBOT/1.0 (+https://github.com/BigMe123/BSGBOT)"}

        async with aiohttp.ClientSession(
            headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            # Fetch from public timeline if no hashtags
            if not self.hashtags:
                async for item in self._fetch_timeline(session, "public"):
                    yield item
            else:
                # Hashtag fan-out - one request per hashtag
                for hashtag in self.hashtags:
                    try:
                        async for item in self._fetch_hashtag(session, hashtag):
                            yield item
                    except Exception as e:
                        logger.error(f"Failed to fetch Mastodon #{hashtag}: {e}")
                        continue

                    # Rate limiting between hashtags
                    if self.delay_ms > 0:
                        await asyncio.sleep(self.delay_ms / 1000.0)

    async def _fetch_hashtag(
        self, session: aiohttp.ClientSession, hashtag: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Fetch posts for a specific hashtag."""

        hashtag = hashtag.lstrip("#")
        url = f"https://{self.instance}/api/v1/timelines/tag/{hashtag}"

        params = {
            "limit": min(self.limit_per_tag, 40),  # Mastodon max per request
            "local": str(self.local).lower(),
        }

        logger.info(f"Fetching Mastodon #{hashtag} from {self.instance}")

        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"Mastodon API returned {resp.status}")
                    return

                posts = await resp.json()

                count = 0
                for post in posts[: self.limit_per_tag]:
                    try:
                        yield self._process_post(post, hashtag)
                        count += 1
                    except Exception as e:
                        logger.warning(f"Failed to process Mastodon post: {e}")
                        continue

                logger.info(f"Fetched {count} posts from #{hashtag} on {self.instance}")

        except Exception as e:
            logger.error(f"Failed to fetch Mastodon timeline: {e}")

    async def _fetch_timeline(
        self, session: aiohttp.ClientSession, timeline: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Fetch from public timeline."""

        url = f"https://{self.instance}/api/v1/timelines/{timeline}"
        params = {
            "limit": min(self.limit_per_tag, 40),
            "local": str(self.local).lower(),
        }

        logger.info(f"Fetching Mastodon {timeline} timeline from {self.instance}")

        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return

                posts = await resp.json()

                count = 0
                for post in posts[: self.limit_per_tag]:
                    try:
                        yield self._process_post(post, timeline)
                        count += 1
                    except Exception as e:
                        logger.warning(f"Failed to process post: {e}")
                        continue

                logger.info(
                    f"Fetched {count} posts from {timeline} timeline on {self.instance}"
                )

        except Exception as e:
            logger.error(f"Failed to fetch timeline: {e}")

    def _process_post(self, post: dict, subsource: str) -> Dict[str, Any]:
        """Process a Mastodon post."""

        # Extract text content
        text = strip_html(post.get("content", ""))

        # Add spoiler text if present
        if post.get("spoiler_text"):
            text = f"{post['spoiler_text']}\n\n{text}"

        # Extract author info
        account = post.get("account", {})
        author = account.get("display_name") or account.get("username")

        return {
            "id": make_id(self.name, self.instance, str(post.get("id"))),
            "source": self.name,
            "subsource": f"{self.instance}/#{subsource}",
            "author": author,
            "title": post.get("spoiler_text") or text[:100],
            "text": clean_text(text),
            "url": post.get("url") or post.get("uri", ""),
            "published_at": parse_date(post.get("created_at")),
            "lang": post.get("language"),
            "raw": post,
        }
