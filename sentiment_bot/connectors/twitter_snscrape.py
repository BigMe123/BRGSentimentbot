"""Twitter/X connector using snscrape with keyword fan-out."""

import asyncio
import json
import subprocess
import sys
import importlib.util
from typing import AsyncIterator, Dict, Any, List
from .base import Connector
from ..ingest.utils import make_id, parse_date, clean_text
import logging

logger = logging.getLogger(__name__)


class TwitterSnscrape(Connector):
    """Fetch tweets using snscrape with keyword fan-out (no API key required)."""

    name = "twitter"

    def __init__(
        self,
        queries: List[str] = None,
        max_per_query: int = 400,
        delay_ms: int = 0,
        **kwargs,
    ):
        """
        Initialize Twitter connector.

        Args:
            queries: Search queries with optional 'since:' date filters
            max_per_query: Max tweets per query
            delay_ms: Delay between queries (usually 0 for snscrape)
        """
        super().__init__(**kwargs)
        self.queries = queries or [
            '"crypto" OR "blockchain" OR "bitcoin" OR "ethereum" since:2025-08-20'
        ]
        self.max_per_query = max_per_query
        self.delay_ms = delay_ms

    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """Fetch tweets using snscrape - one request per query (keyword fan-out)."""

        # Check if snscrape is available
        if not importlib.util.find_spec("snscrape"):
            logger.warning(
                "snscrape not installed; skipping Twitter connector. Install with: pip install snscrape"
            )
            return

        for query in self.queries:
            try:
                async for item in self._fetch_query(query):
                    yield item
            except Exception as e:
                logger.error(f"Failed to fetch Twitter query '{query}': {e}")
                continue

            # Rate limiting between queries (if configured)
            if self.delay_ms > 0:
                await asyncio.sleep(self.delay_ms / 1000.0)

    async def _fetch_query(self, query: str) -> AsyncIterator[Dict[str, Any]]:
        """Fetch tweets for a specific query using snscrape CLI."""

        logger.info(f"Fetching tweets via snscrape: '{query}'")

        # Build snscrape command
        cmd = [
            sys.executable,
            "-m",
            "snscrape",
            "--jsonl",
            "--max-results",
            str(self.max_per_query),
            "twitter-search",
            query,
        ]

        try:
            # Run snscrape CLI process
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                if stderr:
                    error_msg = stderr.decode("utf-8", errors="ignore")
                    logger.error(f"snscrape failed for '{query}': {error_msg}")
                else:
                    logger.error(
                        f"snscrape failed for '{query}' with return code {process.returncode}"
                    )
                return

            if not stdout:
                logger.warning(f"No tweets found for query: '{query}'")
                return

            # Parse JSONL output
            lines = stdout.decode("utf-8", errors="ignore").strip().split("\n")
            count = 0

            for line in lines:
                if not line.strip():
                    continue

                try:
                    tweet_data = json.loads(line)
                    item = self._process_tweet(tweet_data, query)
                    if item:
                        yield item
                        count += 1
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse tweet JSON: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Failed to process tweet: {e}")
                    continue

            logger.info(f"Fetched {count} tweets for '{query}'")

        except Exception as e:
            logger.error(f"Failed to run snscrape for '{query}': {e}")

    def _process_tweet(self, tweet_data: dict, query: str) -> Dict[str, Any]:
        """Process a single tweet from snscrape output."""

        # Extract user info
        user = tweet_data.get("user", {})
        username = (
            user.get("username")
            if isinstance(user, dict)
            else tweet_data.get("username")
        )

        # Get tweet content
        content = tweet_data.get("content", tweet_data.get("rawContent", ""))

        # Build URL
        tweet_id = str(tweet_data.get("id", ""))
        if username and tweet_id:
            url = f"https://twitter.com/{username}/status/{tweet_id}"
        else:
            url = tweet_data.get("url", "")

        return {
            "id": make_id(self.name, tweet_id or url),
            "source": self.name,
            "subsource": f"search: {query}",
            "author": username,
            "title": None,  # Tweets don't have titles
            "text": clean_text(content),
            "url": url,
            "published_at": parse_date(tweet_data.get("date")),
            "lang": tweet_data.get("lang", "en"),
            "raw": tweet_data,
        }
