#!/usr/bin/env python3
"""
Source Registry with TheNewsAPI.com Integration
===============================================
Manages news sources with API-first priority routing and RSS fallback.
Uses TheNewsAPI.com for comprehensive news coverage.
"""

import sqlite3
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
import time
import requests
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import feedparser

logger = logging.getLogger(__name__)


class SourceChannel(Enum):
    """Source data channel types."""
    API = "api"
    RSS = "rss"
    BOTH = "both"
    NONE = "none"


class QuotaStatus(Enum):
    """API quota status levels."""
    GREEN = "green"   # < 60% used
    YELLOW = "yellow" # 60-80% used
    ORANGE = "orange" # 80-95% used
    RED = "red"       # > 95% used
    EXHAUSTED = "exhausted"  # 100% used


@dataclass
class Source:
    """Represents a news source with API and RSS capabilities."""
    source_id: str
    domain: str
    country: str
    language: str
    channel: SourceChannel
    reliability_score: float  # 0.0 to 1.0
    audience_estimate: int
    api_coverage: bool = False
    rss_endpoints: List[str] = field(default_factory=list)
    last_checked: Optional[datetime] = None
    success_rate: float = 1.0
    avg_articles_per_fetch: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedEvent:
    """Normalized event structure for API and RSS sources."""
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
    fetch_channel: SourceChannel = SourceChannel.API
    fetch_timestamp: datetime = field(default_factory=datetime.now)


class QuotaManager:
    """Fetches and parses RSS feeds from news sources."""

    def __init__(self, db_path: str = "source_registry.db"):
        self.db_path = db_path
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'BSG-RSS-Bot/1.0'})

    def fetch_rss_articles(self, rss_url: str, source_domain: str,
                          query: str = None, max_articles: int = 10) -> List[UnifiedEvent]:
        """Fetch articles from RSS feed."""
        events = []

        try:
            # Try feedparser first for better RSS parsing
            feed = feedparser.parse(rss_url)

            if not feed.entries:
                # Fallback to manual XML parsing
                response = self.session.get(rss_url, timeout=10)
                if response.status_code == 200:
                    feed = self._parse_xml_manually(response.content)
                else:
                    logger.warning(f"Failed to fetch RSS from {rss_url}: HTTP {response.status_code}")
                    return events

            # Process feed entries
            for entry in feed.entries[:max_articles]:
                if query and not self._matches_query(entry, query):
                    continue

                event = self._create_event_from_entry(entry, source_domain)
                if event:
                    events.append(event)

        except Exception as e:
            logger.error(f"Error fetching RSS from {rss_url}: {e}")

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
                    from dateutil import parser
                    published_at = parser.parse(entry.published)
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
                language='en',  # Assume English for now
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

        # Return feedparser-like structure
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
        return 'USA'  # Default

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


