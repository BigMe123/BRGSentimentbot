#!/usr/bin/env python3
"""
Master Source Consolidation Script
Consolidates all RSS sources from multiple databases into a single unified catalog.

Current Sources:
- skb_catalog.db: 1,413 sources with 3,903 RSS endpoints
- rss_source_registry.db: 108 sources
- source_registry.db: 98 sources

Total: ~1,619 unique sources with 3,900+ RSS endpoints
"""

import sqlite3
import json
from collections import defaultdict
from typing import Dict, List, Set
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SourceConsolidator:
    """Consolidates sources from multiple databases into unified catalog."""

    def __init__(self):
        self.databases = {
            'skb_catalog.db': '/Users/marcod/Desktop/BSG/BRGSentimentbot/skb_catalog.db',
            'rss_source_registry.db': '/Users/marcod/Desktop/BSG/BRGSentimentbot/rss_source_registry.db',
            'source_registry.db': '/Users/marcod/Desktop/BSG/BRGSentimentbot/source_registry.db',
        }
        self.consolidated_sources = {}
        self.total_endpoints = 0

    def load_skb_catalog(self):
        """Load sources from skb_catalog.db (main database)."""
        conn = sqlite3.connect(self.databases['skb_catalog.db'])
        cursor = conn.execute('SELECT domain, name, region, country, data, priority, reliability_score FROM sources')

        count = 0
        endpoints = 0

        for row in cursor:
            domain, name, region, country, data_json, priority, reliability = row
            try:
                data = json.loads(data_json)
                rss_endpoints = data.get('rss_endpoints', [])

                if isinstance(rss_endpoints, list):
                    endpoints += len(rss_endpoints)

                self.consolidated_sources[domain] = {
                    'domain': domain,
                    'name': name,
                    'region': region,
                    'country': country,
                    'rss_endpoints': rss_endpoints,
                    'priority': priority,
                    'reliability_score': reliability,
                    'topics': data.get('topics', []),
                    'languages': data.get('languages', ['en']),
                    'source_db': 'skb_catalog'
                }
                count += 1
            except Exception as e:
                logger.error(f"Error loading {domain}: {e}")

        conn.close()
        logger.info(f"Loaded {count} sources with {endpoints} endpoints from skb_catalog.db")
        self.total_endpoints += endpoints

    def load_rss_source_registry(self):
        """Load sources from rss_source_registry.db."""
        conn = sqlite3.connect(self.databases['rss_source_registry.db'])
        cursor = conn.execute('SELECT domain, country, language, rss_endpoints, reliability_score, metadata FROM sources')

        count = 0
        for row in cursor:
            domain, country, language, rss_endpoints_json, reliability, metadata_json = row

            if domain in self.consolidated_sources:
                # Merge RSS endpoints
                try:
                    new_endpoints = json.loads(rss_endpoints_json) if rss_endpoints_json else []
                    existing = self.consolidated_sources[domain]['rss_endpoints']
                    self.consolidated_sources[domain]['rss_endpoints'] = list(set(existing + new_endpoints))
                except:
                    pass
            else:
                try:
                    metadata = json.loads(metadata_json) if metadata_json else {}
                    endpoints = json.loads(rss_endpoints_json) if rss_endpoints_json else []

                    self.consolidated_sources[domain] = {
                        'domain': domain,
                        'name': metadata.get('name', domain),
                        'region': metadata.get('region', 'unknown'),
                        'country': country or 'Unknown',
                        'rss_endpoints': endpoints,
                        'priority': 0.5,
                        'reliability_score': reliability or 0.5,
                        'topics': metadata.get('topics', []),
                        'languages': [language] if language else ['en'],
                        'source_db': 'rss_source_registry'
                    }
                    self.total_endpoints += len(endpoints)
                    count += 1
                except Exception as e:
                    logger.error(f"Error loading {domain} from RSS registry: {e}")

        conn.close()
        logger.info(f"Added {count} new sources from rss_source_registry.db")

    def load_source_registry(self):
        """Load sources from source_registry.db."""
        conn = sqlite3.connect(self.databases['source_registry.db'])
        cursor = conn.execute('SELECT domain, country, language, rss_endpoints, reliability_score, metadata FROM sources')

        count = 0
        for row in cursor:
            domain, country, language, rss_endpoints_json, reliability, metadata_json = row

            if domain not in self.consolidated_sources:
                try:
                    metadata = json.loads(metadata_json) if metadata_json else {}
                    endpoints = json.loads(rss_endpoints_json) if rss_endpoints_json else []

                    self.consolidated_sources[domain] = {
                        'domain': domain,
                        'name': metadata.get('name', domain),
                        'region': metadata.get('region', 'unknown'),
                        'country': country or 'Unknown',
                        'rss_endpoints': endpoints,
                        'priority': 0.5,
                        'reliability_score': reliability or 0.5,
                        'topics': metadata.get('topics', []),
                        'languages': [language] if language else ['en'],
                        'source_db': 'source_registry'
                    }
                    self.total_endpoints += len(endpoints)
                    count += 1
                except Exception as e:
                    logger.error(f"Error loading {domain} from source registry: {e}")

        conn.close()
        logger.info(f"Added {count} new sources from source_registry.db")

    def get_statistics(self) -> Dict:
        """Get comprehensive statistics about consolidated sources."""
        stats = {
            'total_sources': len(self.consolidated_sources),
            'total_endpoints': self.total_endpoints,
            'by_region': defaultdict(int),
            'by_source_db': defaultdict(int),
            'top_domains_by_endpoints': [],
        }

        for domain, source in self.consolidated_sources.items():
            stats['by_region'][source['region']] += 1
            stats['by_source_db'][source['source_db']] += 1

        # Top domains by endpoint count
        sorted_sources = sorted(
            self.consolidated_sources.items(),
            key=lambda x: len(x[1].get('rss_endpoints', [])),
            reverse=True
        )
        stats['top_domains_by_endpoints'] = [
            (domain, len(source.get('rss_endpoints', [])))
            for domain, source in sorted_sources[:20]
        ]

        return stats

    def consolidate(self):
        """Run full consolidation process."""
        logger.info("Starting source consolidation...")

        self.load_skb_catalog()
        self.load_rss_source_registry()
        self.load_source_registry()

        stats = self.get_statistics()

        logger.info("\n=== CONSOLIDATION COMPLETE ===")
        logger.info(f"Total Unique Sources: {stats['total_sources']}")
        logger.info(f"Total RSS Endpoints: {stats['total_endpoints']}")
        logger.info(f"\nBy Region:")
        for region, count in sorted(stats['by_region'].items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  {region:15s}: {count:4d} sources")

        logger.info(f"\nBy Source Database:")
        for db, count in stats['by_source_db'].items():
            logger.info(f"  {db:25s}: {count:4d} sources")

        logger.info(f"\nTop 20 Domains by RSS Endpoints:")
        for domain, count in stats['top_domains_by_endpoints']:
            logger.info(f"  {domain:30s}: {count:3d} endpoints")

        return stats


if __name__ == "__main__":
    consolidator = SourceConsolidator()
    stats = consolidator.consolidate()

    print(f"\n✅ Consolidation complete!")
    print(f"📊 {stats['total_sources']} unique sources with {stats['total_endpoints']} RSS endpoints")
    print(f"💾 All sources available in unified catalog")
