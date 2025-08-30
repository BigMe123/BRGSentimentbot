"""
Unified Source Knowledge Base (SKB) Catalog with SQLite storage and precomputed indexes.
This is the SINGLE SOURCE OF TRUTH for all source management.
"""

import sqlite3
import json
import yaml
import hashlib
import mmap
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field, asdict, fields
from collections import defaultdict
import logging
from datetime import datetime, timedelta
import re
from difflib import get_close_matches

logger = logging.getLogger(__name__)


@dataclass
class SourceRecord:
    """Complete source record with all metadata."""

    domain: str
    name: str
    region: str
    country: str = ""
    languages: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    primary_sections: List[str] = field(default_factory=list)
    rss_endpoints: List[str] = field(default_factory=list)
    sitemap_endpoints: List[str] = field(default_factory=list)
    priority: float = 0.5
    policy: str = "allow"  # allow/deny/js_allowed/api_only/respect_robots/headless
    rate_limit_ms: int = 300
    max_docs_per_run: int = 30
    notes: str = ""

    # Runtime stats (updated periodically)
    historical_yield: float = 0.0  # avg fresh words per run
    freshness_score: float = 0.5  # how recently updated
    reliability_score: float = 0.5  # success rate
    last_success: Optional[str] = None  # ISO timestamp
    last_failure: Optional[str] = None
    error_count: int = 0

    # Discovery metadata
    discovered_at: Optional[str] = None  # ISO timestamp
    discovery_method: Optional[str] = (
        None  # "manual", "rss_autodiscovery", "sitemap", "crawl"
    )
    validation_status: str = "active"  # active/staging/parked

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceRecord":
        # Filter out unexpected fields
        valid_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)