class SourceRegistry:
    """Central registry for RSS news sources."""

    def __init__(self, db_path: str = "source_registry.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize source registry database."""
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
            CREATE TABLE IF NOT EXISTS rss_fetch_log (
                fetch_id TEXT PRIMARY KEY,
                domain TEXT,
                rss_url TEXT,
                timestamp TIMESTAMP,
                articles_found INTEGER,
                success BOOLEAN,
                error_message TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def register_source(self, source: Source) -> bool:
        """Register or update an RSS news source."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT OR REPLACE INTO sources
                (source_id, domain, country, language, channel, reliability_score,
                 audience_estimate, rss_endpoints, last_checked,
                 success_rate, avg_articles_per_fetch, metadata, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                source.source_id,
                source.domain,
                source.country,
                source.language,
                source.channel.value,
                source.reliability_score,
                source.audience_estimate,
                json.dumps(source.rss_endpoints),
                source.last_checked,
                source.success_rate,
                source.avg_articles_per_fetch,
                json.dumps(source.metadata),
                datetime.now()
            ))

            conn.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to register source {source.domain}: {e}")
            return False

        finally:
            conn.close()

    def get_source(self, domain: str) -> Optional[Source]:
        """Get source by domain."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT source_id, domain, country, language, channel, reliability_score,
                   audience_estimate, api_coverage, rss_endpoints, last_checked,
                   success_rate, avg_articles_per_fetch, metadata
            FROM sources
            WHERE domain = ?
        ''', (domain,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return Source(
            source_id=row[0],
            domain=row[1],
            country=row[2],
            language=row[3],
            channel=SourceChannel(row[4]),
            reliability_score=row[5],
            audience_estimate=row[6],
            api_coverage=row[7],
            rss_endpoints=json.loads(row[8]) if row[8] else [],
            last_checked=datetime.fromisoformat(row[9]) if row[9] else None,
            success_rate=row[10],
            avg_articles_per_fetch=row[11],
            metadata=json.loads(row[12]) if row[12] else {}
        )

    def get_api_covered_sources(self) -> List[Source]:
        """Get all sources with API coverage."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT source_id, domain, country, language, channel, reliability_score,
                   audience_estimate, api_coverage, rss_endpoints, last_checked,
                   success_rate, avg_articles_per_fetch, metadata
            FROM sources
            WHERE api_coverage = TRUE
            ORDER BY reliability_score DESC, audience_estimate DESC
        ''')

        sources = []
        for row in cursor.fetchall():
            sources.append(Source(
                source_id=row[0],
                domain=row[1],
                country=row[2],
                language=row[3],
                channel=SourceChannel(row[4]),
                reliability_score=row[5],
                audience_estimate=row[6],
                api_coverage=row[7],
                rss_endpoints=json.loads(row[8]) if row[8] else [],
                last_checked=datetime.fromisoformat(row[9]) if row[9] else None,
                success_rate=row[10],
                avg_articles_per_fetch=row[11],
                metadata=json.loads(row[12]) if row[12] else {}
            ))

        conn.close()
        return sources

    def audit_coverage(self, domain: str, api_articles: int, rss_articles: int) -> None:
        """Record coverage audit results."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        audit_id = hashlib.md5(f"{domain}{datetime.now().isoformat()}".encode()).hexdigest()

        if api_articles > 0 and rss_articles > 0:
            status = "both"
        elif api_articles > 0:
            status = "api_only"
        elif rss_articles > 0:
            status = "rss_only"
        else:
            status = "none"

        cursor.execute('''
            INSERT INTO coverage_audit
            (audit_id, domain, api_check_time, api_articles_found,
             rss_articles_found, coverage_status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            audit_id,
            domain,
            datetime.now(),
            api_articles,
            rss_articles,
            status,
            f"API: {api_articles}, RSS: {rss_articles}"
        ))

        # Update source coverage status
        if api_articles > 0:
            cursor.execute('''
                UPDATE sources
                SET api_coverage = TRUE,
                    channel = CASE
                        WHEN channel = 'rss' THEN 'both'
                        ELSE channel
                    END,
                    updated_at = ?
                WHERE domain = ?
            ''', (datetime.now(), domain))

        conn.commit()
        conn.close()


class ProviderConfig:
    """Configuration for news API providers."""
    def __init__(self, name: str, base_url: str, endpoints: Dict[str, str],
                 param_map: Dict[str, str], auth_param: str):
        self.name = name
        self.base_url = base_url
        self.endpoints = endpoints  # {"general": "/news/all", "top": "/news/top"}
        self.param_map = param_map  # Parameter name mapping
        self.auth_param = auth_param  # "api_token" or "apikey"


class PriorityRouter:
    """Multi-provider news router with intelligent fallback and endpoint selection."""

    def __init__(self, api_key: str, db_path: str = "source_registry.db"):
        self.api_key = api_key
        self.registry = SourceRegistry(db_path)
        self.quota_mgr = QuotaManager(db_path)
        self.session = requests.Session()

        # Initialize provider configurations - ONLY general news providers
        self.providers = {
            "thenewsapi_com": ProviderConfig(
                name="TheNewsAPI.com",
                base_url="https://api.thenewsapi.com/v1",
                endpoints={"general": "/news/all", "top": "/news/top", "categories": "/news/categories"},
                param_map={"query": "search", "limit": "limit", "date_from": "published_after", "language": "language", "country": "locale"},
                auth_param="api_token"
            )
        }

        # Provider capability registry - ONLY general news
        self.provider_capabilities = {
            "general_news": ["thenewsapi_com"],
            "country_specific": ["thenewsapi_com"]
        }

    def fetch_articles(self, query: str, country: str = None,
                      days_back: int = 7) -> List[UnifiedEvent]:
        """Fetch articles with intelligent multi-provider routing."""
        events = []

        # Check quota first
        remaining, quota_status = self.quota_mgr.check_quota()

        if quota_status in [QuotaStatus.RED, QuotaStatus.EXHAUSTED]:
            logger.warning(f"Quota status {quota_status}, falling back to RSS only")
            return self._fetch_from_rss(query, country, days_back)

        # Try API providers if quota allows
        if remaining >= 40:  # At least one API call worth
            api_events = self._fetch_with_provider_routing(query, country, days_back)
            events.extend(api_events)

            # If API returned insufficient results, supplement with RSS
            if len(api_events) < 10:
                logger.info(f"API returned only {len(api_events)} articles, supplementing with RSS")
                rss_events = self._fetch_from_rss(query, country, days_back)
                events.extend(rss_events)
        else:
            # Not enough quota for API call
            logger.info(f"Only {remaining} articles remaining in quota, using RSS")
            events = self._fetch_from_rss(query, country, days_back)

        # Deduplicate
        events = self._deduplicate_events(events)

        return events

    def _fetch_with_provider_routing(self, query: str, country: str = None,
                                   days_back: int = 7) -> List[UnifiedEvent]:
        """Fetch with intelligent provider routing and fallback."""
        events = []

        # Route ALL queries to general news providers only
        provider_order = ["thenewsapi_com"]
        endpoint_order = ["general"]

        # Try each provider in order until we get results
        for provider_id in provider_order:
            if not events:  # Only try next provider if current one failed
                for endpoint_type in endpoint_order:
                    provider_events = self._fetch_from_provider(
                        provider_id, endpoint_type, query, country, days_back
                    )
                    if provider_events:
                        events.extend(provider_events)
                        logger.info(f"Successfully fetched {len(provider_events)} articles from {provider_id}:{endpoint_type}")
                        break  # Stop trying other endpoints for this provider

        return events

    def _fetch_from_provider(self, provider_id: str, endpoint_type: str,
                           query: str, country: str = None, days_back: int = 7) -> List[UnifiedEvent]:
        """Fetch from specific provider and endpoint."""
        if provider_id not in self.providers:
            logger.error(f"Unknown provider: {provider_id}")
            return []

        provider = self.providers[provider_id]

        if endpoint_type not in provider.endpoints:
            logger.debug(f"Provider {provider_id} does not support endpoint {endpoint_type}")
            return []

        events = []
        start_time = time.time()

        try:
            # Build URL and parameters based on provider configuration
            url = provider.base_url + provider.endpoints[endpoint_type]
            params = self._build_provider_params(provider, query, country, days_back, endpoint_type)

            logger.info(f"Trying {provider.name} {endpoint_type} endpoint: {url}")

            response = self.session.get(url, params=params, timeout=10)
            response_time_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                articles = self._parse_provider_response(response.json(), provider_id, endpoint_type)

                # Articles already filtered by API query parameter - no additional filtering needed

                # Consume quota and convert to events
                if articles and self.quota_mgr.consume_quota(len(articles)):
                    for article in articles:
                        event = self._normalize_api_article(article, provider_id)
                        if event:
                            events.append(event)

                    # Log successful call
                    self.quota_mgr.log_api_call(
                        endpoint=url,
                        params=params,
                        articles_returned=len(articles),
                        response_time_ms=response_time_ms,
                        success=True
                    )

                    logger.info(f"Successfully fetched {len(articles)} articles from {provider.name}")
                elif articles:
                    logger.warning("Quota consumption failed, results discarded")
                else:
                    logger.info(f"No articles returned from {provider.name} {endpoint_type}")
            else:
                logger.warning(f"{provider.name} {endpoint_type} returned status {response.status_code}: {response.text[:200]}")

                # Log failed call
                self.quota_mgr.log_api_call(
                    endpoint=url,
                    params=params,
                    articles_returned=0,
                    response_time_ms=response_time_ms,
                    success=False,
                    error_message=f"HTTP {response.status_code}"
                )

        except Exception as e:
            logger.error(f"Error fetching from {provider.name}: {e}")
            self.quota_mgr.log_api_call(
                endpoint=url if 'url' in locals() else 'unknown',
                params=params if 'params' in locals() else {},
                articles_returned=0,
                response_time_ms=int((time.time() - start_time) * 1000),
                success=False,
                error_message=str(e)
            )

        return events

    def _build_provider_params(self, provider: ProviderConfig, query: str,
                             country: str, days_back: int, endpoint_type: str) -> Dict[str, Any]:
        """Build API parameters based on provider configuration."""
        params = {}

        # Add authentication
        params[provider.auth_param] = self.api_key

        # Add query for all endpoints
        if query:
            query_param = provider.param_map.get("query", "q")
            params[query_param] = query

        # Add limit
        limit_param = provider.param_map.get("limit", "limit")
        params[limit_param] = 40

        # Add date range for all endpoints
        date_param = provider.param_map.get("date_from", "published_after")
        published_after = (datetime.now() - timedelta(days=days_back)).isoformat() + 'Z'
        params[date_param] = published_after

        # Add language if supported
        if "language" in provider.param_map:
            params[provider.param_map["language"]] = "en"

        # Add country if provided and supported
        if country and "country" in provider.param_map:
            country_param = provider.param_map["country"]
            params[country_param] = country.lower()[:2] if len(country) > 2 else country

        return params

    def _parse_provider_response(self, data: dict, provider_id: str, endpoint_type: str) -> List[dict]:
        """Parse response data based on provider format."""
        articles = []

        if provider_id == "thenewsapi_com":
            # TheNewsAPI.com format: data array
            articles = data.get('data', [])

        return articles

    def _filter_articles_by_query(self, articles: List[dict], query: str) -> List[dict]:
        """Filter articles by query terms."""
        if not query:
            return articles

        filtered_articles = []
        query_terms = query.lower().split()

        for article in articles:
            text = (article.get('title', '') + ' ' +
                   article.get('description', '') + ' ' +
                   article.get('content', '')).lower()

            # Check if any query term appears in the text
            if any(term in text for term in query_terms):
                filtered_articles.append(article)

        return filtered_articles

    def _fetch_from_rss(self, query: str, country: str = None,
                       days_back: int = 7) -> List[UnifiedEvent]:
        """Fetch from RSS sources (placeholder - integrate with existing RSS system)."""
        events = []

        # TODO: Integrate with existing RSS harvesting system
        # This is a placeholder showing the interface
        logger.info(f"RSS fetch for query='{query}', country='{country}' (not yet implemented)")

        return events

    def _normalize_api_article(self, article: dict, provider_id: str = None) -> Optional[UnifiedEvent]:
        """Normalize TheNewsAPI article to unified event."""
        try:
            # Parse published date
            published_str = article.get('published_at', '')
            if published_str:
                published_at = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
                published_at = published_at.replace(tzinfo=None)
            else:
                published_at = datetime.now()

            # Extract source info
            source_info = article.get('source', {})
            domain = source_info.get('domain', 'unknown')

            # Generate event ID
            url = article.get('url', '')
            event_id = hashlib.md5(url.encode()).hexdigest()

            # Extract countries mentioned
            target_countries = []
            content = (article.get('title', '') + ' ' +
                      article.get('description', '') + ' ' +
                      article.get('content', ''))

            # Simple country detection (can be enhanced)
            country_keywords = ['United States', 'China', 'Russia', 'Germany', 'France',
                              'United Kingdom', 'Japan', 'India', 'Brazil', 'Canada']
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
                full_text=article.get('content', article.get('description', '')),
                url=url,
                canonical_url=url,
                media=[article.get('thumbnail', '')] if article.get('thumbnail') else [],
                ner_entities=article.get('NER', {}),
                sentiment=article.get('sentiment'),
                summary=article.get('summary'),
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
        # Check registry first
        source = self.registry.get_source(domain)
        if source and source.country:
            return source.country

        # Simple TLD mapping
        tld_country_map = {
            '.uk': 'GBR', '.au': 'AUS', '.ca': 'CAN', '.de': 'DEU',
            '.fr': 'FRA', '.jp': 'JPN', '.cn': 'CHN', '.in': 'IND',
            '.br': 'BRA', '.ru': 'RUS', '.za': 'ZAF', '.mx': 'MEX'
        }

        for tld, country in tld_country_map.items():
            if tld in domain:
                return country

        return 'USA'  # Default

    def _deduplicate_events(self, events: List[UnifiedEvent]) -> List[UnifiedEvent]:
        """Deduplicate events by URL and content hash."""
        seen_urls = set()
        seen_hashes = set()
        unique_events = []

        for event in events:
            if event.url not in seen_urls and event.content_hash not in seen_hashes:
                unique_events.append(event)
                seen_urls.add(event.url)
                seen_hashes.add(event.content_hash)

        return unique_events


class CoverageMonitor:
    """Monitors and reports on source coverage."""

    def __init__(self, db_path: str = "source_registry.db"):
        self.db_path = db_path
        self.registry = SourceRegistry(db_path)

    def generate_daily_report(self) -> Dict[str, Any]:
        """Generate daily coverage and performance report."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        today = datetime.now().date().isoformat()

        # Get quota usage
        cursor.execute('''
            SELECT articles_fetched, api_calls_made, quota_status
            FROM api_quota
            WHERE date = ?
        ''', (today,))

        quota_row = cursor.fetchone()

        # Get API performance
        cursor.execute('''
            SELECT
                COUNT(*) as total_calls,
                SUM(articles_returned) as total_articles,
                AVG(response_time_ms) as avg_response_time,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_calls,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed_calls
            FROM api_calls_log
            WHERE DATE(timestamp) = ?
        ''', (today,))

        perf_row = cursor.fetchone()

        # Get coverage stats
        cursor.execute('''
            SELECT
                COUNT(*) as total_sources,
                SUM(CASE WHEN api_coverage = 1 THEN 1 ELSE 0 END) as api_covered,
                SUM(CASE WHEN channel = 'rss' THEN 1 ELSE 0 END) as rss_only,
                SUM(CASE WHEN channel = 'both' THEN 1 ELSE 0 END) as both_channels
            FROM sources
        ''')

        coverage_row = cursor.fetchone()

        # Get top uncovered RSS sources
        cursor.execute('''
            SELECT domain, audience_estimate, reliability_score
            FROM sources
            WHERE api_coverage = 0 AND channel IN ('rss', 'both')
            ORDER BY audience_estimate DESC, reliability_score DESC
            LIMIT 10
        ''')

        uncovered_sources = cursor.fetchall()

        conn.close()

        report = {
            'date': today,
            'quota': {
                'articles_used': quota_row[0] if quota_row else 0,
                'api_calls_made': quota_row[1] if quota_row else 0,
                'quota_status': quota_row[2] if quota_row else 'green',
                'remaining': 10000 - (quota_row[0] if quota_row else 0)
            },
            'performance': {
                'total_calls': perf_row[0] or 0,
                'total_articles': perf_row[1] or 0,
                'avg_response_time_ms': round(perf_row[2] or 0, 2),
                'successful_calls': perf_row[3] or 0,
                'failed_calls': perf_row[4] or 0,
                'success_rate': round(((perf_row[3] or 0) / (perf_row[0] or 1)) * 100, 2)
            },
            'coverage': {
                'total_sources': coverage_row[0] or 0,
                'api_covered': coverage_row[1] or 0,
                'rss_only': coverage_row[2] or 0,
                'both_channels': coverage_row[3] or 0,
                'api_coverage_percent': round(((coverage_row[1] or 0) / (coverage_row[0] or 1)) * 100, 2)
            },
            'top_uncovered_sources': [
                {'domain': row[0], 'audience': row[1], 'reliability': row[2]}
                for row in uncovered_sources
            ]
        }

        return report

    def print_report(self, report: Dict[str, Any]) -> None:
        """Print formatted coverage report."""
        print("\n" + "=" * 60)
        print(f"DAILY COVERAGE REPORT - {report['date']}")
        print("=" * 60)

        print("\n📊 QUOTA USAGE")
        print(f"  Articles Used: {report['quota']['articles_used']:,} / 10,000")
        print(f"  API Calls: {report['quota']['api_calls_made']}")
        print(f"  Status: {report['quota']['quota_status'].upper()}")
        print(f"  Remaining: {report['quota']['remaining']:,}")

        print("\n⚡ API PERFORMANCE")
        print(f"  Total Calls: {report['performance']['total_calls']}")
        print(f"  Articles Fetched: {report['performance']['total_articles']:,}")
        print(f"  Avg Response Time: {report['performance']['avg_response_time_ms']}ms")
        print(f"  Success Rate: {report['performance']['success_rate']}%")

        print("\n🌐 SOURCE COVERAGE")
        print(f"  Total Sources: {report['coverage']['total_sources']}")
        print(f"  API Covered: {report['coverage']['api_covered']} ({report['coverage']['api_coverage_percent']}%)")
        print(f"  RSS Only: {report['coverage']['rss_only']}")
        print(f"  Both Channels: {report['coverage']['both_channels']}")

        if report['top_uncovered_sources']:
            print("\n🎯 TOP UNCOVERED RSS SOURCES (candidates for API coverage)")
            for source in report['top_uncovered_sources'][:5]:
                print(f"  - {source['domain']}: audience={source['audience']:,}, reliability={source['reliability']:.2f}")


def initialize_from_master_sources():
    """Initialize registry from existing master sources YAML."""
    import yaml

    registry = SourceRegistry()

    # Load from master sources YAML
    yaml_path = Path("/Users/marcod/Desktop/BSG/BSGBOT/config/master_sources.yaml")
    if yaml_path.exists():
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)

        # Handle the correct YAML structure
        sources_list = data.get('sources', [])

        for source_info in sources_list:
            if not isinstance(source_info, dict):
                continue

            domain = source_info.get('domain', source_info.get('name', ''))
            if not domain:
                continue

            # Map country names to codes
            country_map = {
                'united_states': 'USA', 'united_kingdom': 'GBR',
                'germany': 'DEU', 'france': 'FRA', 'japan': 'JPN',
                'china': 'CHN', 'india': 'IND', 'brazil': 'BRA'
            }

            country = source_info.get('country', 'united_states')
            country_code = country_map.get(country, 'USA')

            # Create source from YAML data
            source = Source(
                source_id=hashlib.md5(domain.encode()).hexdigest(),
                domain=domain,
                country=country_code,
                language=source_info.get('language', 'en'),
                channel=SourceChannel.RSS,  # Start with RSS, will be updated by coverage audit
                reliability_score=source_info.get('priority', 0.5),
                audience_estimate=source_info.get('audience', 10000),
                api_coverage=False,  # Will be determined by coverage audit
                rss_endpoints=source_info.get('rss_endpoints', []),
                metadata={
                    'region': source_info.get('region', 'global'),
                    'topics': source_info.get('topics', []),
                    'name': source_info.get('name', domain)
                }
            )

            registry.register_source(source)
            logger.info(f"Registered source: {domain}")

    return registry


if __name__ == "__main__":
    # Initialize from master sources
    print("Initializing source registry from master sources...")
    registry = initialize_from_master_sources()

    # Create priority router
    api_key = 'DA4E99C181A54E1DFDB494EC2ABBA98D'
    router = PriorityRouter(api_key)

    # Test fetch with quota management
    print("\nTesting priority router with quota management...")
    events = router.fetch_articles("Germany", days_back=7)
    print(f"Fetched {len(events)} events")

    # Generate and print daily report
    monitor = CoverageMonitor()
    report = monitor.generate_daily_report()
    monitor.print_report(report)