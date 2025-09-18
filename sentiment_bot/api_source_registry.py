#!/usr/bin/env python3
"""
TheNewsAPI.com Source Registry
==============================
API-first news collection system using TheNewsAPI.com with RSS fallback.
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
    """Manages TheNewsAPI.com quota and usage."""

    def __init__(self, db_path: str = "api_registry.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize quota tracking database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_quota (
                date TEXT PRIMARY KEY,
                requests_made INTEGER DEFAULT 0,
                articles_fetched INTEGER DEFAULT 0,
                last_reset TIMESTAMP,
                quota_status TEXT DEFAULT 'green'
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_calls_log (
                call_id TEXT PRIMARY KEY,
                timestamp TIMESTAMP,
                endpoint TEXT,
                query TEXT,
                articles_returned INTEGER,
                response_time_ms INTEGER,
                success BOOLEAN,
                error_message TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def check_quota(self) -> Tuple[int, QuotaStatus]:
        """Check remaining quota for today."""
        # For demonstration, assume reasonable limits
        # Actual limits depend on your TheNewsAPI.com plan
        return 1000, QuotaStatus.GREEN

    def consume_quota(self, requests_count: int = 1) -> bool:
        """Consume quota and return True if successful."""
        return True  # Simplified for demo

    def log_api_call(self, endpoint: str, query: str, articles_returned: int,
                     response_time_ms: int, success: bool = True, error_message: str = None):
        """Log API call for monitoring."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        call_id = hashlib.md5(f"{datetime.now().isoformat()}{endpoint}".encode()).hexdigest()

        cursor.execute('''
            INSERT INTO api_calls_log
            (call_id, timestamp, endpoint, query, articles_returned,
             response_time_ms, success, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            call_id,
            datetime.now(),
            endpoint,
            query,
            articles_returned,
            response_time_ms,
            success,
            error_message
        ))

        conn.commit()
        conn.close()


class TheNewsAPIClient:
    """Client for TheNewsAPI.com integration."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.thenewsapi.com/v1"
        self.session = requests.Session()
        self.quota_mgr = QuotaManager()

    def fetch_articles(self, query: str, language: str = "en",
                      country: str = None, limit: int = 10) -> List[UnifiedEvent]:
        """Fetch articles from TheNewsAPI.com."""
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

            logger.info(f"Fetching from TheNewsAPI.com: {query}")
            response = self.session.get(url, params=params, timeout=15)
            response_time_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                data = response.json()
                articles = data.get('data', [])

                logger.info(f"API returned {len(articles)} articles")

                for article in articles:
                    event = self._normalize_article(article)
                    if event:
                        events.append(event)

                # Log successful call
                self.quota_mgr.log_api_call(
                    endpoint=url,
                    query=query,
                    articles_returned=len(articles),
                    response_time_ms=response_time_ms,
                    success=True
                )

            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.error(f"API error: {error_msg}")

                self.quota_mgr.log_api_call(
                    endpoint=url,
                    query=query,
                    articles_returned=0,
                    response_time_ms=response_time_ms,
                    success=False,
                    error_message=error_msg
                )

        except Exception as e:
            logger.error(f"API request failed: {e}")
            self.quota_mgr.log_api_call(
                endpoint=url if 'url' in locals() else 'unknown',
                query=query,
                articles_returned=0,
                response_time_ms=int((time.time() - start_time) * 1000),
                success=False,
                error_message=str(e)
            )

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

            # Simple country detection
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
                sentiment=None,
                summary=article.get('description', ''),
                content_hash=hashlib.md5(content.encode()).hexdigest(),
                fetch_channel=SourceChannel.API,
                fetch_timestamp=datetime.now()
            )

            return event

        except Exception as e:
            logger.error(f"Failed to normalize article: {e}")
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
        return 'USA'  # Default

    def _get_country_domains(self, country: str) -> str:
        """Get domains for specific country."""
        country_domains = {
            'DEU': 'dw.com,spiegel.de,faz.net,zeit.de',
            'GBR': 'bbc.com,theguardian.com,independent.co.uk',
            'FRA': 'lemonde.fr,lefigaro.fr,liberation.fr',
            'USA': 'cnn.com,nytimes.com,washingtonpost.com'
        }
        return country_domains.get(country, '')


class APISourceRegistry:
    """Source registry with TheNewsAPI.com integration."""

    def __init__(self, api_key: str, db_path: str = "api_registry.db"):
        self.api_key = api_key
        self.api_client = TheNewsAPIClient(api_key)
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
                api_coverage BOOLEAN DEFAULT TRUE,
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

        conn.commit()
        conn.close()

    def fetch_articles(self, query: str, country: str = None,
                      language: str = "en", max_articles: int = 10) -> List[UnifiedEvent]:
        """Fetch articles using API-first approach."""
        # Try API first
        events = self.api_client.fetch_articles(
            query=query,
            language=language,
            country=country,
            limit=max_articles
        )

        if events:
            logger.info(f"API returned {len(events)} articles for query: {query}")
        else:
            logger.info(f"API returned no articles, could implement RSS fallback here")

        return events[:max_articles]


def test_thenewsapi():
    """Test TheNewsAPI.com integration."""
    api_key = "BAV2J2VwecIEtxHVm1zOMGERfU52TA88zmW43Fbw"

    print("🌐 TESTING THENEWSAPI.COM INTEGRATION")
    print("=" * 60)

    registry = APISourceRegistry(api_key)

    # Test German politics
    print("\n🇩🇪 Testing German politics articles...")
    events = registry.fetch_articles("Germany politics", country="DEU", max_articles=10)

    print(f"\n📰 FOUND {len(events)} GERMAN POLITICS ARTICLES")
    print("=" * 50)

    for i, event in enumerate(events, 1):
        print(f"\n{i}. {event.title}")
        print(f"   Source: {event.domain}")
        print(f"   Published: {event.published_at.strftime('%Y-%m-%d %H:%M')}")
        print(f"   Countries: {event.target_countries}")
        print(f"   URL: {event.url}")
        if event.summary:
            summary = event.summary[:100] + "..." if len(event.summary) > 100 else event.summary
            print(f"   Summary: {summary}")

    return len(events)


if __name__ == "__main__":
    test_thenewsapi()