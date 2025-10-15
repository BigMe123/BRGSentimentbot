#!/usr/bin/env python3
"""
Risk Intelligence Database Schema & Manager
Unified signals storage for all agentic outputs
"""

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import hashlib


@dataclass
class Signal:
    """Risk signal data model"""
    id: str
    ts: str  # ISO timestamp
    source: str  # 'query_agent', 'monitor_agent', 'forecast_agent', 'summarizer_agent', etc.
    category: str  # 'macro', 'regulatory', 'brand', 'supply_chain', 'market', 'geopolitical'
    entity: Optional[str]  # company/country/sector
    title: str
    summary: str
    risk_score: float  # 0-100
    tags: List[str]
    link: Optional[str]
    raw: Dict[str, Any]  # Full metadata, evidence, prompts used
    confidence: float = 0.0  # 0-1 confidence score
    impact: str = "medium"  # low, medium, high, critical

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        d = asdict(self)
        d['tags'] = json.dumps(d['tags'])
        d['raw'] = json.dumps(d['raw'])
        return d


@dataclass
class AgentStatus:
    """Agent health tracking"""
    agent_name: str
    last_heartbeat: str
    status: str  # 'healthy', 'degraded', 'down'
    signals_produced: int
    avg_confidence: float
    last_error: Optional[str] = None


