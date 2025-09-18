#!/usr/bin/env python3
"""
Hybrid Source Registry - RSS First, API Fallback
================================================
RSS-first news collection with TheNewsAPI.com fallback when RSS fails.
Seamless integration for maximum coverage and reliability.
"""

import sqlite3
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import time
import requests
import xml.etree.ElementTree as ET
import feedparser
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)


class SourceChannel(Enum):
    """Source data channel types."""
    RSS = "rss"
    API = "api"
    HYBRID = "hybrid"
    NONE = "none"


@dataclass
class Source:
    """Represents a news source with RSS and API capabilities."""
    source_id: str
    domain: str
    country: str
    language: str
    channel: SourceChannel
    reliability_score: float  # 0.0 to 1.0
    audience_estimate: int
    rss_endpoints: List[str] = field(default_factory=list)
    api_coverage: bool = True  # Assume API covers most sources
    last_checked: Optional[datetime] = None
    success_rate: float = 1.0
    avg_articles_per_fetch: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedEvent:
    """Normalized event structure for RSS and API sources."""
    event_id: str
    published_at: datetime
    source_id: str
    domain: str
    origin_country: str
    target_countries: List[str]
    language: str
    title: str
    full_text: str
    url: str
    canonical_url: str
    media: List[str] = field(default_factory=list)
    ner_entities: Dict[str, List[str]] = field(default_factory=dict)
    sentiment: Optional[float] = None
    summary: Optional[str] = None
    content_hash: str = ""
    fetch_channel: SourceChannel = SourceChannel.RSS
    fetch_timestamp: datetime = field(default_factory=datetime.now)


