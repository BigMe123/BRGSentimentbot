#!/usr/bin/env python3
"""
RSS Monitoring Infrastructure
Real-time health monitoring, validation, and quarantine system for RSS feeds
"""

import asyncio
import aiohttp
import feedparser
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
import json
import sqlite3
import logging
from pathlib import Path
import pandas as pd
from urllib.parse import urlparse
import hashlib
import time

logger = logging.getLogger(__name__)


@dataclass
class FeedHealth:
    """Health status of an RSS feed"""

    url: str
    domain: str
    last_check: datetime
    status: str  # "healthy", "degraded", "quarantine", "dead"

    # Health metrics
    response_time_ms: float
    items_count: int
    last_item_age_hours: float
    error_count: int = 0
    consecutive_errors: int = 0

    # Validation results
    has_valid_structure: bool = True
    has_recent_items: bool = True
    has_required_fields: bool = True

    # Historical performance
    success_rate_7d: float = 1.0
    avg_response_time_7d: float = 0.0
    avg_items_7d: float = 0.0

    def is_healthy(self) -> bool:
        """Check if feed is healthy"""
        return (
            self.status == "healthy" and
            self.consecutive_errors < 3 and
            self.success_rate_7d >= 0.8 and
            self.has_recent_items
        )

    def should_quarantine(self) -> bool:
        """Check if feed should be quarantined"""
        return (
            self.consecutive_errors >= 5 or
            self.success_rate_7d < 0.5 or
            self.status == "quarantine"
        )


@dataclass
class FeedItem:
    """Parsed RSS feed item"""

    title: str
    link: str
    published: datetime
    description: Optional[str] = None
    author: Optional[str] = None
    categories: List[str] = field(default_factory=list)
    guid: Optional[str] = None
    source_url: str = ""
    content_hash: str = ""

    def __post_init__(self):
        """Generate content hash if not provided"""
        if not self.content_hash:
            content = f"{self.title}{self.link}{self.published}"
            self.content_hash = hashlib.md5(content.encode()).hexdigest()


