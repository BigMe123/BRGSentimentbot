#!/usr/bin/env python3
"""
Master Source Manager - Single source of truth for all news sources
This module provides unified access to all configured sources from the SKB catalog
"""

import sqlite3
import json
import yaml
import os
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class NewsSource:
    """Unified news source representation."""

    domain: str
    name: str
    region: str
    country: str
    priority: float = 0.5
    topics: List[str] = field(default_factory=list)
    rss_feeds: List[str] = field(default_factory=list)
    language: str = "en"
    category: str = "general"
    policy: str = "allow"
    reliability_score: float = 0.5
    freshness_score: float = 0.5
    validation_status: str = "active"
    connector_type: Optional[str] = None  # reddit, hackernews, gdelt, etc.

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return asdict(self)

    def to_yaml_dict(self) -> Dict:
        """Convert to YAML-compatible dictionary."""
        return {
            "domain": self.domain,
            "name": self.name,
            "topics": self.topics,
            "priority": round(self.priority, 2),
            "policy": self.policy,
            "region": self.region,
            "country": self.country,
            "language": self.language,
            "rss_endpoints": self.rss_feeds if self.rss_feeds else None,
        }


class MasterSourceManager:
    """
    Centralized source manager that provides a single interface to all news sources.
    This is the ONLY place where sources should be defined and accessed.
    """

    def __init__(self, db_path: str = "skb_catalog.db", config_dir: str = "config"):
        """Initialize the master source manager."""
        self.db_path = db_path
        self.config_dir = Path(config_dir)
        self.sources: Dict[str, NewsSource] = {}
        self._load_all_sources()

    def _load_all_sources(self):
        """Load all sources from the SKB catalog database."""
        if not os.path.exists(self.db_path):
            logger.warning(f"SKB catalog database not found at {self.db_path}")
            self._create_default_catalog()

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Load all sources from database
            cursor.execute(
                """
                SELECT domain, name, region, country, data, priority,
                       policy, freshness_score, reliability_score, 
                       validation_status
                FROM sources
                WHERE validation_status = 'active'
                ORDER BY priority DESC
            """
            )

            for row in cursor.fetchall():
                try:
                    # Parse JSON data field
                    data = json.loads(row["data"]) if row["data"] else {}

                    source = NewsSource(
                        domain=row["domain"],
                        name=row["name"],
                        region=row["region"],
                        country=row["country"] or "Unknown",
                        priority=row["priority"],
                        topics=data.get("topics", ["general"]),
                        rss_feeds=data.get("rss_endpoints", data.get("rss_feeds", [])),
                        language=data.get("language", "en"),
                        category=data.get("category", "general"),
                        policy=row["policy"],
                        reliability_score=row["reliability_score"],
                        freshness_score=row["freshness_score"],
                        validation_status=row["validation_status"],
                    )

                    # Determine connector type based on domain
                    source.connector_type = self._determine_connector_type(
                        source.domain
                    )

                    self.sources[source.domain] = source

                except Exception as e:
                    logger.error(f"Error loading source {row['domain']}: {e}")
                    continue

            conn.close()
            logger.info(f"Loaded {len(self.sources)} active sources from SKB catalog")

        except Exception as e:
            logger.error(f"Error loading sources from database: {e}")
            self._load_fallback_sources()

    def _determine_connector_type(self, domain: str) -> Optional[str]:
        """Determine which connector to use based on domain."""
        domain_lower = domain.lower()

        # Special connectors
        if "reddit.com" in domain_lower:
            return "reddit"
        elif "hackernews" in domain_lower or "ycombinator" in domain_lower:
            return "hackernews"
        elif "youtube.com" in domain_lower:
            return "youtube"
        elif "twitter.com" in domain_lower or "x.com" in domain_lower:
            return "twitter"
        elif "mastodon" in domain_lower:
            return "mastodon"
        elif "bluesky" in domain_lower:
            return "bluesky"
        elif "wikipedia.org" in domain_lower:
            return "wikipedia"
        elif "stackexchange" in domain_lower or "stackoverflow" in domain_lower:
            return "stackexchange"
        elif "gdelt" in domain_lower:
            return "gdelt"
        elif any(x in domain_lower for x in ["arxiv.org", "nature.com", "science.org"]):
            return "academic"
        else:
            # Default to RSS/web scraping
            return "rss"

    def _create_default_catalog(self):
        """Create a default catalog database if none exists."""
        logger.info("Creating default SKB catalog database...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create schema
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sources (
                domain TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                region TEXT NOT NULL,
                country TEXT,
                data JSON NOT NULL,
                priority REAL DEFAULT 0.5,
                policy TEXT DEFAULT 'allow',
                historical_yield REAL DEFAULT 0.0,
                freshness_score REAL DEFAULT 0.5,
                reliability_score REAL DEFAULT 0.5,
                validation_status TEXT DEFAULT 'active',
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_count INTEGER DEFAULT 0
            )
        """
        )

        # Add indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_region ON sources(region)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_priority ON sources(priority DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_validation ON sources(validation_status)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy ON sources(policy)")

        conn.commit()
        conn.close()

    def _load_fallback_sources(self):
        """Load fallback sources from YAML files if database fails."""
        logger.info("Loading fallback sources from YAML files...")

        # Try to load from various YAML files
        yaml_files = [
            self.config_dir / "skb_sources.yaml",
            self.config_dir / "sources.yaml",
            self.config_dir / "all_sources.yaml",
        ]

        for yaml_file in yaml_files:
            if yaml_file.exists():
                try:
                    with open(yaml_file, "r") as f:
                        data = yaml.safe_load(f)

                    if "sources" in data:
                        for source_data in data["sources"]:
                            source = NewsSource(
                                domain=source_data["domain"],
                                name=source_data.get("name", source_data["domain"]),
                                region=source_data.get("region", "unknown"),
                                country=source_data.get("country", "Unknown"),
                                priority=source_data.get("priority", 0.5),
                                topics=source_data.get("topics", ["general"]),
                                rss_feeds=source_data.get("rss_endpoints", []),
                                language=source_data.get("language", "en"),
                                category=source_data.get("category", "general"),
                                policy=source_data.get("policy", "allow"),
                            )
                            source.connector_type = self._determine_connector_type(
                                source.domain
                            )
                            self.sources[source.domain] = source

                    logger.info(f"Loaded {len(self.sources)} sources from {yaml_file}")
                    break

                except Exception as e:
                    logger.error(
                        f"Error loading fallback sources from {yaml_file}: {e}"
                    )
                    continue

    # === PUBLIC API METHODS ===

    def get_all_sources(self) -> List[NewsSource]:
        """Get all active sources."""
        return list(self.sources.values())

    def get_sources_by_region(self, region: str) -> List[NewsSource]:
        """Get sources filtered by region."""
        return [s for s in self.sources.values() if s.region == region]

    def get_sources_by_country(self, country: str) -> List[NewsSource]:
        """Get sources filtered by country."""
        return [s for s in self.sources.values() if s.country == country]

    def get_sources_by_topic(self, topic: str) -> List[NewsSource]:
        """Get sources that cover a specific topic."""
        return [s for s in self.sources.values() if topic in s.topics]

    def get_sources_by_language(self, language: str) -> List[NewsSource]:
        """Get sources in a specific language."""
        return [s for s in self.sources.values() if s.language == language]

    def get_sources_by_connector(self, connector_type: str) -> List[NewsSource]:
        """Get sources that use a specific connector type."""
        return [s for s in self.sources.values() if s.connector_type == connector_type]

    def get_high_priority_sources(self, min_priority: float = 0.7) -> List[NewsSource]:
        """Get high priority sources above a threshold."""
        return sorted(
            [s for s in self.sources.values() if s.priority >= min_priority],
            key=lambda x: x.priority,
            reverse=True,
        )

    def get_source(self, domain: str) -> Optional[NewsSource]:
        """Get a specific source by domain."""
        return self.sources.get(domain)

    def get_sources_for_bot(
        self,
        regions: Optional[List[str]] = None,
        topics: Optional[List[str]] = None,
        min_priority: float = 0.0,
        max_sources: Optional[int] = None,
    ) -> List[Dict]:
        """
        Get sources formatted for the sentiment bot.
        This is the main method that should be used by the bot.
        """
        sources = list(self.sources.values())

        # Filter by regions
        if regions:
            sources = [s for s in sources if s.region in regions]

        # Filter by topics
        if topics:
            sources = [s for s in sources if any(t in s.topics for t in topics)]

        # Filter by priority
        sources = [s for s in sources if s.priority >= min_priority]

        # Sort by priority
        sources = sorted(sources, key=lambda x: x.priority, reverse=True)

        # Limit number of sources
        if max_sources:
            sources = sources[:max_sources]

        # Convert to bot format
        bot_sources = []
        for source in sources:
            bot_source = {
                "domain": source.domain,
                "name": source.name,
                "topics": source.topics,
                "priority": source.priority,
                "policy": source.policy,
                "region": source.region,
                "rss_endpoints": source.rss_feeds if source.rss_feeds else None,
                "connector_type": source.connector_type,
            }
            bot_sources.append(bot_source)

        return bot_sources

    def export_to_yaml(self, output_path: Optional[str] = None) -> str:
        """Export all sources to YAML format."""
        sources_list = []

        for source in sorted(
            self.sources.values(), key=lambda x: x.priority, reverse=True
        ):
            sources_list.append(source.to_yaml_dict())

        yaml_data = {
            "version": "2.0",
            "description": "Master source list for BSG Sentiment Bot",
            "total_sources": len(sources_list),
            "sources": sources_list,
        }

        yaml_content = yaml.dump(yaml_data, default_flow_style=False, sort_keys=False)

        if output_path:
            with open(output_path, "w") as f:
                f.write(yaml_content)
            logger.info(f"Exported {len(sources_list)} sources to {output_path}")

        return yaml_content

    def get_statistics(self) -> Dict:
        """Get statistics about the source collection."""
        stats = {
            "total_sources": len(self.sources),
            "by_region": {},
            "by_country": {},
            "by_topic": {},
            "by_language": {},
            "by_connector": {},
            "priority_ranges": {
                "high": 0,  # >= 0.7
                "medium": 0,  # 0.4 - 0.7
                "low": 0,  # < 0.4
            },
            "with_rss": 0,
            "without_rss": 0,
        }

        # Count by various dimensions
        for source in self.sources.values():
            # Region
            stats["by_region"][source.region] = (
                stats["by_region"].get(source.region, 0) + 1
            )

            # Country
            stats["by_country"][source.country] = (
                stats["by_country"].get(source.country, 0) + 1
            )

            # Topics
            for topic in source.topics:
                stats["by_topic"][topic] = stats["by_topic"].get(topic, 0) + 1

            # Language
            stats["by_language"][source.language] = (
                stats["by_language"].get(source.language, 0) + 1
            )

            # Connector
            connector = source.connector_type or "unknown"
            stats["by_connector"][connector] = (
                stats["by_connector"].get(connector, 0) + 1
            )

            # Priority ranges
            if source.priority >= 0.7:
                stats["priority_ranges"]["high"] += 1
            elif source.priority >= 0.4:
                stats["priority_ranges"]["medium"] += 1
            else:
                stats["priority_ranges"]["low"] += 1

            # RSS feeds
            if source.rss_feeds:
                stats["with_rss"] += 1
            else:
                stats["without_rss"] += 1

        return stats

    def reload(self):
        """Reload all sources from the database."""
        self.sources.clear()
        self._load_all_sources()
        logger.info(f"Reloaded {len(self.sources)} sources")

    def add_source(self, source: NewsSource) -> bool:
        """Add or update a source in the catalog."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            data = {
                "topics": source.topics,
                "category": source.category,
                "language": source.language,
                "rss_feeds": source.rss_feeds,
            }

            cursor.execute(
                """
                INSERT OR REPLACE INTO sources 
                (domain, name, region, country, data, priority, policy,
                 freshness_score, reliability_score, validation_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    source.domain,
                    source.name,
                    source.region,
                    source.country,
                    json.dumps(data),
                    source.priority,
                    source.policy,
                    source.freshness_score,
                    source.reliability_score,
                    source.validation_status,
                ),
            )

            conn.commit()
            conn.close()

            # Update in-memory cache
            self.sources[source.domain] = source

            logger.info(f"Added/updated source: {source.domain}")
            return True

        except Exception as e:
            logger.error(f"Error adding source {source.domain}: {e}")
            return False


# === SINGLETON INSTANCE ===
_master_source_manager: Optional[MasterSourceManager] = None


def get_master_sources() -> MasterSourceManager:
    """Get the singleton instance of the master source manager."""
    global _master_source_manager
    if _master_source_manager is None:
        _master_source_manager = MasterSourceManager()
    return _master_source_manager


def get_sources_for_config(config: Dict) -> List[Dict]:
    """
    Get sources based on bot configuration.
    This is the main entry point for the sentiment bot.
    """
    manager = get_master_sources()

    # Extract filtering parameters from config
    regions = config.get("regions", None)
    topics = config.get("topics", None)
    min_priority = config.get("min_priority", 0.0)
    max_sources = config.get("max_sources", None)

    return manager.get_sources_for_bot(
        regions=regions,
        topics=topics,
        min_priority=min_priority,
        max_sources=max_sources,
    )


# === CONVENIENCE FUNCTIONS ===


def reload_sources():
    """Reload all sources from the database."""
    manager = get_master_sources()
    manager.reload()


def get_source_statistics() -> Dict:
    """Get statistics about available sources."""
    manager = get_master_sources()
    return manager.get_statistics()


def export_master_list(output_path: str = "config/master_sources.yaml"):
    """Export the master source list to YAML."""
    manager = get_master_sources()
    return manager.export_to_yaml(output_path)


def list_high_priority_sources(min_priority: float = 0.7) -> List[NewsSource]:
    """List all high priority sources."""
    manager = get_master_sources()
    return manager.get_high_priority_sources(min_priority)


if __name__ == "__main__":
    """Test and display source statistics."""
    import pprint

    print("🌍 Master Source Manager")
    print("=" * 60)

    manager = get_master_sources()
    stats = manager.get_statistics()

    print(f"\n📊 Source Statistics:")
    print(f"Total sources: {stats['total_sources']}")

    print(f"\n🌍 By Region:")
    for region, count in sorted(
        stats["by_region"].items(), key=lambda x: x[1], reverse=True
    ):
        print(f"  {region:15} {count:4} sources")

    print(f"\n⭐ By Priority:")
    print(f"  High (≥0.7):    {stats['priority_ranges']['high']:4} sources")
    print(f"  Medium (0.4-0.7): {stats['priority_ranges']['medium']:4} sources")
    print(f"  Low (<0.4):     {stats['priority_ranges']['low']:4} sources")

    print(f"\n📡 RSS Feeds:")
    print(f"  With RSS:       {stats['with_rss']:4} sources")
    print(f"  Without RSS:    {stats['without_rss']:4} sources")

    print(f"\n🔌 By Connector Type:")
    for connector, count in sorted(
        stats["by_connector"].items(), key=lambda x: x[1], reverse=True
    )[:10]:
        print(f"  {connector:15} {count:4} sources")

    print(f"\n💎 Top 10 High-Priority Sources:")
    for i, source in enumerate(list_high_priority_sources()[:10], 1):
        rss_indicator = "📡" if source.rss_feeds else "❌"
        print(f"  {i:2}. {source.domain:30} ({source.priority:.2f}) {rss_indicator}")

    # Export to YAML
    export_master_list()
    print(f"\n✅ Master source list exported to config/master_sources.yaml")