class RiskDatabase:
    """Risk Intelligence Database Manager"""

    def __init__(self, db_path: str = "data/risk_intelligence.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = None
        self._initialize_db()

    def _initialize_db(self):
        """Create tables if they don't exist"""
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # Main signals table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id TEXT PRIMARY KEY,
                ts TIMESTAMP NOT NULL,
                source TEXT NOT NULL,
                category TEXT,
                entity TEXT,
                title TEXT NOT NULL,
                summary TEXT,
                risk_score REAL,
                confidence REAL DEFAULT 0.0,
                impact TEXT DEFAULT 'medium',
                tags TEXT,
                link TEXT,
                raw TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes for fast queries
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts DESC)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_category ON signals(category)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_entity ON signals(entity)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_risk_score ON signals(risk_score DESC)
        """)

        # Agent status table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_status (
                agent_name TEXT PRIMARY KEY,
                last_heartbeat TIMESTAMP NOT NULL,
                status TEXT NOT NULL,
                signals_produced INTEGER DEFAULT 0,
                avg_confidence REAL DEFAULT 0.0,
                last_error TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Dedupe tracking table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_hashes (
                content_hash TEXT PRIMARY KEY,
                signal_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (signal_id) REFERENCES signals(id)
            )
        """)

        self.conn.commit()

    def generate_signal_id(self, title: str, source: str, ts: str) -> str:
        """Generate unique signal ID"""
        unique_str = f"{title}:{source}:{ts}"
        return hashlib.sha256(unique_str.encode()).hexdigest()[:16]

    def compute_content_hash(self, title: str, summary: str, entity: str = "") -> str:
        """Compute content hash for deduplication"""
        content = f"{title.lower().strip()}:{summary.lower().strip()[:200]}:{entity.lower().strip()}"
        return hashlib.md5(content.encode()).hexdigest()

    def is_duplicate(self, signal: Signal, time_window_hours: int = 24) -> bool:
        """Check if signal is duplicate within time window"""
        content_hash = self.compute_content_hash(signal.title, signal.summary, signal.entity or "")

        cursor = self.conn.execute("""
            SELECT signal_id FROM signal_hashes
            WHERE content_hash = ?
            AND created_at > datetime('now', '-' || ? || ' hours')
        """, (content_hash, time_window_hours))

        return cursor.fetchone() is not None

    def insert_signal(self, signal: Signal, check_duplicate: bool = True) -> bool:
        """Insert new signal (returns False if duplicate)"""
        if check_duplicate and self.is_duplicate(signal):
            return False

        data = signal.to_dict()

        try:
            self.conn.execute("""
                INSERT INTO signals (
                    id, ts, source, category, entity, title, summary,
                    risk_score, confidence, impact, tags, link, raw
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data['id'], data['ts'], data['source'], data['category'],
                data['entity'], data['title'], data['summary'], data['risk_score'],
                data['confidence'], data['impact'], data['tags'], data['link'], data['raw']
            ))

            # Track hash for deduplication
            content_hash = self.compute_content_hash(signal.title, signal.summary, signal.entity or "")
            self.conn.execute("""
                INSERT OR IGNORE INTO signal_hashes (content_hash, signal_id)
                VALUES (?, ?)
            """, (content_hash, signal.id))

            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_latest_signals(self, limit: int = 50, category: Optional[str] = None,
                          min_risk_score: float = 0.0) -> List[Dict]:
        """Get latest signals with optional filters"""
        query = """
            SELECT * FROM signals
            WHERE risk_score >= ?
        """
        params = [min_risk_score]

        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)

        cursor = self.conn.execute(query, params)
        signals = []
        for row in cursor.fetchall():
            signal_dict = dict(row)
            signal_dict['tags'] = json.loads(signal_dict['tags']) if signal_dict['tags'] else []
            signal_dict['raw'] = json.loads(signal_dict['raw']) if signal_dict['raw'] else {}
            signals.append(signal_dict)

        return signals

    def get_signals_by_entity(self, entity: str, limit: int = 20) -> List[Dict]:
        """Get signals for specific entity"""
        cursor = self.conn.execute("""
            SELECT * FROM signals
            WHERE entity = ?
            ORDER BY ts DESC
            LIMIT ?
        """, (entity, limit))

        return [dict(row) for row in cursor.fetchall()]

    def get_signals_time_range(self, start_ts: str, end_ts: str,
                               category: Optional[str] = None) -> List[Dict]:
        """Get signals in time range"""
        query = "SELECT * FROM signals WHERE ts BETWEEN ? AND ?"
        params = [start_ts, end_ts]

        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY ts DESC"
        cursor = self.conn.execute(query, params)

        return [dict(row) for row in cursor.fetchall()]

    def get_signal_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics"""
        stats = {}

        # Total signals
        cursor = self.conn.execute("SELECT COUNT(*) as total FROM signals")
        stats['total_signals'] = cursor.fetchone()['total']

        # By category
        cursor = self.conn.execute("""
            SELECT category, COUNT(*) as count
            FROM signals
            GROUP BY category
            ORDER BY count DESC
        """)
        stats['by_category'] = {row['category']: row['count'] for row in cursor.fetchall()}

        # By source (agent)
        cursor = self.conn.execute("""
            SELECT source, COUNT(*) as count
            FROM signals
            GROUP BY source
            ORDER BY count DESC
        """)
        stats['by_source'] = {row['source']: row['count'] for row in cursor.fetchall()}

        # Average risk score
        cursor = self.conn.execute("SELECT AVG(risk_score) as avg_risk FROM signals")
        stats['avg_risk_score'] = cursor.fetchone()['avg_risk'] or 0.0

        # High risk signals (>70)
        cursor = self.conn.execute("SELECT COUNT(*) as count FROM signals WHERE risk_score > 70")
        stats['high_risk_count'] = cursor.fetchone()['count']

        # Signals last 24h
        cursor = self.conn.execute("""
            SELECT COUNT(*) as count FROM signals
            WHERE ts > datetime('now', '-1 day')
        """)
        stats['last_24h'] = cursor.fetchone()['count']

        return stats

    def update_agent_heartbeat(self, agent_name: str, status: str = 'healthy',
                               error: Optional[str] = None):
        """Update agent health status"""
        now = datetime.now(timezone.utc).isoformat()

        self.conn.execute("""
            INSERT OR REPLACE INTO agent_status (
                agent_name, last_heartbeat, status, last_error, updated_at
            ) VALUES (?, ?, ?, ?, ?)
        """, (agent_name, now, status, error, now))
        self.conn.commit()

    def get_agent_status(self, agent_name: Optional[str] = None) -> List[Dict]:
        """Get agent status (all or specific)"""
        if agent_name:
            cursor = self.conn.execute("""
                SELECT * FROM agent_status WHERE agent_name = ?
            """, (agent_name,))
        else:
            cursor = self.conn.execute("SELECT * FROM agent_status")

        return [dict(row) for row in cursor.fetchall()]

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()


# Singleton instance
_db_instance: Optional[RiskDatabase] = None

def get_risk_db() -> RiskDatabase:
    """Get singleton database instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = RiskDatabase()
    return _db_instance