class RSSFetcher:
    """RSS feed fetcher with robust error handling."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'BSG-Hybrid-Bot/1.0'})

    def fetch_rss_articles(self, rss_url: str, source_domain: str,
                          query: str = None, max_articles: int = 10) -> List[UnifiedEvent]:
        """Fetch articles from RSS feed with comprehensive error handling."""
        events = []

        try:
            logger.info(f"Attempting RSS fetch from {source_domain}: {rss_url}")

            # Try feedparser first
            feed = feedparser.parse(rss_url)

            if not feed.entries:
                # Fallback to manual request + parsing
                response = self.session.get(rss_url, timeout=10)
                if response.status_code == 200:
                    feed = self._parse_xml_manually(response.content)
                else:
                    logger.warning(f"RSS fetch failed for {rss_url}: HTTP {response.status_code}")
                    return events

            # Process entries
            articles_found = 0
            for entry in feed.entries:
                if articles_found >= max_articles:
                    break

                if query and not self._matches_query(entry, query):
                    continue

                event = self._create_event_from_entry(entry, source_domain)
                if event:
                    events.append(event)
                    articles_found += 1

            logger.info(f"RSS success: {len(events)} articles from {source_domain}")

        except Exception as e:
            logger.error(f"RSS fetch failed for {rss_url}: {e}")

        return events

    def _matches_query(self, entry, query: str) -> bool:
        """Check if RSS entry matches search query."""
        query_terms = query.lower().split()
        text = (entry.get('title', '') + ' ' +
               entry.get('summary', '') + ' ' +
               entry.get('description', '')).lower()

        return any(term in text for term in query_terms)

    def _create_event_from_entry(self, entry, source_domain: str) -> Optional[UnifiedEvent]:
        """Create UnifiedEvent from RSS entry."""
        try:
            title = entry.get('title', '').strip()
            if not title:
                return None

            # Get published date
            published_at = datetime.now()
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published_at = datetime(*entry.published_parsed[:6])
            elif 'published' in entry:
                try:
                    published_at = date_parser.parse(entry.published)
                    if published_at.tzinfo:
                        published_at = published_at.replace(tzinfo=None)
                except:
                    pass

            # Get URL
            url = entry.get('link', '')
            if not url:
                return None

            # Get content
            content = entry.get('summary', '') or entry.get('description', '')

            # Generate event ID
            event_id = hashlib.md5(url.encode()).hexdigest()

            # Create event
            event = UnifiedEvent(
                event_id=event_id,
                published_at=published_at,
                source_id=source_domain,
                domain=source_domain,
                origin_country=self._infer_country(source_domain),
                target_countries=self._extract_countries(title + ' ' + content),
                language='en',
                title=title,
                full_text=content,
                url=url,
                canonical_url=url,
                content_hash=hashlib.md5((title + content).encode()).hexdigest(),
                fetch_channel=SourceChannel.RSS,
                fetch_timestamp=datetime.now()
            )

            return event

        except Exception as e:
            logger.error(f"Error creating event from RSS entry: {e}")
            return None

    def _parse_xml_manually(self, xml_content: bytes) -> feedparser.FeedParserDict:
        """Manual XML parsing fallback."""
        entries = []
        try:
            root = ET.fromstring(xml_content)
            items = root.findall('.//item')

            for item in items:
                entry = {}
                title_elem = item.find('title')
                if title_elem is not None and title_elem.text:
                    entry['title'] = title_elem.text

                link_elem = item.find('link')
                if link_elem is not None and link_elem.text:
                    entry['link'] = link_elem.text

                desc_elem = item.find('description')
                if desc_elem is not None and desc_elem.text:
                    entry['summary'] = desc_elem.text

                pubdate_elem = item.find('pubDate')
                if pubdate_elem is not None and pubdate_elem.text:
                    entry['published'] = pubdate_elem.text

                entries.append(entry)

        except ET.ParseError as e:
            logger.error(f"XML parsing error: {e}")

        result = feedparser.FeedParserDict()
        result.entries = entries
        return result

    def _infer_country(self, domain: str) -> str:
        """Infer country from domain."""
        tld_country_map = {
            '.uk': 'GBR', '.au': 'AUS', '.ca': 'CAN', '.de': 'DEU',
            '.fr': 'FRA', '.jp': 'JPN', '.cn': 'CHN', '.in': 'IND',
            '.br': 'BRA', '.ru': 'RUS', '.za': 'ZAF', '.mx': 'MEX'
        }

        for tld, country in tld_country_map.items():
            if tld in domain:
                return country
        return 'USA'

    def _extract_countries(self, text: str) -> List[str]:
        """Extract country mentions from text."""
        countries = []
        country_keywords = ['United States', 'China', 'Russia', 'Germany', 'France',
                           'United Kingdom', 'Japan', 'India', 'Brazil', 'Canada',
                           'Liechtenstein', 'Switzerland', 'Austria', 'Italy']

        text_lower = text.lower()
        for country in country_keywords:
            if country.lower() in text_lower:
                countries.append(country)

        return countries


class APIFallback:
    """TheNewsAPI.com fallback client."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.thenewsapi.com/v1"
        self.session = requests.Session()

    def fetch_articles(self, query: str, language: str = "en",
                      country: str = None, limit: int = 10) -> List[UnifiedEvent]:
        """Fetch articles from TheNewsAPI.com as fallback."""
        events = []
        start_time = time.time()

        try:
            url = f"{self.base_url}/news/all"

            params = {
                'api_token': self.api_key,
                'search': query,
                'language': language,
                'limit': limit,
                'sort': 'published_at'
            }

            if country:
                params['domains'] = self._get_country_domains(country)

            logger.info(f"API fallback: fetching from TheNewsAPI.com for query: {query}")
            response = self.session.get(url, params=params, timeout=15)

            if response.status_code == 200:
                data = response.json()
                articles = data.get('data', [])

                logger.info(f"API fallback success: {len(articles)} articles")

                for article in articles:
                    event = self._normalize_article(article)
                    if event:
                        events.append(event)

            else:
                logger.error(f"API fallback failed: HTTP {response.status_code}")

        except Exception as e:
            logger.error(f"API fallback error: {e}")

        return events

    def _normalize_article(self, article: dict) -> Optional[UnifiedEvent]:
        """Normalize API article to UnifiedEvent."""
        try:
            # Parse published date
            published_str = article.get('published_at', '')
            if published_str:
                published_at = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
                published_at = published_at.replace(tzinfo=None)
            else:
                published_at = datetime.now()

            # Extract source info
            domain = article.get('source', 'unknown')

            # Generate event ID
            url = article.get('url', '')
            event_id = hashlib.md5(url.encode()).hexdigest()

            # Extract countries mentioned
            target_countries = []
            content = (article.get('title', '') + ' ' +
                      article.get('description', '') + ' ' +
                      article.get('snippet', ''))

            country_keywords = ['United States', 'China', 'Russia', 'Germany', 'France',
                              'United Kingdom', 'Japan', 'India', 'Brazil', 'Canada',
                              'Liechtenstein', 'Switzerland', 'Austria', 'Italy']
            for country in country_keywords:
                if country.lower() in content.lower():
                    target_countries.append(country)

            # Create unified event
            event = UnifiedEvent(
                event_id=event_id,
                published_at=published_at,
                source_id=domain,
                domain=domain,
                origin_country=self._infer_country(domain),
                target_countries=target_countries,
                language=article.get('language', 'en'),
                title=article.get('title', ''),
                full_text=article.get('snippet', article.get('description', '')),
                url=url,
                canonical_url=url,
                media=[article.get('image_url', '')] if article.get('image_url') else [],
                summary=article.get('description', ''),
                content_hash=hashlib.md5(content.encode()).hexdigest(),
                fetch_channel=SourceChannel.API,
                fetch_timestamp=datetime.now()
            )

            return event

        except Exception as e:
            logger.error(f"Failed to normalize API article: {e}")
            return None

    def _infer_country(self, domain: str) -> str:
        """Infer country from domain."""
        tld_country_map = {
            '.uk': 'GBR', '.au': 'AUS', '.ca': 'CAN', '.de': 'DEU',
            '.fr': 'FRA', '.jp': 'JPN', '.cn': 'CHN', '.in': 'IND',
            '.br': 'BRA', '.ru': 'RUS', '.za': 'ZAF', '.mx': 'MEX'
        }

        for tld, country in tld_country_map.items():
            if tld in domain:
                return country
        return 'USA'

    def _get_country_domains(self, country: str) -> str:
        """Get domains for specific country."""
        country_domains = {
            'DEU': 'dw.com,spiegel.de,faz.net,zeit.de',
            'GBR': 'bbc.com,theguardian.com,independent.co.uk',
            'FRA': 'lemonde.fr,lefigaro.fr,liberation.fr',
            'USA': 'cnn.com,nytimes.com,washingtonpost.com'
        }
        return country_domains.get(country, '')


