#!/usr/bin/env python3
"""
News Ingestion Pipeline with Quality Gates
===========================================
Unified ingestion system for TheNewsAPI and RSS sources with deduplication,
quality control, and intelligent routing.
"""

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
import numpy as np
try:
    from simhash import Simhash
    HAS_SIMHASH = True
except ImportError:
    HAS_SIMHASH = False
    # Simple hash-based alternative
    class Simhash:
        def __init__(self, tokens):
            self.value = hash(' '.join(tokens)) & 0xFFFFFFFF
import feedparser
import aiohttp
from bs4 import BeautifulSoup

from sentiment_bot.source_registry import (
    SourceRegistry, PriorityRouter, QuotaManager,
    UnifiedEvent, SourceChannel, Source
)

logger = logging.getLogger(__name__)


class QualityGates:
    """Quality control and deduplication for news articles."""

    def __init__(self):
        self.seen_hashes: Set[str] = set()
        self.simhash_index: Dict[int, List[str]] = {}  # simhash -> [event_ids]
        self.min_text_length = 100
        self.max_text_length = 50000
        self.simhash_threshold = 3  # Hamming distance for near-duplicates

    def is_duplicate(self, event: UnifiedEvent) -> bool:
        """Check if event is duplicate or near-duplicate."""
        # Exact URL match
        if event.url in self.seen_hashes:
            return True

        # Content hash match (exact duplicate)
        if event.content_hash in self.seen_hashes:
            return True

        # Near-duplicate detection using SimHash
        text = event.title + " " + event.full_text
        simhash = Simhash(text.split()).value

        # Check for near-duplicates
        for existing_hash, event_ids in self.simhash_index.items():
            if self._hamming_distance(simhash, existing_hash) <= self.simhash_threshold:
                logger.debug(f"Near-duplicate detected: {event.event_id} similar to {event_ids[0]}")
                return True

        # Not a duplicate - add to indices
        self.seen_hashes.add(event.url)
        self.seen_hashes.add(event.content_hash)
        if simhash not in self.simhash_index:
            self.simhash_index[simhash] = []
        self.simhash_index[simhash].append(event.event_id)

        return False

    def _hamming_distance(self, hash1: int, hash2: int) -> int:
        """Calculate Hamming distance between two hashes."""
        x = hash1 ^ hash2
        count = 0
        while x:
            count += x & 1
            x >>= 1
        return count

    def passes_quality_checks(self, event: UnifiedEvent) -> bool:
        """Check if event passes quality thresholds."""
        # Check text length
        text_length = len(event.full_text)
        if text_length < self.min_text_length:
            logger.debug(f"Event {event.event_id} rejected: text too short ({text_length} chars)")
            return False

        if text_length > self.max_text_length:
            logger.debug(f"Event {event.event_id} rejected: text too long ({text_length} chars)")
            return False

        # Check for required fields
        if not event.title or not event.url:
            logger.debug(f"Event {event.event_id} rejected: missing required fields")
            return False

        # Check publication date (not too old)
        if event.published_at:
            age_days = (datetime.now() - event.published_at).days
            if age_days > 30:  # Skip articles older than 30 days
                logger.debug(f"Event {event.event_id} rejected: too old ({age_days} days)")
                return False

        return True

    def detect_syndication(self, events: List[UnifiedEvent]) -> List[UnifiedEvent]:
        """Detect and collapse syndicated content, keeping most reliable source."""
        # Group events by similar content
        content_groups: Dict[int, List[UnifiedEvent]] = {}

        for event in events:
            text = event.title + " " + event.full_text[:500]  # Use first 500 chars
            simhash = Simhash(text.split()).value

            # Find matching group
            matched = False
            for group_hash, group_events in content_groups.items():
                if self._hamming_distance(simhash, group_hash) <= 2:  # Very similar
                    group_events.append(event)
                    matched = True
                    break

            if not matched:
                content_groups[simhash] = [event]

        # For each group, keep the best source
        filtered_events = []
        for group_events in content_groups.values():
            if len(group_events) == 1:
                filtered_events.append(group_events[0])
            else:
                # Sort by reliability score (from source registry) and publication date
                best_event = min(group_events, key=lambda e: (
                    -self._get_source_reliability(e.domain),  # Higher reliability first
                    e.published_at  # Earlier publication first
                ))
                filtered_events.append(best_event)
                logger.info(f"Collapsed {len(group_events)} syndicated articles into 1")

        return filtered_events

    def _get_source_reliability(self, domain: str) -> float:
        """Get reliability score for a domain."""
        registry = SourceRegistry()
        source = registry.get_source(domain)
        return source.reliability_score if source else 0.5


