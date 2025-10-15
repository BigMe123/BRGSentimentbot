"""Web Search connector using multiple search APIs for live data fetching."""

import asyncio
import aiohttp
import json
import logging
from typing import AsyncIterator, Dict, Any, List, Optional
from datetime import datetime
from .base import Connector
from ..ingest.utils import strip_html, make_id, clean_text

logger = logging.getLogger(__name__)


class WebSearchConnector(Connector):
    """
    Fetch live news and information from web searches.

    This connector searches the web for topics and returns structured content
    that can be analyzed for sentiment. It aggregates from multiple sources.
    """

    name = "web_search"

    def __init__(
        self,
        queries: List[str] = None,
        max_results_per_query: int = 20,
        search_apis: List[str] = None,
        delay_ms: int = 500,
        sources_filter: List[str] = None,
        **kwargs,
    ):
        """
        Initialize Web Search connector.

        Args:
            queries: Search queries to execute
            max_results_per_query: Maximum results per query
            search_apis: Which APIs to use (e.g., ["duckduckgo", "newsapi"])
            delay_ms: Delay between requests in milliseconds
            sources_filter: Preferred news sources (e.g., ["reuters", "bloomberg"])
        """
        super().__init__(**kwargs)
        self.queries = queries or []
        self.max_results = max_results_per_query
        self.search_apis = search_apis or ["duckduckgo"]
        self.delay_ms = delay_ms
        self.sources_filter = sources_filter or []

    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """Fetch content from web searches."""

        if not self.queries:
            logger.warning("No search queries provided to WebSearchConnector")
            return

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

        async with aiohttp.ClientSession(
            headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            for query in self.queries:
                logger.info(f"Searching web for: {query}")

                try:
                    async for item in self._search_query(session, query):
                        yield item
                except Exception as e:
                    logger.error(f"Failed to search for '{query}': {e}")
                    continue

                # Rate limiting
                if self.delay_ms > 0:
                    await asyncio.sleep(self.delay_ms / 1000.0)

    async def _search_query(
        self, session: aiohttp.ClientSession, query: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Execute search for a specific query."""

        results_count = 0

        # Use DuckDuckGo Instant Answer API (free, no key required)
        if "duckduckgo" in self.search_apis:
            async for item in self._search_duckduckgo(session, query):
                if results_count >= self.max_results:
                    break
                yield item
                results_count += 1

    async def _search_duckduckgo(
        self, session: aiohttp.ClientSession, query: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Search using DuckDuckGo Instant Answer API."""

        try:
            # DuckDuckGo Instant Answer API
            url = "https://api.duckduckgo.com/"
            params = {
                "q": query,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1
            }

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    logger.warning(f"DuckDuckGo API returned status {response.status}")
                    return

                data = await response.json()

                # Extract abstract/summary
                if data.get("Abstract"):
                    yield {
                        "id": make_id(data.get("AbstractURL", "") + query),
                        "source": self.name,
                        "url": data.get("AbstractURL", ""),
                        "title": data.get("Heading", query),
                        "text": data.get("Abstract", ""),
                        "published_at": datetime.utcnow().isoformat(),
                        "metadata": {
                            "query": query,
                            "source_name": data.get("AbstractSource", "DuckDuckGo"),
                            "search_type": "instant_answer"
                        }
                    }

                # Extract related topics
                for topic in data.get("RelatedTopics", [])[:5]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        yield {
                            "id": make_id(topic.get("FirstURL", "") + topic.get("Text", "")),
                            "source": self.name,
                            "url": topic.get("FirstURL", ""),
                            "title": topic.get("Text", "")[:100],
                            "text": topic.get("Text", ""),
                            "published_at": datetime.utcnow().isoformat(),
                            "metadata": {
                                "query": query,
                                "source_name": "DuckDuckGo Related",
                                "search_type": "related_topic"
                            }
                        }

        except Exception as e:
            logger.error(f"DuckDuckGo search failed for '{query}': {e}")


class EnhancedWebSearchConnector(Connector):
    """
    Enhanced web search that simulates multi-source aggregation.

    This connector creates synthetic search results based on common news patterns
    and known reliable sources for specific topics.
    """

    name = "enhanced_web_search"

    def __init__(
        self,
        topic: str = "",
        queries: List[str] = None,
        max_results: int = 50,
        include_sources: List[str] = None,
        **kwargs,
    ):
        """
        Initialize Enhanced Web Search connector.

        Args:
            topic: Main topic to search for
            queries: Specific search queries
            max_results: Maximum total results
            include_sources: Preferred sources to prioritize
        """
        super().__init__(**kwargs)
        self.topic = topic
        self.queries = queries or self._generate_queries(topic)
        self.max_results = max_results
        self.include_sources = include_sources or [
            "reuters", "bloomberg", "cnn", "bbc", "financial times",
            "wall street journal", "daily nation", "business daily"
        ]

        # Source credibility scores
        self.source_credibility = {
            "reuters": 0.95,
            "bloomberg": 0.93,
            "financial times": 0.92,
            "wall street journal": 0.90,
            "bbc": 0.90,
            "ap": 0.92,
            "cnn": 0.75,
            "daily nation": 0.80,
            "business daily": 0.78,
            "standard": 0.75,
        }

    def _generate_queries(self, topic: str) -> List[str]:
        """Generate related search queries for a topic."""
        base_queries = [topic]

        # Add contextual queries
        if "kenya" in topic.lower():
            base_queries.extend([
                f"{topic} AGOA",
                f"{topic} trade agreement",
                f"{topic} exports imports",
                f"{topic} economic impact",
                f"{topic} bilateral relations"
            ])

        if "agoa" in topic.lower():
            base_queries.extend([
                "AGOA expiration 2025",
                "AGOA renewal extension",
                "AGOA Kenya impact jobs",
                "AGOA textile apparel"
            ])

        return base_queries[:10]  # Limit to 10 queries

    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Fetch web search results.

        Note: This is a template. In production, integrate with:
        - NewsAPI (newsapi.org)
        - GDELT (gdeltproject.org)
        - Bing News API
        - Google News RSS
        - Direct RSS feeds from major publications
        """

        logger.info(f"Enhanced web search for topic: {self.topic}")

        # For now, yield template structure
        # In production, replace with actual API calls

        for query in self.queries[:3]:  # Limit for demo
            yield {
                "id": make_id(query + str(datetime.utcnow())),
                "source": self.name,
                "url": f"https://example.com/search?q={query}",
                "title": f"Search results for: {query}",
                "text": f"[Web search connector active] Query: {query}. Configure API keys to fetch live data.",
                "published_at": datetime.utcnow().isoformat(),
                "metadata": {
                    "query": query,
                    "search_type": "template",
                    "note": "Configure NewsAPI, GDELT, or other APIs for live data"
                }
            }


# Export connectors
__all__ = ["WebSearchConnector", "EnhancedWebSearchConnector"]
