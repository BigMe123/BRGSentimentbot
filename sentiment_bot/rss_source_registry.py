#!/usr/bin/env python3
"""
RSS Source Registry
===================
Pure RSS-based news collection system for BSG Bot.
No API dependencies - RSS feeds only.
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
import requests
import xml.etree.ElementTree as ET
import feedparser
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)


class SourceChannel(Enum):
    """Source data channel types."""
    RSS = "rss"
    NONE = "none"


@dataclass
class Source:
    """Represents an RSS news source."""
    source_id: str
    domain: str
    country: str
    language: str
    channel: SourceChannel
    reliability_score: float  # 0.0 to 1.0
    audience_estimate: int
    rss_endpoints: List[str] = field(default_factory=list)
    last_checked: Optional[datetime] = None
    success_rate: float = 1.0
    avg_articles_per_fetch: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedEvent:
    """Normalized event structure for RSS sources."""
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
    """Fetches and parses RSS feeds from news sources."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'BSG-RSS-Bot/1.0'})

    def fetch_rss_articles(self, rss_url: str, source_domain: str,
                          query: str = None, max_articles: int = 10) -> List[UnifiedEvent]:
        """Fetch articles from RSS feed."""
        events = []

        try:
            logger.info(f"Fetching RSS from {source_domain}: {rss_url}")

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

            logger.info(f"Found {len(events)} articles from {source_domain}")

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


class RSSSourceRegistry:
    """RSS-only source registry."""

    def __init__(self, db_path: str = "rss_source_registry.db"):
        self.db_path = db_path
        self.fetcher = RSSFetcher()
        self.init_database()

    def init_database(self):
        """Initialize RSS source registry database."""
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

    def fetch_articles(self, query: str, country: str = None,
                      days_back: int = 7, max_articles: int = 10) -> List[UnifiedEvent]:
        """Fetch articles from RSS sources."""
        events = []

        # Get relevant sources
        sources = self.get_sources_by_country(country) if country else self.get_all_sources()

        for source in sources[:5]:  # Try first 5 sources
            if len(events) >= max_articles:
                break

            for rss_url in source.rss_endpoints:
                source_events = self.fetcher.fetch_rss_articles(
                    rss_url, source.domain, query, max_articles - len(events)
                )
                events.extend(source_events)

                if len(events) >= max_articles:
                    break

        # Filter by date
        cutoff_date = datetime.now() - timedelta(days=days_back)
        recent_events = [e for e in events if e.published_at >= cutoff_date]

        return recent_events[:max_articles]

    def get_sources_by_country(self, country: str) -> List[Source]:
        """Get sources for a specific country."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT source_id, domain, country, language, channel, reliability_score,
                   audience_estimate, rss_endpoints, last_checked,
                   success_rate, avg_articles_per_fetch, metadata
            FROM sources
            WHERE country = ? AND rss_endpoints != '[]'
            ORDER BY reliability_score DESC, audience_estimate DESC
        ''', (country,))

        return self._build_sources_from_rows(cursor.fetchall(), conn)

    def get_all_sources(self) -> List[Source]:
        """Get all sources with RSS feeds."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT source_id, domain, country, language, channel, reliability_score,
                   audience_estimate, rss_endpoints, last_checked,
                   success_rate, avg_articles_per_fetch, metadata
            FROM sources
            WHERE rss_endpoints != '[]' AND rss_endpoints IS NOT NULL
            ORDER BY reliability_score DESC, audience_estimate DESC
        ''')

        return self._build_sources_from_rows(cursor.fetchall(), conn)

    def _build_sources_from_rows(self, rows: List[Tuple], conn) -> List[Source]:
        """Build Source objects from database rows."""
        sources = []
        for row in rows:
            try:
                sources.append(Source(
                    source_id=row[0],
                    domain=row[1],
                    country=row[2],
                    language=row[3],
                    channel=SourceChannel(row[4]),
                    reliability_score=row[5],
                    audience_estimate=row[6],
                    rss_endpoints=json.loads(row[7]) if row[7] else [],
                    last_checked=datetime.fromisoformat(row[8]) if row[8] else None,
                    success_rate=row[9],
                    avg_articles_per_fetch=row[10],
                    metadata=json.loads(row[11]) if row[11] else {}
                ))
            except Exception as e:
                logger.error(f"Error building source from row: {e}")
                continue

        conn.close()
        return sources


def initialize_rss_registry_from_master_sources():
    """Initialize RSS registry from existing master sources YAML."""
    import yaml

    registry = RSSSourceRegistry()

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

            # Create RSS-only source
            source = Source(
                source_id=hashlib.md5(domain.encode()).hexdigest(),
                domain=domain,
                country=country_code,
                language=source_info.get('language', 'en'),
                channel=SourceChannel.RSS,
                reliability_score=source_info.get('priority', 0.5),
                audience_estimate=source_info.get('audience', 10000),
                rss_endpoints=source_info.get('rss_endpoints', []),
                metadata={
                    'region': source_info.get('region', 'global'),
                    'topics': source_info.get('topics', []),
                    'name': source_info.get('name', domain)
                }
            )

            # Register source in database
            conn = sqlite3.connect(registry.db_path)
            cursor = conn.cursor()

            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO sources
                    (source_id, domain, country, language, channel, reliability_score,
                     audience_estimate, rss_endpoints, success_rate, avg_articles_per_fetch,
                     metadata, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    source.source_id,
                    source.domain,
                    source.country,
                    source.language,
                    source.channel.value,
                    source.reliability_score,
                    source.audience_estimate,
                    json.dumps(source.rss_endpoints),
                    source.success_rate,
                    source.avg_articles_per_fetch,
                    json.dumps(source.metadata),
                    datetime.now()
                ))
                conn.commit()
                logger.info(f"Registered RSS source: {domain}")
            except Exception as e:
                logger.error(f"Failed to register {domain}: {e}")
            finally:
                conn.close()

    return registry


if __name__ == "__main__":
    # Test RSS system
    print("Initializing RSS-only source registry...")
    registry = initialize_rss_registry_from_master_sources()

    # Test German politics fetch
    print("\nTesting German politics article fetch...")
    events = registry.fetch_articles("Germany politics", country="DEU", max_articles=5)

    print(f"Found {len(events)} articles:")
    for i, event in enumerate(events, 1):
        print(f"{i}. {event.title[:60]}...")
        print(f"   Source: {event.domain}")
        print(f"   Published: {event.published_at}")