class RSSHarvester:
    """Harvests articles from RSS feeds with full text extraction."""

    def __init__(self):
        self.session = None
        self.registry = SourceRegistry()

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def harvest_rss_sources(self, sources: List[Source],
                                 max_per_source: int = 20) -> List[UnifiedEvent]:
        """Harvest articles from RSS sources."""
        events = []

        for source in sources:
            if not source.rss_endpoints:
                continue

            for rss_url in source.rss_endpoints[:3]:  # Max 3 RSS feeds per source
                try:
                    source_events = await self._harvest_feed(
                        source, rss_url, max_per_source
                    )
                    events.extend(source_events)
                    logger.info(f"Harvested {len(source_events)} articles from {source.domain}")
                except Exception as e:
                    logger.error(f"Failed to harvest {source.domain}: {e}")

        return events

    async def _harvest_feed(self, source: Source, rss_url: str,
                          max_articles: int) -> List[UnifiedEvent]:
        """Harvest articles from a single RSS feed."""
        events = []

        try:
            # Fetch and parse RSS feed
            async with self.session.get(rss_url, timeout=10) as response:
                content = await response.text()

            feed = feedparser.parse(content)

            for entry in feed.entries[:max_articles]:
                try:
                    event = await self._process_rss_entry(source, entry)
                    if event:
                        events.append(event)
                except Exception as e:
                    logger.debug(f"Failed to process RSS entry: {e}")

        except Exception as e:
            logger.error(f"Failed to fetch RSS feed {rss_url}: {e}")

        return events

    async def _process_rss_entry(self, source: Source, entry: dict) -> Optional[UnifiedEvent]:
        """Process single RSS entry into unified event."""
        try:
            # Extract basic fields
            title = entry.get('title', '')
            url = entry.get('link', '')
            published = entry.get('published_parsed')

            if not title or not url:
                return None

            # Parse publication date
            if published:
                published_at = datetime(*published[:6])
            else:
                published_at = datetime.now()

            # Try to get full text
            full_text = entry.get('summary', '')

            # If we have content, use it
            if 'content' in entry and entry.content:
                full_text = entry.content[0].get('value', full_text)

            # If text is still short, try to fetch from URL
            if len(full_text) < 200:
                article_text = await self._fetch_article_content(url)
                if article_text:
                    full_text = article_text

            # Generate event ID
            event_id = hashlib.md5(url.encode()).hexdigest()

            # Create unified event
            event = UnifiedEvent(
                event_id=event_id,
                published_at=published_at,
                source_id=source.source_id,
                domain=source.domain,
                origin_country=source.country,
                target_countries=[],  # Will be extracted by NER
                language=source.language,
                title=title,
                full_text=full_text,
                url=url,
                canonical_url=url,
                content_hash=hashlib.md5(full_text.encode()).hexdigest(),
                fetch_channel=SourceChannel.RSS,
                fetch_timestamp=datetime.now()
            )

            return event

        except Exception as e:
            logger.debug(f"Failed to process RSS entry: {e}")
            return None

    async def _fetch_article_content(self, url: str) -> Optional[str]:
        """Fetch and extract article content from URL."""
        try:
            async with self.session.get(url, timeout=5) as response:
                html = await response.text()

            soup = BeautifulSoup(html, 'html.parser')

            # Remove script and style elements
            for script in soup(['script', 'style']):
                script.decompose()

            # Try to find article content
            article_selectors = [
                'article', 'main', '[role="main"]',
                '.article-content', '.post-content', '.entry-content',
                '.story-body', '.article-body'
            ]

            for selector in article_selectors:
                content = soup.select_one(selector)
                if content:
                    return content.get_text(separator=' ', strip=True)

            # Fallback to body text
            body = soup.find('body')
            if body:
                text = body.get_text(separator=' ', strip=True)
                # Return if it's substantial
                if len(text) > 500:
                    return text[:10000]  # Limit to 10k chars

            return None

        except Exception as e:
            logger.debug(f"Failed to fetch article content from {url}: {e}")
            return None


