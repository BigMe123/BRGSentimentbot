"""
Optimized fetcher with integrated HTTP client, content filtering, and metrics.
This is the unified fetcher that brings together all optimizations.
"""

import asyncio
import feedparser
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from urllib.parse import urlparse
import logging

from .http_client import get_http_client
from .content_filter import ContentFilter, ArticleMetadata
from .metrics import MetricsCollector
from .config import settings
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Result from fetching and processing articles."""

    articles: List[ArticleMetadata]
    metrics: Dict[str, Any]
    alerts: List[Any]


class OptimizedFetcher:
    """
    Unified fetcher with all optimizations:
    - HTTP connection pooling and circuit breakers
    - Content filtering (freshness, dedup, skew control)
    - Metrics collection and alerting
    - Budget-aware execution
    """

    def __init__(
        self,
        budget_seconds: int = 300,  # 5 minutes
        max_concurrency: int = 64,
        per_domain_limit: int = 6,
        freshness_hours: int = 24,
        max_docs_per_domain: int = 10,
        max_domain_word_share: float = 0.15,
    ):
        self.budget_seconds = budget_seconds
        self.max_concurrency = max_concurrency
        self.per_domain_limit = per_domain_limit

        # Components
        self.http_client = None
        self.content_filter = ContentFilter(
            freshness_hours=freshness_hours,
            max_docs_per_domain=max_docs_per_domain,
            max_domain_word_share=max_domain_word_share,
        )
        self.metrics = MetricsCollector()

        # Timing
        self.start_time = None
        self.stop_requested = False

        # Queues for pipeline stages
        self.feed_queue: asyncio.Queue = asyncio.Queue()
        self.article_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.parse_queue: asyncio.Queue = asyncio.Queue(maxsize=500)

    async def initialize(self):
        """Initialize the fetcher components."""
        self.http_client = await get_http_client()
        self.start_time = time.time()

    def check_budget(self) -> bool:
        """Check if we're within time budget."""
        if self.start_time is None:
            return True

        elapsed = time.time() - self.start_time
        remaining = self.budget_seconds - elapsed

        if remaining < 10:  # Less than 10 seconds left
            logger.warning(f"Budget nearly exhausted: {remaining:.1f}s remaining")
            return False

        return True

    async def fetch_feed(self, feed_url: str) -> List[Dict[str, Any]]:
        """Fetch and parse an RSS/Atom feed."""
        domain = urlparse(feed_url).netloc

        # Fetch feed
        start = time.time()
        content, meta = await self.http_client.fetch(feed_url)
        latency_ms = int((time.time() - start) * 1000)

        # Record metrics
        success = content is not None
        self.metrics.record_fetch(
            domain=domain,
            success=success,
            latency_ms=latency_ms,
            status=meta.get("status", "unknown"),
            headless=False,
        )

        if not success:
            logger.debug(f"Failed to fetch feed {feed_url}: {meta.get('status')}")
            return []

        # Parse feed
        try:
            feed = feedparser.parse(content)
            articles = []

            for entry in feed.entries[:50]:  # Limit entries per feed
                # Extract article data
                article = {
                    "url": entry.get("link", ""),
                    "title": entry.get("title", ""),
                    "text": entry.get("summary", ""),
                    "published": None,
                    "domain": domain,
                }

                # Parse published date
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        article["published"] = datetime.fromtimestamp(
                            time.mktime(entry.published_parsed), tz=timezone.utc
                        )
                    except:
                        pass

                articles.append(article)

            logger.info(f"Parsed {len(articles)} articles from {feed_url}")
            return articles

        except Exception as e:
            logger.error(f"Error parsing feed {feed_url}: {e}")
            return []

    async def fetch_article_content(
        self, article: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Fetch full article content if needed."""
        url = article["url"]
        domain = urlparse(url).netloc

        # Skip if we already have sufficient content
        if article.get("text") and len(article["text"].split()) > 100:
            return article

        # Check budget before fetching
        if not self.check_budget():
            logger.debug(f"Budget exhausted, skipping article fetch for {url}")
            return None

        # Fetch article HTML
        start = time.time()
        content, meta = await self.http_client.fetch(url)
        latency_ms = int((time.time() - start) * 1000)

        # Record metrics
        success = content is not None
        self.metrics.record_fetch(
            domain=domain,
            success=success,
            latency_ms=latency_ms,
            status=meta.get("status", "unknown"),
            headless=False,
        )

        if success and content:
            # Basic HTML text extraction (simplified)
            import re

            text = re.sub(r"<[^>]+>", " ", content.decode("utf-8", errors="ignore"))
            text = re.sub(r"\s+", " ", text).strip()

            article["text"] = text[:10000]  # Cap at 10k chars

        return article

    async def feed_worker(self):
        """Worker to process RSS feeds."""
        while not self.stop_requested:
            try:
                feed_url = await asyncio.wait_for(self.feed_queue.get(), timeout=1.0)

                if feed_url is None:  # Poison pill
                    break

                # Check budget
                if not self.check_budget():
                    logger.info("Budget exhausted in feed worker")
                    break

                # Fetch and parse feed
                articles = await self.fetch_feed(feed_url)

                # Queue articles for processing
                for article in articles:
                    if not self.check_budget():
                        break

                    try:
                        await asyncio.wait_for(
                            self.article_queue.put(article), timeout=1.0
                        )
                    except asyncio.TimeoutError:
                        logger.warning("Article queue full, dropping article")

                self.feed_queue.task_done()

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Feed worker error: {e}")

    async def article_worker(self):
        """Worker to fetch article content."""
        while not self.stop_requested:
            try:
                article = await asyncio.wait_for(self.article_queue.get(), timeout=1.0)

                if article is None:  # Poison pill
                    break

                # Check budget
                if not self.check_budget():
                    logger.info("Budget exhausted in article worker")
                    break

                # Fetch full content if needed
                article = await self.fetch_article_content(article)

                if article:
                    # Queue for parsing
                    try:
                        await asyncio.wait_for(
                            self.parse_queue.put(article), timeout=1.0
                        )
                    except asyncio.TimeoutError:
                        logger.warning("Parse queue full, dropping article")

                self.article_queue.task_done()

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Article worker error: {e}")

    async def process_feeds(self, feed_urls: List[str]) -> FetchResult:
        """
        Process all feeds with budget awareness.

        Returns:
            FetchResult with filtered articles and metrics
        """
        await self.initialize()

        # Queue all feeds
        for url in feed_urls:
            await self.feed_queue.put(url)

        # Start workers
        num_feed_workers = min(10, len(feed_urls))
        num_article_workers = 20

        workers = []

        # Feed workers
        for _ in range(num_feed_workers):
            workers.append(asyncio.create_task(self.feed_worker()))

        # Article workers
        for _ in range(num_article_workers):
            workers.append(asyncio.create_task(self.article_worker()))

        logger.info(f"Started {len(workers)} workers for {len(feed_urls)} feeds")

        # Wait for feeds to be processed or budget to expire
        deadline = self.start_time + self.budget_seconds

        while True:
            # Check if all work is done
            if (
                self.feed_queue.empty()
                and self.article_queue.empty()
                and self.parse_queue.empty()
            ):
                break

            # Check budget
            if time.time() >= deadline:
                logger.warning("Budget expired, stopping workers")
                self.stop_requested = True
                break

            await asyncio.sleep(1)

        # Send poison pills to stop workers
        for _ in range(num_feed_workers):
            await self.feed_queue.put(None)
        for _ in range(num_article_workers):
            await self.article_queue.put(None)

        # Wait for workers to finish
        await asyncio.gather(*workers, return_exceptions=True)

        # Collect all parsed articles
        articles = []
        while not self.parse_queue.empty():
            try:
                article = self.parse_queue.get_nowait()
                articles.append(article)
            except:
                break

        logger.info(f"Collected {len(articles)} articles before filtering")

        # Apply content filtering
        filtered = self.content_filter.filter_and_weight(articles)

        # Record article metrics
        for article in filtered:
            self.metrics.record_article(
                domain=article.domain,
                word_count=article.word_count,
                published=article.published,
                was_deduped=False,
            )

        # Check alerts
        alerts = self.metrics.check_alerts()

        # Get final metrics
        metrics = self.metrics.get_metrics()

        # Log summary
        logger.info(f"Pipeline complete: {len(filtered)} articles after filtering")
        logger.info(f"Metrics: {metrics}")

        if alerts:
            for alert in alerts:
                logger.warning(f"ALERT [{alert.severity}]: {alert.message}")

        # Close HTTP client
        if self.http_client:
            await self.http_client.close()

        return FetchResult(articles=filtered, metrics=metrics, alerts=alerts)


async def fetch_with_budget(
    feed_urls: List[str], budget_seconds: int = 300, **kwargs
) -> FetchResult:
    """
    Convenience function to fetch feeds with a time budget.

    Args:
        feed_urls: List of RSS/Atom feed URLs
        budget_seconds: Maximum time to spend fetching
        **kwargs: Additional arguments for OptimizedFetcher

    Returns:
        FetchResult with articles and metrics
    """
    fetcher = OptimizedFetcher(budget_seconds=budget_seconds, **kwargs)

    return await fetcher.process_feeds(feed_urls)