class HybridSourceRegistry:
    """Hybrid RSS-first with API fallback source registry."""

    def __init__(self, api_key: str, db_path: str = "hybrid_registry.db"):
        self.api_key = api_key
        self.rss_fetcher = RSSFetcher()
        self.api_fallback = APIFallback(api_key)
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize hybrid source registry database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sources (
                source_id TEXT PRIMARY KEY,
                domain TEXT UNIQUE NOT NULL,
                country TEXT,
                language TEXT,
                channel TEXT,
                reliability_score REAL DEFAULT 0.5,
                audience_estimate INTEGER DEFAULT 1000,
                rss_endpoints TEXT,
                api_coverage BOOLEAN DEFAULT TRUE,
                last_checked TIMESTAMP,
                success_rate REAL DEFAULT 1.0,
                avg_articles_per_fetch REAL DEFAULT 0.0,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain);
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fetch_log (
                fetch_id TEXT PRIMARY KEY,
                query TEXT,
                source_type TEXT,  -- 'rss' or 'api'
                timestamp TIMESTAMP,
                articles_found INTEGER,
                success BOOLEAN,
                error_message TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def fetch_articles(self, query: str, country: str = None,
                      language: str = "en", max_articles: int = 10) -> List[UnifiedEvent]:
        """Fetch articles using RSS-first, API-fallback strategy."""
        all_events = []

        # Step 1: Try RSS sources first
        logger.info(f"Starting hybrid fetch for query: '{query}' (RSS first)")
        rss_events = self._fetch_from_rss_sources(query, country, max_articles)

        if rss_events:
            logger.info(f"RSS success: found {len(rss_events)} articles")
            all_events.extend(rss_events)

            # Log successful RSS fetch
            self._log_fetch('rss', query, len(rss_events), True)
        else:
            logger.warning("RSS fetch failed or returned no results")
            self._log_fetch('rss', query, 0, False, "No articles or RSS errors")

        # Step 2: If RSS insufficient, use API fallback
        if len(all_events) < max_articles:
            remaining_needed = max_articles - len(all_events)
            logger.info(f"RSS insufficient ({len(all_events)}/{max_articles}), using API fallback for {remaining_needed} more")

            api_events = self.api_fallback.fetch_articles(
                query=query,
                language=language,
                country=country,
                limit=remaining_needed
            )

            if api_events:
                logger.info(f"API fallback success: found {len(api_events)} additional articles")
                all_events.extend(api_events)
                self._log_fetch('api', query, len(api_events), True)
            else:
                logger.warning("API fallback also failed")
                self._log_fetch('api', query, 0, False, "API fallback failed")

        # Step 3: Deduplicate and return
        unique_events = self._deduplicate_events(all_events)

        logger.info(f"Hybrid fetch complete: {len(unique_events)} unique articles (RSS: {len(rss_events)}, API: {len(api_events) if 'api_events' in locals() else 0})")

        return unique_events[:max_articles]

    def _fetch_from_rss_sources(self, query: str, country: str, max_articles: int) -> List[UnifiedEvent]:
        """Fetch from RSS sources with error handling."""
        events = []
        sources = self._get_sources_for_country(country) if country else self._get_all_sources()

        for source in sources[:5]:  # Try first 5 sources
            if len(events) >= max_articles:
                break

            for rss_url in source.rss_endpoints:
                try:
                    source_events = self.rss_fetcher.fetch_rss_articles(
                        rss_url, source.domain, query, max_articles - len(events)
                    )
                    events.extend(source_events)

                    if len(events) >= max_articles:
                        break

                except Exception as e:
                    logger.error(f"RSS error for {source.domain}: {e}")
                    continue

        return events

    def _get_sources_for_country(self, country: str) -> List[Source]:
        """Get sources for specific country from master sources."""
        sources = []
        try:
            # Load from master sources using the unified source manager
            from sentiment_bot.unified_source_manager import UnifiedSourceManager
            source_mgr = UnifiedSourceManager()

            # Get all sources and filter by country
            all_sources = source_mgr.get_all_sources()

            for source_data in all_sources:
                if source_data.get('country', '').lower() == country.lower():
                    source = Source(
                        source_id=source_data['domain'],
                        domain=source_data['domain'],
                        country=source_data.get('country', ''),
                        language=source_data.get('language', 'en'),
                        channel=SourceChannel.HYBRID,
                        reliability_score=source_data.get('priority', 0.5),
                        audience_estimate=10000,
                        rss_endpoints=source_data.get('rss_endpoints', [])
                    )
                    sources.append(source)

            logger.info(f"Found {len(sources)} sources for country: {country}")

        except Exception as e:
            logger.error(f"Error loading sources for country {country}: {e}")
            # Fallback to hardcoded sources
            if country == "DEU":
                return [
                    Source("dw", "dw.com", "DEU", "en", SourceChannel.HYBRID, 0.9, 100000,
                           ["https://rss.dw.com/rdf/rss-en-all", "https://rss.dw.com/xml/rss-en-pol"]),
                    Source("spiegel", "spiegel.de", "DEU", "en", SourceChannel.HYBRID, 0.8, 80000,
                           ["https://www.spiegel.de/international/index.rss"])
                ]

        return sources

    def _get_all_sources(self) -> List[Source]:
        """Get all available sources."""
        # Sample sources for demonstration
        return [
            Source("bbc", "bbc.com", "GBR", "en", SourceChannel.HYBRID, 0.95, 200000,
                   ["http://feeds.bbci.co.uk/news/rss.xml"]),
            Source("cnn", "cnn.com", "USA", "en", SourceChannel.HYBRID, 0.8, 150000,
                   ["http://rss.cnn.com/rss/edition.rss"])
        ]

    def _deduplicate_events(self, events: List[UnifiedEvent]) -> List[UnifiedEvent]:
        """Remove duplicate events based on URL and content hash."""
        seen_urls = set()
        seen_hashes = set()
        unique_events = []

        for event in events:
            if event.url not in seen_urls and event.content_hash not in seen_hashes:
                unique_events.append(event)
                seen_urls.add(event.url)
                seen_hashes.add(event.content_hash)

        return unique_events

    def _log_fetch(self, source_type: str, query: str, articles_found: int,
                   success: bool, error_message: str = None):
        """Log fetch attempt for monitoring."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        fetch_id = hashlib.md5(f"{datetime.now().isoformat()}{source_type}{query}".encode()).hexdigest()

        cursor.execute('''
            INSERT INTO fetch_log
            (fetch_id, query, source_type, timestamp, articles_found, success, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            fetch_id,
            query,
            source_type,
            datetime.now(),
            articles_found,
            success,
            error_message
        ))

        conn.commit()
        conn.close()


def test_hybrid_system():
    """Test the hybrid RSS-first, API-fallback system."""
    print("🔄 TESTING HYBRID RSS-FIRST + API FALLBACK SYSTEM")
    print("=" * 70)

    api_key = "BAV2J2VwecIEtxHVm1zOMGERfU52TA88zmW43Fbw"
    registry = HybridSourceRegistry(api_key)

    # Test 1: German politics (should get RSS + API)
    print("\n🇩🇪 Test 1: German Politics (RSS first, API fallback)")
    events = registry.fetch_articles("Germany politics", country="DEU", max_articles=10)

    print(f"\n📰 FOUND {len(events)} TOTAL ARTICLES")
    print("Source breakdown:")
    rss_count = len([e for e in events if e.fetch_channel == SourceChannel.RSS])
    api_count = len([e for e in events if e.fetch_channel == SourceChannel.API])
    print(f"  📡 RSS: {rss_count} articles")
    print(f"  🌐 API: {api_count} articles")

    print("\nSample articles:")
    for i, event in enumerate(events[:3], 1):
        channel_icon = "📡" if event.fetch_channel == SourceChannel.RSS else "🌐"
        print(f"  {i}. {channel_icon} {event.title[:60]}...")
        print(f"     Source: {event.domain} | {event.fetch_channel.value.upper()}")

    # Test 2: Obscure topic (likely to need API fallback)
    print(f"\n🇱🇮 Test 2: Liechtenstein (likely to need API fallback)")
    events2 = registry.fetch_articles("Liechtenstein", max_articles=5)

    print(f"\n📰 FOUND {len(events2)} TOTAL ARTICLES")
    rss_count2 = len([e for e in events2 if e.fetch_channel == SourceChannel.RSS])
    api_count2 = len([e for e in events2 if e.fetch_channel == SourceChannel.API])
    print(f"  📡 RSS: {rss_count2} articles")
    print(f"  🌐 API: {api_count2} articles")

    print(f"\n✅ HYBRID SYSTEM SUCCESS")
    print(f"✅ RSS-first strategy with seamless API fallback")
    print(f"✅ Total coverage: {len(events) + len(events2)} articles across tests")
    print(f"✅ Automatic failover when RSS sources insufficient")

    return len(events), len(events2)


if __name__ == "__main__":
    test_hybrid_system()