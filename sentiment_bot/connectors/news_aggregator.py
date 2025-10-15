"""
Multi-source news aggregator for comprehensive topic coverage.

This connector aggregates news from multiple sources:
- Google News RSS
- GDELT Project
- NewsAPI (if API key configured)
- Direct RSS feeds from major publications
"""

import asyncio
import aiohttp
import feedparser
import json
import logging
from typing import AsyncIterator, Dict, Any, List, Optional
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlencode
from .base import Connector
from ..ingest.utils import strip_html, make_id, parse_date, clean_text

logger = logging.getLogger(__name__)


class NewsAggregatorConnector(Connector):
    """
    Aggregate news from multiple sources for comprehensive coverage.

    Combines:
    - Google News RSS (free, no API key)
    - GDELT (free, no API key)
    - RSS feeds from major publications
    - Optional: NewsAPI (requires key)
    """

    name = "news_aggregator"

    def __init__(
        self,
        topic: str = "",
        queries: List[str] = None,
        max_results: int = 100,
        sources: List[str] = None,
        days_back: int = 7,
        newsapi_key: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize News Aggregator connector.

        Args:
            topic: Main topic to search for
            queries: Additional search queries
            max_results: Maximum total results across all sources
            sources: Specific news sources to prioritize
            days_back: How many days back to search
            newsapi_key: NewsAPI key (optional)
        """
        super().__init__(**kwargs)
        self.topic = topic
        self.queries = queries or self._generate_queries(topic)
        self.max_results = max_results
        self.days_back = days_back
        self.newsapi_key = newsapi_key

        # Major publication RSS feeds
        self.rss_feeds = {
            "reuters": "https://www.reutersagency.com/feed/",
            "bbc_world": "http://feeds.bbci.co.uk/news/world/rss.xml",
            "bbc_business": "http://feeds.bbci.co.uk/news/business/rss.xml",
            "aljazeera": "https://www.aljazeera.com/xml/rss/all.xml",
            "ap_world": "https://apnews.com/world-news",
        }

        # Kenyan sources
        self.kenyan_sources = {
            "daily_nation": "https://nation.africa/kenya/news/-/1056/latest/rss.xml",
            "business_daily": "https://www.businessdailyafrica.com/bd/feed",
            "standard": "https://www.standardmedia.co.ke/rss/",
            "star_kenya": "https://www.the-star.co.ke/feed",
        }

        if sources:
            self.sources = sources
        else:
            self.sources = list(self.rss_feeds.keys()) + list(self.kenyan_sources.keys())

    def _generate_queries(self, topic: str) -> List[str]:
        """Generate related search queries for better coverage."""
        base_queries = [topic]
        topic_lower = topic.lower()

        # Kenya/AGOA specific queries
        if "kenya" in topic_lower or "agoa" in topic_lower:
            base_queries.extend([
                "Kenya AGOA trade",
                "AGOA expiration Kenya",
                "Kenya US bilateral",
                "Kenya textile exports",
                "AGOA renewal",
                "Kenya tariffs AGOA"
            ])

        # Tariff queries
        if "tariff" in topic_lower:
            base_queries.extend([
                f"{topic} impact",
                f"{topic} trade"
            ])

        return base_queries[:10]

    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """Fetch news from multiple sources."""

        logger.info(f"Aggregating news for: {self.topic}")

        headers = {
            "User-Agent": "BSGBOT/1.0 (+https://github.com/BigMe123/BSGBOT)"
        }

        async with aiohttp.ClientSession(
            headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            results_count = 0

            # 1. Fetch from Google News RSS
            if results_count < self.max_results:
                async for item in self._fetch_google_news(session):
                    if results_count >= self.max_results:
                        break
                    yield item
                    results_count += 1

            # 2. Fetch from GDELT
            if results_count < self.max_results:
                async for item in self._fetch_gdelt(session):
                    if results_count >= self.max_results:
                        break
                    yield item
                    results_count += 1

            # 3. Fetch from RSS feeds
            if results_count < self.max_results:
                async for item in self._fetch_rss_feeds(session):
                    if results_count >= self.max_results:
                        break
                    yield item
                    results_count += 1

            # 4. Fetch from NewsAPI (if key provided)
            if self.newsapi_key and results_count < self.max_results:
                async for item in self._fetch_newsapi(session):
                    if results_count >= self.max_results:
                        break
                    yield item
                    results_count += 1

        logger.info(f"News aggregation complete: {results_count} articles fetched")

    async def _fetch_google_news(
        self, session: aiohttp.ClientSession
    ) -> AsyncIterator[Dict[str, Any]]:
        """Fetch from Google News RSS."""

        for query in self.queries[:7]:  # Use more queries for better coverage
            try:
                encoded_query = quote_plus(query)
                url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"

                async with session.get(url) as response:
                    if response.status != 200:
                        continue

                    content = await response.text()
                    feed = feedparser.parse(content)

                    for entry in feed.entries[:10]:  # Get 10 per query for more total articles
                        yield {
                            "id": make_id(entry.get("link", entry.get("id", ""))),
                            "source": "google_news",
                            "url": entry.get("link", ""),
                            "title": entry.get("title", ""),
                            "text": strip_html(entry.get("summary", "")),
                            "published_at": parse_date(entry.get("published", "")) or datetime.utcnow().isoformat(),
                            "metadata": {
                                "query": query,
                                "source_name": entry.get("source", {}).get("title", "Google News"),
                            }
                        }

                await asyncio.sleep(0.5)  # Rate limit

            except Exception as e:
                logger.error(f"Google News fetch failed for '{query}': {e}")

    async def _fetch_gdelt(
        self, session: aiohttp.ClientSession
    ) -> AsyncIterator[Dict[str, Any]]:
        """Fetch from GDELT Project."""

        try:
            # GDELT 2.0 API (free, no key required)
            for query in self.queries[:2]:
                url = "https://api.gdeltproject.org/api/v2/doc/doc"
                params = {
                    "query": query,
                    "mode": "artlist",
                    "maxrecords": 25,
                    "format": "json",
                    "sort": "datedesc"
                }

                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        continue

                    data = await response.json()

                    for article in data.get("articles", [])[:25]:
                        yield {
                            "id": make_id(article.get("url", "")),
                            "source": "gdelt",
                            "url": article.get("url", ""),
                            "title": article.get("title", ""),
                            "text": article.get("seendate", ""),  # GDELT provides limited text
                            "published_at": article.get("seendate", datetime.utcnow().isoformat()),
                            "metadata": {
                                "query": query,
                                "source_name": article.get("domain", "GDELT"),
                                "language": article.get("language", "en"),
                                "tone": article.get("tone", ""),
                            }
                        }

                await asyncio.sleep(1.0)  # Rate limit

        except Exception as e:
            logger.error(f"GDELT fetch failed: {e}")

    async def _fetch_rss_feeds(
        self, session: aiohttp.ClientSession
    ) -> AsyncIterator[Dict[str, Any]]:
        """Fetch from direct RSS feeds."""

        all_feeds = {**self.rss_feeds, **self.kenyan_sources}

        for source_name, feed_url in all_feeds.items():
            try:
                async with session.get(feed_url) as response:
                    if response.status != 200:
                        continue

                    content = await response.text()
                    feed = feedparser.parse(content)

                    for entry in feed.entries[:15]:  # Limit per feed
                        # Check if article is relevant to topic
                        title = entry.get("title", "").lower()
                        summary = entry.get("summary", "").lower()

                        if self.topic.lower() in title or self.topic.lower() in summary:
                            yield {
                                "id": make_id(entry.get("link", entry.get("id", ""))),
                                "source": f"rss_{source_name}",
                                "url": entry.get("link", ""),
                                "title": entry.get("title", ""),
                                "text": strip_html(entry.get("summary", entry.get("description", ""))),
                                "published_at": parse_date(entry.get("published", entry.get("pubDate", ""))) or datetime.utcnow().isoformat(),
                                "metadata": {
                                    "source_name": source_name,
                                    "feed_url": feed_url,
                                }
                            }

                await asyncio.sleep(0.3)  # Rate limit

            except Exception as e:
                logger.error(f"RSS fetch failed for {source_name}: {e}")

    async def _fetch_newsapi(
        self, session: aiohttp.ClientSession
    ) -> AsyncIterator[Dict[str, Any]]:
        """Fetch from NewsAPI (requires API key)."""

        if not self.newsapi_key:
            return

        try:
            from_date = (datetime.utcnow() - timedelta(days=self.days_back)).strftime("%Y-%m-%d")

            for query in self.queries[:2]:
                url = "https://newsapi.org/v2/everything"
                params = {
                    "q": query,
                    "from": from_date,
                    "sortBy": "publishedAt",
                    "language": "en",
                    "pageSize": 50,
                    "apiKey": self.newsapi_key
                }

                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        continue

                    data = await response.json()

                    for article in data.get("articles", []):
                        yield {
                            "id": make_id(article.get("url", "")),
                            "source": "newsapi",
                            "url": article.get("url", ""),
                            "title": article.get("title", ""),
                            "text": article.get("description", "") + " " + article.get("content", ""),
                            "published_at": article.get("publishedAt", datetime.utcnow().isoformat()),
                            "metadata": {
                                "query": query,
                                "source_name": article.get("source", {}).get("name", "NewsAPI"),
                                "author": article.get("author", ""),
                            }
                        }

                await asyncio.sleep(1.0)  # Rate limit

        except Exception as e:
            logger.error(f"NewsAPI fetch failed: {e}")


__all__ = ["NewsAggregatorConnector"]