class NewsIngestionPipeline:
    """Main ingestion pipeline orchestrator."""

    def __init__(self, api_key: str, db_path: str = "source_registry.db"):
        self.api_key = api_key
        self.registry = SourceRegistry(db_path)
        self.router = PriorityRouter(api_key, db_path)
        self.quota_mgr = QuotaManager(db_path)
        self.quality_gates = QualityGates()
        self.batch_size = 40  # Articles per API call
        self.pacing_interval = 150  # Seconds between batches (10k/day ≈ 7/min)

    async def ingest_by_region(self, region: str, topics: List[str] = None) -> List[UnifiedEvent]:
        """Ingest news for a specific region with topic filtering."""
        all_events = []

        # Build search query
        if topics:
            query = f"{region} {' OR '.join(topics)}"
        else:
            query = region

        # Check quota before proceeding
        remaining, status = self.quota_mgr.check_quota()

        if remaining < self.batch_size:
            logger.warning(f"Insufficient quota ({remaining} < {self.batch_size}), using RSS only")
            return await self._ingest_rss_only(query, region)

        # Try API first
        api_events = await self._ingest_from_api(query, region)
        all_events.extend(api_events)

        # If API returned few results, supplement with RSS
        if len(api_events) < 20:
            logger.info(f"API returned only {len(api_events)} events, supplementing with RSS")
            rss_events = await self._ingest_rss_only(query, region)
            all_events.extend(rss_events)

        # Apply quality gates
        all_events = self._apply_quality_pipeline(all_events)

        return all_events

    async def _ingest_from_api(self, query: str, region: str) -> List[UnifiedEvent]:
        """Ingest from TheNewsAPI with proper parameters."""
        events = []

        # Map region to locale code
        region_locale_map = {
            'United States': 'us', 'USA': 'us',
            'United Kingdom': 'gb', 'UK': 'gb',
            'Germany': 'de', 'France': 'fr',
            'Japan': 'jp', 'China': 'cn',
            'India': 'in', 'Brazil': 'br',
            'Canada': 'ca', 'Australia': 'au'
        }

        locale = region_locale_map.get(region, 'us')

        # Fetch from API using correct endpoint
        try:
            events = self.router._fetch_from_api(
                query=query,
                country=locale,
                days_back=7,
                endpoint='all'  # Use /news/all for comprehensive coverage
            )
            logger.info(f"Fetched {len(events)} events from API for {region}")
        except Exception as e:
            logger.error(f"API ingestion failed: {e}")

        return events

    async def _ingest_rss_only(self, query: str, region: str) -> List[UnifiedEvent]:
        """Ingest from RSS sources only."""
        events = []

        # Get RSS sources for region
        sources = self._get_region_sources(region)

        # Use RSS harvester
        async with RSSHarvester() as harvester:
            events = await harvester.harvest_rss_sources(sources, max_per_source=10)

        # Filter by query terms if provided
        if query:
            query_terms = query.lower().split()
            events = [
                e for e in events
                if any(term in (e.title + " " + e.full_text).lower() for term in query_terms)
            ]

        logger.info(f"Harvested {len(events)} RSS events for {region}")
        return events

    def _get_region_sources(self, region: str) -> List[Source]:
        """Get sources for a specific region."""
        conn = self.registry.db_path
        sources = []

        # This would query the registry for region-specific sources
        # For now, return top sources
        all_sources = self.registry.get_api_covered_sources()

        # Filter by country/region if possible
        region_sources = [
            s for s in all_sources
            if region.lower() in s.country.lower() or
               region.lower() in s.metadata.get('region', '').lower()
        ]

        return region_sources[:20] if region_sources else all_sources[:20]

    def _apply_quality_pipeline(self, events: List[UnifiedEvent]) -> List[UnifiedEvent]:
        """Apply all quality gates and filters."""
        logger.info(f"Applying quality pipeline to {len(events)} events")

        # Step 1: Quality checks
        events = [e for e in events if self.quality_gates.passes_quality_checks(e)]
        logger.info(f"After quality checks: {len(events)} events")

        # Step 2: Deduplication
        unique_events = []
        for event in events:
            if not self.quality_gates.is_duplicate(event):
                unique_events.append(event)
        events = unique_events
        logger.info(f"After deduplication: {len(events)} events")

        # Step 3: Syndication detection
        events = self.quality_gates.detect_syndication(events)
        logger.info(f"After syndication collapse: {len(events)} events")

        return events

    async def scheduled_ingestion_cycle(self):
        """Run scheduled ingestion cycle for all regions."""
        regions = [
            'United States', 'Europe', 'Asia', 'Middle East',
            'Latin America', 'Africa', 'Oceania'
        ]

        topics = [
            'economy', 'politics', 'technology', 'climate',
            'trade', 'conflict', 'health'
        ]

        all_events = []

        for region in regions:
            # Check if we should continue
            remaining, status = self.quota_mgr.check_quota()
            if remaining < 100:
                logger.warning(f"Low quota ({remaining}), stopping ingestion cycle")
                break

            # Ingest for this region
            events = await self.ingest_by_region(region, topics[:3])
            all_events.extend(events)

            # Pace requests
            await asyncio.sleep(self.pacing_interval)

        logger.info(f"Ingestion cycle complete: {len(all_events)} total events")
        return all_events


async def run_coverage_audit():
    """Run coverage audit to identify API vs RSS coverage."""
    registry = SourceRegistry()
    router = PriorityRouter('DA4E99C181A54E1DFDB494EC2ABBA98D')

    # Get all sources
    sources = registry.get_api_covered_sources()

    for source in sources[:50]:  # Audit first 50 sources
        # Try API
        api_events = router._fetch_from_api(source.domain, days_back=1)

        # Try RSS (would need RSS implementation)
        rss_events = []  # Placeholder

        # Record audit
        registry.audit_coverage(
            domain=source.domain,
            api_articles=len(api_events),
            rss_articles=len(rss_events)
        )

        logger.info(f"Audited {source.domain}: API={len(api_events)}, RSS={len(rss_events)}")

        # Rate limit
        await asyncio.sleep(2)


async def main():
    """Main entry point for testing."""
    # Initialize pipeline
    pipeline = NewsIngestionPipeline('DA4E99C181A54E1DFDB494EC2ABBA98D')

    # Test ingestion
    events = await pipeline.ingest_by_region('United States', ['economy', 'technology'])
    print(f"\nIngested {len(events)} events for United States")

    if events:
        print("\nSample events:")
        for event in events[:3]:
            print(f"  - {event.title[:80]}")
            print(f"    Source: {event.domain}, Channel: {event.fetch_channel.value}")
            print(f"    Published: {event.published_at}")


if __name__ == "__main__":
    asyncio.run(main())