class SKBCatalog:
    """High-performance SKB catalog with SQLite backend and precomputed indexes."""

    SCHEMA_VERSION = 2

    def __init__(self, db_path: str = "skb_catalog.db", cache_ttl: int = 300):
        self.db_path = db_path
        self.cache_ttl = cache_ttl  # seconds
        self.conn = None
        self._cache = {}
        self._cache_timestamps = {}
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database with schema."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # Enable WAL mode for better concurrency
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")

        # Create main sources table
        self.conn.execute(
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
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create indexes for fast lookups
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_region ON sources(region)")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_priority ON sources(priority DESC)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_validation ON sources(validation_status)"
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_policy ON sources(policy)")

        # Create inverted index tables
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS topic_index (
                topic TEXT NOT NULL,
                domain TEXT NOT NULL,
                PRIMARY KEY (topic, domain),
                FOREIGN KEY (domain) REFERENCES sources(domain)
            )
        """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS language_index (
                language TEXT NOT NULL,
                domain TEXT NOT NULL,
                PRIMARY KEY (language, domain),
                FOREIGN KEY (domain) REFERENCES sources(domain)
            )
        """
        )

        # Create metadata table
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """
        )

        # Store schema version
        self.conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("schema_version", str(self.SCHEMA_VERSION)),
        )

        self.conn.commit()

    def import_from_yaml(self, yaml_path: str):
        """Import sources from YAML SKB file."""
        logger.info(f"Importing SKB from {yaml_path}")

        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)

        # Start transaction
        self.conn.execute("BEGIN TRANSACTION")

        try:
            # Clear existing data
            self.conn.execute("DELETE FROM sources")
            self.conn.execute("DELETE FROM topic_index")
            self.conn.execute("DELETE FROM language_index")

            # Process regions
            for region_key, region_data in data.get("regions", {}).items():
                for source_data in region_data.get("sources", []):
                    # Create source record
                    source = SourceRecord(
                        domain=source_data["domain"],
                        name=source_data["name"],
                        region=region_key,
                        country=source_data.get("country", ""),
                        languages=source_data.get("languages", []),
                        topics=source_data.get("topics", []),
                        primary_sections=source_data.get("primary_sections", []),
                        rss_endpoints=source_data.get("rss_endpoints", []),
                        sitemap_endpoints=source_data.get("sitemap_endpoints", []),
                        priority=source_data.get("priority", 0.5),
                        policy=source_data.get("policy", "allow"),
                        rate_limit_ms=source_data.get("rate_limit_ms", 300),
                        max_docs_per_run=source_data.get("max_docs_per_run", 30),
                        notes=source_data.get("notes", ""),
                    )

                    # Insert into sources table (replace if exists)
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO sources (
                            domain, name, region, country, data, priority, 
                            policy, historical_yield, freshness_score, 
                            reliability_score, validation_status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            source.domain,
                            source.name,
                            source.region,
                            source.country,
                            json.dumps(source.to_dict()),
                            source.priority,
                            source.policy,
                            source.historical_yield,
                            source.freshness_score,
                            source.reliability_score,
                            source.validation_status,
                        ),
                    )

                    # Update topic index
                    for topic in source.topics:
                        self.conn.execute(
                            "INSERT OR IGNORE INTO topic_index (topic, domain) VALUES (?, ?)",
                            (topic.lower(), source.domain),
                        )

                    # Update language index
                    for language in source.languages:
                        self.conn.execute(
                            "INSERT OR IGNORE INTO language_index (language, domain) VALUES (?, ?)",
                            (language.lower(), source.domain),
                        )

            # Update metadata
            self.conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                ("last_import", datetime.now().isoformat()),
            )

            self.conn.commit()
            logger.info(
                f"Successfully imported {self.conn.execute('SELECT COUNT(*) FROM sources').fetchone()[0]} sources"
            )

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to import SKB: {e}")
            raise

    def get_sources_by_region(
        self, region: str, limit: Optional[int] = None
    ) -> List[SourceRecord]:
        """Get sources for a specific region, ordered by priority."""
        cache_key = f"region:{region}:{limit}"

        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        query = """
            SELECT data FROM sources 
            WHERE region = ? AND validation_status = 'active'
            ORDER BY priority DESC, reliability_score DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor = self.conn.execute(query, (region,))
        sources = [
            SourceRecord.from_dict(json.loads(row["data"])) for row in cursor.fetchall()
        ]

        self._update_cache(cache_key, sources)
        return sources

    def get_sources_by_topic(
        self, topic: str, limit: Optional[int] = None
    ) -> List[SourceRecord]:
        """Get sources for a specific topic."""
        cache_key = f"topic:{topic}:{limit}"

        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        query = """
            SELECT s.domain, s.name, s.region, s.data FROM sources s
            JOIN topic_index ti ON s.domain = ti.domain
            WHERE ti.topic = ? AND s.validation_status = 'active'
            ORDER BY s.priority DESC, s.reliability_score DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor = self.conn.execute(query, (topic.lower(),))
        sources = []
        for row in cursor.fetchall():
            data = json.loads(row["data"]) if row["data"] else {}
            # Add required fields from columns
            data["domain"] = row["domain"]
            data["name"] = row["name"]
            data["region"] = row["region"]
            sources.append(SourceRecord.from_dict(data))

        self._update_cache(cache_key, sources)
        return sources

    def get_sources_by_criteria(
        self,
        region: Optional[str] = None,
        topics: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        policies: Optional[List[str]] = None,
        min_priority: float = 0.0,
        limit: Optional[int] = None,
    ) -> List[SourceRecord]:
        """Advanced source selection with multiple criteria."""

        # Build query dynamically
        conditions = ["validation_status = 'active'"]
        params = []

        if region:
            conditions.append("region = ?")
            params.append(region)

        if policies:
            placeholders = ",".join(["?" for _ in policies])
            conditions.append(f"policy IN ({placeholders})")
            params.extend(policies)

        conditions.append("priority >= ?")
        params.append(min_priority)

        # Handle topic intersection
        if topics:
            topic_domains = set()
            for topic in topics:
                cursor = self.conn.execute(
                    "SELECT domain FROM topic_index WHERE topic = ?", (topic.lower(),)
                )
                domains = {row[0] for row in cursor.fetchall()}
                if not topic_domains:
                    topic_domains = domains
                else:
                    topic_domains &= domains  # Intersection

            if topic_domains:
                placeholders = ",".join(["?" for _ in topic_domains])
                conditions.append(f"domain IN ({placeholders})")
                params.extend(list(topic_domains))
            else:
                return []  # No sources match all topics

        # Handle language filter
        if languages:
            lang_domains = set()
            for language in languages:
                cursor = self.conn.execute(
                    "SELECT domain FROM language_index WHERE language = ?",
                    (language.lower(),),
                )
                lang_domains.update(row[0] for row in cursor.fetchall())

            if lang_domains:
                placeholders = ",".join(["?" for _ in lang_domains])
                conditions.append(f"domain IN ({placeholders})")
                params.extend(list(lang_domains))

        # Build and execute query
        query = f"""
            SELECT domain, name, region, data FROM sources
            WHERE {' AND '.join(conditions)}
            ORDER BY priority DESC, reliability_score DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor = self.conn.execute(query, params)
        sources = []
        for row in cursor.fetchall():
            data = json.loads(row["data"]) if row["data"] else {}
            # Add required fields from columns
            data["domain"] = row["domain"]
            data["name"] = row["name"]
            data["region"] = row["region"]
            sources.append(SourceRecord.from_dict(data))

        return sources

    def fuzzy_match_topics(self, query: str, threshold: float = 0.6) -> List[str]:
        """Find topics that fuzzy match the query."""
        # Get all unique topics
        cursor = self.conn.execute("SELECT DISTINCT topic FROM topic_index")
        all_topics = [row[0] for row in cursor.fetchall()]

        # Normalize query
        query_normalized = query.lower().strip()

        # Find close matches
        matches = get_close_matches(
            query_normalized, all_topics, n=10, cutoff=threshold
        )

        # Also check for substring matches
        substring_matches = [
            t for t in all_topics if query_normalized in t or t in query_normalized
        ]

        # Combine and deduplicate
        combined = list(set(matches + substring_matches))
        return combined[:10]  # Return top 10 matches

    def update_source_stats(
        self,
        domain: str,
        yield_words: float = None,
        success: bool = None,
        error_msg: str = None,
    ):
        """Update runtime statistics for a source."""
        cursor = self.conn.execute(
            "SELECT data, historical_yield, reliability_score, error_count FROM sources WHERE domain = ?",
            (domain,),
        )
        row = cursor.fetchone()
        if not row:
            return

        data = json.loads(row["data"])
        historical_yield = row["historical_yield"]
        reliability_score = row["reliability_score"]
        error_count = row["error_count"]

        # Update yield with exponential moving average
        if yield_words is not None:
            historical_yield = 0.7 * historical_yield + 0.3 * yield_words

        # Update reliability score
        if success is not None:
            if success:
                reliability_score = min(1.0, reliability_score * 1.1)
                data["last_success"] = datetime.now().isoformat()
            else:
                reliability_score = max(0.1, reliability_score * 0.9)
                error_count += 1
                data["last_failure"] = datetime.now().isoformat()
                if error_msg:
                    data["last_error"] = error_msg

        # Update freshness score based on last success
        if data.get("last_success"):
            last_success = datetime.fromisoformat(data["last_success"])
            hours_ago = (datetime.now() - last_success).total_seconds() / 3600
            freshness_score = max(0.1, 1.0 - (hours_ago / 168))  # Decay over a week
        else:
            freshness_score = 0.5

        # Update database
        self.conn.execute(
            """
            UPDATE sources 
            SET data = ?, historical_yield = ?, reliability_score = ?, 
                freshness_score = ?, error_count = ?, last_updated = CURRENT_TIMESTAMP
            WHERE domain = ?
        """,
            (
                json.dumps(data),
                historical_yield,
                reliability_score,
                freshness_score,
                error_count,
                domain,
            ),
        )
        self.conn.commit()

        # Invalidate cache
        self._invalidate_cache()

    def promote_source(self, domain: str, new_status: str = "active"):
        """Promote a source from staging to active."""
        self.conn.execute(
            "UPDATE sources SET validation_status = ? WHERE domain = ?",
            (new_status, domain),
        )
        self.conn.commit()
        self._invalidate_cache()

    def park_source(self, domain: str):
        """Park a dead or problematic source."""
        self.conn.execute(
            "UPDATE sources SET validation_status = 'parked' WHERE domain = ?",
            (domain,),
        )
        self.conn.commit()
        self._invalidate_cache()

    def add_discovered_source(self, source: SourceRecord):
        """Add a newly discovered source to staging."""
        source.validation_status = "staging"
        source.discovered_at = datetime.now().isoformat()

        try:
            self.conn.execute(
                """
                INSERT INTO sources (
                    domain, name, region, country, data, priority, 
                    policy, validation_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    source.domain,
                    source.name,
                    source.region,
                    source.country,
                    json.dumps(source.to_dict()),
                    source.priority,
                    source.policy,
                    source.validation_status,
                ),
            )

            # Update indexes
            for topic in source.topics:
                self.conn.execute(
                    "INSERT OR IGNORE INTO topic_index (topic, domain) VALUES (?, ?)",
                    (topic.lower(), source.domain),
                )

            for language in source.languages:
                self.conn.execute(
                    "INSERT OR IGNORE INTO language_index (language, domain) VALUES (?, ?)",
                    (language.lower(), source.domain),
                )

            self.conn.commit()
            self._invalidate_cache()
            return True

        except sqlite3.IntegrityError:
            # Source already exists
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get catalog statistics."""
        stats = {
            "total_sources": self.conn.execute(
                "SELECT COUNT(*) FROM sources"
            ).fetchone()[0],
            "active_sources": self.conn.execute(
                "SELECT COUNT(*) FROM sources WHERE validation_status = 'active'"
            ).fetchone()[0],
            "staging_sources": self.conn.execute(
                "SELECT COUNT(*) FROM sources WHERE validation_status = 'staging'"
            ).fetchone()[0],
            "parked_sources": self.conn.execute(
                "SELECT COUNT(*) FROM sources WHERE validation_status = 'parked'"
            ).fetchone()[0],
            "regions": {},
            "topics": {},
            "avg_reliability": self.conn.execute(
                "SELECT AVG(reliability_score) FROM sources WHERE validation_status = 'active'"
            ).fetchone()[0]
            or 0.0,
            "avg_yield": self.conn.execute(
                "SELECT AVG(historical_yield) FROM sources WHERE validation_status = 'active'"
            ).fetchone()[0]
            or 0.0,
        }

        # Region distribution
        cursor = self.conn.execute(
            """
            SELECT region, COUNT(*) as count 
            FROM sources 
            WHERE validation_status = 'active'
            GROUP BY region
        """
        )
        stats["regions"] = {row["region"]: row["count"] for row in cursor.fetchall()}

        # Topic distribution
        cursor = self.conn.execute(
            """
            SELECT topic, COUNT(*) as count 
            FROM topic_index ti
            JOIN sources s ON ti.domain = s.domain
            WHERE s.validation_status = 'active'
            GROUP BY topic
            ORDER BY count DESC
            LIMIT 20
        """
        )
        stats["topics"] = {row["topic"]: row["count"] for row in cursor.fetchall()}

        return stats

    def _is_cache_valid(self, key: str) -> bool:
        """Check if cache entry is still valid."""
        if key not in self._cache:
            return False

        timestamp = self._cache_timestamps.get(key, 0)
        return (time.time() - timestamp) < self.cache_ttl

    def _update_cache(self, key: str, value: Any):
        """Update cache with new value."""
        self._cache[key] = value
        self._cache_timestamps[key] = time.time()

    def _invalidate_cache(self):
        """Clear all cache entries."""
        self._cache.clear()
        self._cache_timestamps.clear()

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


# Singleton instance for global access
_catalog_instance = None


def get_catalog() -> SKBCatalog:
    """Get the global SKB catalog instance."""
    global _catalog_instance
    if _catalog_instance is None:
        _catalog_instance = SKBCatalog()
    return _catalog_instance
