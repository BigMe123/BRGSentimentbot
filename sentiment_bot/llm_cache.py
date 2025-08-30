"""
Lightweight SQLite cache for LLM responses to avoid redundant API calls.
Caches based on content hash + model name for precise deduplication.
"""

import sqlite3
import json
import hashlib
import os
import logging
from contextlib import closing
from typing import Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Cache database path
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "state")
DB_PATH = os.path.join(CACHE_DIR, "llm_cache.sqlite")

# Ensure state directory exists
os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_key(text: str, model: str) -> str:
    """Generate cache key from text content and model name."""
    content = f"{model}\n{text}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _init_cache_db():
    """Initialize cache database with schema."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 1
            )
        """
        )

        # Index for cleanup queries
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_accessed_at 
            ON llm_cache(accessed_at)
        """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_model 
            ON llm_cache(model)
        """
        )

        conn.commit()


def get_cache(text: str, model: str) -> Optional[Any]:
    """
    Retrieve cached result for text + model combination.
    Returns None if not found.
    """
    try:
        _init_cache_db()
        key = _cache_key(text, model)

        with closing(sqlite3.connect(DB_PATH)) as conn:
            # Update access tracking and retrieve value in one query
            conn.execute(
                """
                UPDATE llm_cache 
                SET accessed_at = CURRENT_TIMESTAMP, 
                    access_count = access_count + 1
                WHERE key = ?
            """,
                (key,),
            )

            cursor = conn.execute("SELECT value FROM llm_cache WHERE key = ?", (key,))
            row = cursor.fetchone()

            if row:
                conn.commit()  # Commit the access update
                result = json.loads(row[0])
                logger.debug(f"Cache hit for {model} (key: {key[:12]}...)")
                return result

            logger.debug(f"Cache miss for {model} (key: {key[:12]}...)")
            return None

    except Exception as e:
        logger.warning(f"Cache retrieval failed: {e}")
        return None


def set_cache(text: str, model: str, value: Any):
    """
    Store result in cache for text + model combination.
    """
    try:
        _init_cache_db()
        key = _cache_key(text, model)

        with closing(sqlite3.connect(DB_PATH)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO llm_cache (key, value, model) 
                VALUES (?, ?, ?)
            """,
                (key, json.dumps(value), model),
            )

            conn.commit()
            logger.debug(f"Cached result for {model} (key: {key[:12]}...)")

    except Exception as e:
        logger.warning(f"Cache storage failed: {e}")


def get_cache_stats() -> dict:
    """Get cache statistics for monitoring."""
    try:
        _init_cache_db()

        with closing(sqlite3.connect(DB_PATH)) as conn:
            # Total entries
            cursor = conn.execute("SELECT COUNT(*) FROM llm_cache")
            total_entries = cursor.fetchone()[0]

            # Entries by model
            cursor = conn.execute(
                """
                SELECT model, COUNT(*) as count, SUM(access_count) as total_accesses
                FROM llm_cache 
                GROUP BY model
            """
            )
            by_model = {
                row[0]: {"entries": row[1], "total_accesses": row[2]}
                for row in cursor.fetchall()
            }

            # Recent activity (last 24 hours)
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM llm_cache 
                WHERE accessed_at > datetime('now', '-24 hours')
            """
            )
            recent_accesses = cursor.fetchone()[0]

            return {
                "total_entries": total_entries,
                "by_model": by_model,
                "recent_accesses_24h": recent_accesses,
                "db_size_mb": (
                    os.path.getsize(DB_PATH) / (1024 * 1024)
                    if os.path.exists(DB_PATH)
                    else 0
                ),
            }

    except Exception as e:
        logger.warning(f"Cache stats failed: {e}")
        return {"error": str(e)}


def cleanup_cache(days_old: int = 30, keep_accessed_within_days: int = 7):
    """
    Clean up old cache entries to manage storage.

    Args:
        days_old: Remove entries created more than this many days ago
        keep_accessed_within_days: Keep entries accessed within this many days regardless of age
    """
    try:
        _init_cache_db()

        with closing(sqlite3.connect(DB_PATH)) as conn:
            # Clean up old, unused entries
            cursor = conn.execute(
                """
                DELETE FROM llm_cache 
                WHERE created_at < datetime('now', '-{} days')
                AND accessed_at < datetime('now', '-{} days')
            """.format(
                    days_old, keep_accessed_within_days
                )
            )

            deleted_count = cursor.rowcount
            conn.commit()

            logger.info(f"Cache cleanup: removed {deleted_count} old entries")
            return deleted_count

    except Exception as e:
        logger.warning(f"Cache cleanup failed: {e}")
        return 0


def clear_cache(model: Optional[str] = None):
    """
    Clear cache entries. If model specified, only clear for that model.
    """
    try:
        _init_cache_db()

        with closing(sqlite3.connect(DB_PATH)) as conn:
            if model:
                cursor = conn.execute("DELETE FROM llm_cache WHERE model = ?", (model,))
                logger.info(f"Cleared cache for model: {model}")
            else:
                cursor = conn.execute("DELETE FROM llm_cache")
                logger.info("Cleared entire cache")

            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count

    except Exception as e:
        logger.warning(f"Cache clear failed: {e}")
        return 0