class RSSMonitor:
    """
    Production RSS monitoring system with health checks,
    validation, and automatic quarantine
    """

    def __init__(self, db_path: str = "state/rss_health.db"):
        self.db_path = db_path
        self._init_database()

        # Configuration
        self.config = {
            "timeout_seconds": 10,
            "max_retries": 3,
            "quarantine_threshold": 5,  # consecutive errors
            "health_check_interval": 3600,  # 1 hour
            "max_item_age_days": 7,
            "min_items_threshold": 1,
            "target_success_rate": 0.92
        }

        # In-memory cache
        self._health_cache: Dict[str, FeedHealth] = {}
        self._last_full_check = datetime.now() - timedelta(hours=25)

    def _init_database(self):
        """Initialize SQLite database for health tracking"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Health history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feed_health (
                url TEXT PRIMARY KEY,
                domain TEXT,
                last_check TIMESTAMP,
                status TEXT,
                response_time_ms REAL,
                items_count INTEGER,
                last_item_age_hours REAL,
                error_count INTEGER,
                consecutive_errors INTEGER,
                has_valid_structure BOOLEAN,
                has_recent_items BOOLEAN,
                has_required_fields BOOLEAN,
                success_rate_7d REAL,
                avg_response_time_7d REAL,
                avg_items_7d REAL
            )
        """)

        # Check history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS check_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                check_time TIMESTAMP,
                success BOOLEAN,
                response_time_ms REAL,
                items_count INTEGER,
                error_message TEXT,
                FOREIGN KEY (url) REFERENCES feed_health(url)
            )
        """)

        # Quarantine table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quarantine (
                url TEXT PRIMARY KEY,
                quarantine_time TIMESTAMP,
                reason TEXT,
                last_error TEXT,
                attempts_since_quarantine INTEGER DEFAULT 0
            )
        """)

        conn.commit()
        conn.close()

    async def check_feed(self, url: str) -> Tuple[FeedHealth, List[FeedItem]]:
        """
        Check a single RSS feed health and retrieve items

        Returns:
            Tuple of (FeedHealth, List[FeedItem])
        """
        start_time = time.time()
        domain = urlparse(url).netloc

        try:
            # Fetch and parse feed
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=self.config["timeout_seconds"])
                ) as response:
                    response_time = (time.time() - start_time) * 1000
                    content = await response.text()

            # Parse with feedparser
            feed = feedparser.parse(content)

            # Validate structure
            has_valid_structure = self._validate_feed_structure(feed)

            # Parse items
            items = self._parse_feed_items(feed, url)

            # Calculate metrics
            last_item_age = self._calculate_item_age(items)
            has_recent_items = last_item_age < (self.config["max_item_age_days"] * 24)

            # Check required fields
            has_required_fields = all(
                item.title and item.link and item.published
                for item in items[:5]  # Check first 5 items
            ) if items else False

            # Get historical metrics
            historical = self._get_historical_metrics(url)

            # Create health status
            health = FeedHealth(
                url=url,
                domain=domain,
                last_check=datetime.now(),
                status="healthy" if has_valid_structure and items else "degraded",
                response_time_ms=response_time,
                items_count=len(items),
                last_item_age_hours=last_item_age,
                error_count=0,
                consecutive_errors=0,
                has_valid_structure=has_valid_structure,
                has_recent_items=has_recent_items,
                has_required_fields=has_required_fields,
                success_rate_7d=historical.get("success_rate", 1.0),
                avg_response_time_7d=historical.get("avg_response_time", response_time),
                avg_items_7d=historical.get("avg_items", len(items))
            )

            # Record success
            self._record_check(url, True, response_time, len(items))
            self._update_health_status(health)

            return health, items

        except asyncio.TimeoutError:
            error_msg = "Timeout"
            logger.warning(f"RSS timeout for {url}")
        except aiohttp.ClientError as e:
            error_msg = f"HTTP error: {str(e)}"
            logger.warning(f"RSS HTTP error for {url}: {e}")
        except Exception as e:
            error_msg = f"Parse error: {str(e)}"
            logger.error(f"RSS parse error for {url}: {e}")

        # Handle error case
        previous_health = self._get_previous_health(url)
        consecutive_errors = (previous_health.consecutive_errors + 1) if previous_health else 1

        health = FeedHealth(
            url=url,
            domain=domain,
            last_check=datetime.now(),
            status="quarantine" if consecutive_errors >= self.config["quarantine_threshold"] else "degraded",
            response_time_ms=(time.time() - start_time) * 1000,
            items_count=0,
            last_item_age_hours=999,
            error_count=(previous_health.error_count + 1) if previous_health else 1,
            consecutive_errors=consecutive_errors,
            has_valid_structure=False,
            has_recent_items=False,
            has_required_fields=False,
            success_rate_7d=previous_health.success_rate_7d if previous_health else 0,
            avg_response_time_7d=previous_health.avg_response_time_7d if previous_health else 0,
            avg_items_7d=previous_health.avg_items_7d if previous_health else 0
        )

        # Record failure
        self._record_check(url, False, health.response_time_ms, 0, error_msg)
        self._update_health_status(health)

        # Quarantine if needed
        if health.should_quarantine():
            self._quarantine_feed(url, error_msg)

        return health, []

    async def check_all_feeds(self, feed_urls: List[str]) -> Dict[str, FeedHealth]:
        """
        Check health of all feeds in parallel

        Args:
            feed_urls: List of RSS feed URLs to check

        Returns:
            Dictionary mapping URL to FeedHealth
        """
        logger.info(f"Starting health check for {len(feed_urls)} feeds")

        # Create tasks for parallel checking
        tasks = [self.check_feed(url) for url in feed_urls]

        # Run with concurrency limit
        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent checks

        async def check_with_limit(url):
            async with semaphore:
                return await self.check_feed(url)

        tasks = [check_with_limit(url) for url in feed_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        health_status = {}
        for url, result in zip(feed_urls, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to check {url}: {result}")
                health_status[url] = self._create_error_health(url)
            else:
                health, items = result
                health_status[url] = health

        # Update cache
        self._health_cache.update(health_status)
        self._last_full_check = datetime.now()

        return health_status

    def get_health_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive health report

        Returns:
            Dictionary with health metrics and statistics
        """
        conn = sqlite3.connect(self.db_path)

        # Overall statistics
        overall_query = """
            SELECT
                COUNT(*) as total_feeds,
                SUM(CASE WHEN status = 'healthy' THEN 1 ELSE 0 END) as healthy_feeds,
                SUM(CASE WHEN status = 'degraded' THEN 1 ELSE 0 END) as degraded_feeds,
                SUM(CASE WHEN status = 'quarantine' THEN 1 ELSE 0 END) as quarantined_feeds,
                AVG(success_rate_7d) as avg_success_rate,
                AVG(avg_response_time_7d) as avg_response_time,
                AVG(avg_items_7d) as avg_items_per_feed
            FROM feed_health
        """

        overall = pd.read_sql_query(overall_query, conn).iloc[0].to_dict()

        # Problem feeds
        problem_query = """
            SELECT url, domain, status, consecutive_errors, success_rate_7d
            FROM feed_health
            WHERE status != 'healthy'
            ORDER BY consecutive_errors DESC
            LIMIT 20
        """
        problem_feeds = pd.read_sql_query(problem_query, conn).to_dict('records')

        # Recent failures
        recent_failures_query = """
            SELECT url, check_time, error_message
            FROM check_history
            WHERE success = 0
            ORDER BY check_time DESC
            LIMIT 20
        """
        recent_failures = pd.read_sql_query(recent_failures_query, conn).to_dict('records')

        # Quarantined feeds
        quarantine_query = """
            SELECT url, quarantine_time, reason, attempts_since_quarantine
            FROM quarantine
            ORDER BY quarantine_time DESC
        """
        quarantined = pd.read_sql_query(quarantine_query, conn).to_dict('records')

        conn.close()

        # Calculate health score
        if overall["total_feeds"] > 0:
            health_score = (overall["healthy_feeds"] / overall["total_feeds"]) * 100
        else:
            health_score = 0

        return {
            "timestamp": datetime.now().isoformat(),
            "overall": overall,
            "health_score": health_score,
            "meets_sla": health_score >= self.config["target_success_rate"] * 100,
            "problem_feeds": problem_feeds,
            "recent_failures": recent_failures,
            "quarantined_feeds": quarantined,
            "last_full_check": self._last_full_check.isoformat()
        }

    def export_health_csv(self, output_path: str):
        """Export health data to CSV for analysis"""
        conn = sqlite3.connect(self.db_path)

        # Export feed health
        health_df = pd.read_sql_query("SELECT * FROM feed_health", conn)
        health_df.to_csv(f"{output_path}_health.csv", index=False)

        # Export check history
        history_df = pd.read_sql_query(
            "SELECT * FROM check_history ORDER BY check_time DESC LIMIT 10000",
            conn
        )
        history_df.to_csv(f"{output_path}_history.csv", index=False)

        conn.close()
        logger.info(f"Exported health data to {output_path}")

    def _validate_feed_structure(self, feed: feedparser.FeedParserDict) -> bool:
        """Validate RSS feed structure"""
        # Check for required feed elements
        if not feed.get("feed"):
            return False

        # Check for entries
        if not feed.get("entries"):
            return False

        # Check feed has a title
        if not feed.feed.get("title"):
            return False

        return True

    def _parse_feed_items(self, feed: feedparser.FeedParserDict, source_url: str) -> List[FeedItem]:
        """Parse feed items into FeedItem objects"""
        items = []

        for entry in feed.entries[:50]:  # Limit to 50 items
            try:
                # Parse published date
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                else:
                    published = datetime.now()

                # Extract categories
                categories = []
                if hasattr(entry, "tags"):
                    categories = [tag.term for tag in entry.tags if hasattr(tag, "term")]

                item = FeedItem(
                    title=entry.get("title", ""),
                    link=entry.get("link", ""),
                    published=published,
                    description=entry.get("description", ""),
                    author=entry.get("author", ""),
                    categories=categories,
                    guid=entry.get("id", ""),
                    source_url=source_url
                )

                items.append(item)

            except Exception as e:
                logger.warning(f"Failed to parse feed item: {e}")
                continue

        return items

    def _calculate_item_age(self, items: List[FeedItem]) -> float:
        """Calculate age of most recent item in hours"""
        if not items:
            return 999.0

        most_recent = max(items, key=lambda x: x.published)
        age = datetime.now() - most_recent.published
        return age.total_seconds() / 3600

    def _get_historical_metrics(self, url: str) -> Dict[str, float]:
        """Get 7-day historical metrics for a feed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        seven_days_ago = datetime.now() - timedelta(days=7)

        query = """
            SELECT
                AVG(CASE WHEN success THEN 1 ELSE 0 END) as success_rate,
                AVG(response_time_ms) as avg_response_time,
                AVG(items_count) as avg_items
            FROM check_history
            WHERE url = ? AND check_time > ?
        """

        cursor.execute(query, (url, seven_days_ago))
        result = cursor.fetchone()
        conn.close()

        if result and result[0] is not None:
            return {
                "success_rate": result[0],
                "avg_response_time": result[1] or 0,
                "avg_items": result[2] or 0
            }

        return {"success_rate": 1.0, "avg_response_time": 0, "avg_items": 0}

    def _get_previous_health(self, url: str) -> Optional[FeedHealth]:
        """Get previous health status from cache or database"""
        # Check cache first
        if url in self._health_cache:
            return self._health_cache[url]

        # Check database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM feed_health WHERE url = ?", (url,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return FeedHealth(
                url=row[0],
                domain=row[1],
                last_check=datetime.fromisoformat(row[2]) if row[2] else datetime.now(),
                status=row[3],
                response_time_ms=row[4],
                items_count=row[5],
                last_item_age_hours=row[6],
                error_count=row[7],
                consecutive_errors=row[8],
                has_valid_structure=bool(row[9]),
                has_recent_items=bool(row[10]),
                has_required_fields=bool(row[11]),
                success_rate_7d=row[12],
                avg_response_time_7d=row[13],
                avg_items_7d=row[14]
            )

        return None

    def _record_check(
        self,
        url: str,
        success: bool,
        response_time: float,
        items_count: int,
        error_message: str = None
    ):
        """Record check result in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO check_history (url, check_time, success, response_time_ms, items_count, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (url, datetime.now(), success, response_time, items_count, error_message))

        conn.commit()
        conn.close()

    def _update_health_status(self, health: FeedHealth):
        """Update health status in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO feed_health VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            health.url,
            health.domain,
            health.last_check,
            health.status,
            health.response_time_ms,
            health.items_count,
            health.last_item_age_hours,
            health.error_count,
            health.consecutive_errors,
            health.has_valid_structure,
            health.has_recent_items,
            health.has_required_fields,
            health.success_rate_7d,
            health.avg_response_time_7d,
            health.avg_items_7d
        ))

        conn.commit()
        conn.close()

    def _quarantine_feed(self, url: str, reason: str):
        """Quarantine a problematic feed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO quarantine (url, quarantine_time, reason, last_error)
            VALUES (?, ?, ?, ?)
        """, (url, datetime.now(), f"Exceeded error threshold", reason))

        conn.commit()
        conn.close()

        logger.warning(f"Quarantined feed: {url} - {reason}")

    def _create_error_health(self, url: str) -> FeedHealth:
        """Create error health status"""
        return FeedHealth(
            url=url,
            domain=urlparse(url).netloc,
            last_check=datetime.now(),
            status="error",
            response_time_ms=0,
            items_count=0,
            last_item_age_hours=999,
            error_count=1,
            consecutive_errors=1,
            has_valid_structure=False,
            has_recent_items=False,
            has_required_fields=False
        )

    def release_from_quarantine(self, url: str):
        """Manually release a feed from quarantine"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM quarantine WHERE url = ?", (url,))

        # Reset consecutive errors
        cursor.execute("""
            UPDATE feed_health
            SET consecutive_errors = 0, status = 'degraded'
            WHERE url = ?
        """, (url,))

        conn.commit()
        conn.close()

        logger.info(f"Released {url} from quarantine")

    async def is_quarantined(self, url: str) -> bool:
        """
        Check if a feed is currently quarantined

        Args:
            url: Feed URL to check

        Returns:
            True if quarantined, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT quarantine_time FROM quarantine
            WHERE url = ? AND quarantine_time > datetime('now', '-24 hours')
        """, (url,))

        result = cursor.fetchone()
        conn.close()

        return result is not None

    async def get_all_feed_status(self, feed_urls: Optional[List[str]] = None) -> Dict[str, FeedHealth]:
        """
        Get current status of all monitored feeds

        Args:
            feed_urls: Optional list of specific feeds to check. If None, returns empty dict.

        Returns:
            Dictionary mapping feed URL to FeedHealth
        """
        if not feed_urls:
            return {}

        # Check each feed
        results = {}
        for url in feed_urls:
            health, _ = await self.check_feed(url)
            results[url] = health

        return results


# Export main classes
__all__ = ["RSSMonitor", "FeedHealth", "FeedItem"]