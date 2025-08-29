"""SQLite database for historical sentiment tracking."""

import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class SentimentDB:
    """Database for tracking sentiment analysis history."""
    
    def __init__(self, db_path: str = "state/brg_sentiment.sqlite"):
        """Initialize database connection."""
        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        
        # Enable WAL mode for better concurrency
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        
        self._init_schema()
    
    def _init_schema(self):
        """Initialize database schema."""
        
        # Runs table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                region TEXT,
                topic TEXT,
                other_topic TEXT,
                freshness_rate REAL,
                kept_ratio REAL,
                abstain_rate REAL,
                diversity_json TEXT,
                total_articles INTEGER,
                fresh_articles INTEGER,
                relevant_articles INTEGER,
                clusters_found INTEGER,
                aggregate_sentiment REAL,
                confidence_avg REAL,
                metrics_json TEXT
            )
        """)
        
        # Articles table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                article_id TEXT PRIMARY KEY,
                run_id TEXT,
                url TEXT,
                title TEXT,
                domain TEXT,
                country TEXT,
                language TEXT,
                published_date TIMESTAMP,
                fetched_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                topic TEXT,
                region TEXT,
                sentiment_score REAL,
                sentiment_label TEXT,
                confidence REAL,
                abstained BOOLEAN,
                cluster_id INTEGER,
                aspects_json TEXT,
                stances_json TEXT,
                tags_json TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            )
        """)
        
        # Aspects table (for aggregation)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS aspects (
                aspect_id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id TEXT,
                run_id TEXT,
                aspect_text TEXT,
                aspect_type TEXT,
                sentiment_score REAL,
                sentiment_label TEXT,
                importance REAL,
                FOREIGN KEY (article_id) REFERENCES articles(article_id),
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            )
        """)
        
        # Create indexes
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON runs(timestamp)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_run ON articles(run_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(published_date)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_domain ON articles(domain)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_aspects_run ON aspects(run_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_aspects_text ON aspects(aspect_text)")
        
        self.conn.commit()
    
    def save_run(self, run_data: Dict) -> str:
        """Save a run's metadata.
        
        Returns:
            run_id
        """
        import uuid
        
        run_id = run_data.get('run_id', str(uuid.uuid4()))
        
        self.conn.execute("""
            INSERT INTO runs (
                run_id, region, topic, other_topic,
                freshness_rate, kept_ratio, abstain_rate,
                diversity_json, total_articles, fresh_articles,
                relevant_articles, clusters_found, aggregate_sentiment,
                confidence_avg, metrics_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            run_data.get('region'),
            run_data.get('topic'),
            run_data.get('other_topic'),
            run_data.get('freshness_rate', 0.0),
            run_data.get('kept_ratio', 0.0),
            run_data.get('abstain_rate', 0.0),
            json.dumps(run_data.get('diversity', {})),
            run_data.get('total_articles', 0),
            run_data.get('fresh_articles', 0),
            run_data.get('relevant_articles', 0),
            run_data.get('clusters_found', 0),
            run_data.get('aggregate_sentiment', 0.0),
            run_data.get('confidence_avg', 0.0),
            json.dumps(run_data.get('metrics', {}))
        ))
        
        self.conn.commit()
        return run_id
    
    def save_article(self, article_data: Dict, run_id: str):
        """Save an article's analysis results."""
        import hashlib
        
        # Generate article ID from URL
        url = article_data.get('url', article_data.get('link', ''))
        article_id = hashlib.md5(url.encode()).hexdigest()
        
        # Extract country from domain or region
        country = article_data.get('country', '')
        if not country and 'domain' in article_data:
            # Simple country extraction from domain
            domain = article_data['domain'].lower()
            if '.uk' in domain:
                country = 'UK'
            elif '.us' in domain or '.com' in domain:
                country = 'US'
            elif '.fr' in domain:
                country = 'FR'
            elif '.de' in domain:
                country = 'DE'
            # Add more as needed
        
        self.conn.execute("""
            INSERT OR REPLACE INTO articles (
                article_id, run_id, url, title, domain,
                country, language, published_date, topic, region,
                sentiment_score, sentiment_label, confidence,
                abstained, cluster_id, aspects_json,
                stances_json, tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            article_id,
            run_id,
            url,
            article_data.get('title', ''),
            article_data.get('domain', ''),
            country,
            article_data.get('language', 'en'),
            article_data.get('published_date'),
            article_data.get('topic', ''),
            article_data.get('region', ''),
            article_data.get('sentiment_score', 0.0),
            article_data.get('sentiment_label', 'neutral'),
            article_data.get('confidence', 0.0),
            article_data.get('abstained', False),
            article_data.get('cluster_id'),
            json.dumps(article_data.get('aspects', [])),
            json.dumps(article_data.get('stances', {})),
            json.dumps(article_data.get('tags', []))
        ))
        
        # Save aspects separately for aggregation
        aspects = article_data.get('aspects', [])
        for aspect in aspects:
            self.conn.execute("""
                INSERT INTO aspects (
                    article_id, run_id, aspect_text, aspect_type,
                    sentiment_score, sentiment_label, importance
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                article_id,
                run_id,
                aspect.get('text', ''),
                aspect.get('type', ''),
                aspect.get('sentiment_score', 0.0),
                aspect.get('sentiment_label', 'neutral'),
                aspect.get('importance', 0.0)
            ))
        
        self.conn.commit()
    
    def get_time_series(
        self,
        hours: int = 24,
        region: Optional[str] = None,
        topic: Optional[str] = None
    ) -> List[Dict]:
        """Get sentiment time series for last N hours."""
        
        query = """
            SELECT 
                DATE(published_date) as date,
                AVG(sentiment_score) as avg_sentiment,
                COUNT(*) as article_count,
                AVG(confidence) as avg_confidence
            FROM articles
            WHERE published_date > datetime('now', ? || ' hours')
        """
        
        params = [-hours]
        
        if region:
            query += " AND region = ?"
            params.append(region)
        
        if topic:
            query += " AND topic = ?"
            params.append(topic)
        
        query += " GROUP BY DATE(published_date) ORDER BY date"
        
        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_top_countries_by_sentiment(
        self,
        hours: int = 48,
        topic: Optional[str] = None,
        sentiment_type: str = 'negative',
        limit: int = 5
    ) -> List[Dict]:
        """Get top countries by sentiment."""
        
        if sentiment_type == 'negative':
            order = "ASC"  # Most negative first
        else:
            order = "DESC"  # Most positive first
        
        query = f"""
            SELECT 
                country,
                AVG(sentiment_score) as avg_sentiment,
                COUNT(*) as article_count
            FROM articles
            WHERE published_date > datetime('now', ? || ' hours')
            AND country != ''
        """
        
        params = [-hours]
        
        if topic:
            query += " AND topic = ?"
            params.append(topic)
        
        query += f"""
            GROUP BY country
            HAVING article_count >= 3
            ORDER BY avg_sentiment {order}
            LIMIT ?
        """
        params.append(limit)
        
        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_trending_aspects(
        self,
        hours: int = 24,
        region: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """Get trending aspects by frequency and sentiment."""
        
        query = """
            SELECT 
                aspect_text,
                COUNT(*) as mention_count,
                AVG(sentiment_score) as avg_sentiment,
                AVG(importance) as avg_importance
            FROM aspects a
            JOIN articles art ON a.article_id = art.article_id
            WHERE art.published_date > datetime('now', ? || ' hours')
        """
        
        params = [-hours]
        
        if region:
            query += " AND art.region = ?"
            params.append(region)
        
        query += """
            GROUP BY aspect_text
            HAVING mention_count >= 2
            ORDER BY mention_count DESC, avg_importance DESC
            LIMIT ?
        """
        params.append(limit)
        
        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_run_history(self, limit: int = 10) -> List[Dict]:
        """Get recent run history."""
        
        cursor = self.conn.execute("""
            SELECT * FROM runs
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        runs = []
        for row in cursor.fetchall():
            run_dict = dict(row)
            # Parse JSON fields
            run_dict['diversity'] = json.loads(run_dict.get('diversity_json', '{}'))
            run_dict['metrics'] = json.loads(run_dict.get('metrics_json', '{}'))
            runs.append(run_dict)
        
        return runs
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()