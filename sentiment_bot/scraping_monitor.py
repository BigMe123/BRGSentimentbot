#!/usr/bin/env python3
"""
Scraping Monitor - Real-time monitoring and alerting for BSG scraping operations
==============================================================================

Provides comprehensive monitoring, alerting, and health checks for production scraping.
"""

import json
import time
import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict, deque
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class HealthStatus(Enum):
    """Overall health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"

@dataclass
class HealthMetric:
    """Individual health metric."""
    name: str
    value: float
    threshold_warning: float
    threshold_critical: float
    status: HealthStatus
    last_updated: datetime
    description: str = ""

@dataclass
class Alert:
    """System alert."""
    id: str
    level: AlertLevel
    component: str
    message: str
    timestamp: datetime
    resolved: bool = False
    resolution_time: Optional[datetime] = None
    metadata: Dict = None

@dataclass
class ScrapingMetrics:
    """Comprehensive scraping metrics."""
    total_sources: int = 0
    successful_sources: int = 0
    failed_sources: int = 0
    total_articles: int = 0
    articles_per_minute: float = 0.0
    avg_response_time: float = 0.0
    error_rate: float = 0.0
    circuit_breakers_open: int = 0
    rate_limit_hits: int = 0
    unique_domains: int = 0
    duplicate_articles_filtered: int = 0
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

class ScrapingMonitor:
    """
    Comprehensive monitoring system for scraping operations.

    Features:
    - Real-time metrics collection
    - Health status monitoring
    - Automated alerting
    - Performance trend analysis
    - Persistent storage of metrics
    """

    def __init__(self,
                 db_path: str = "state/scraping_monitor.sqlite",
                 alert_thresholds: Dict = None,
                 enable_persistence: bool = True):
        """Initialize monitoring system."""
        self.db_path = db_path
        self.enable_persistence = enable_persistence

        # Alert thresholds
        self.alert_thresholds = alert_thresholds or {
            'error_rate_warning': 0.15,  # 15% error rate
            'error_rate_critical': 0.30,  # 30% error rate
            'response_time_warning': 10.0,  # 10 seconds
            'response_time_critical': 20.0,  # 20 seconds
            'success_rate_warning': 0.80,  # 80% success rate
            'success_rate_critical': 0.60,  # 60% success rate
            'articles_per_minute_warning': 1.0,  # 1 article per minute
            'circuit_breakers_critical': 5  # 5 domains with breakers open
        }

        # Current metrics
        self.current_metrics = ScrapingMetrics()
        self.health_metrics: Dict[str, HealthMetric] = {}

        # Alert management
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: deque = deque(maxlen=1000)

        # Performance history
        self.metrics_history: deque = deque(maxlen=1440)  # 24 hours of minute-by-minute data

        # Alert callbacks
        self.alert_callbacks: List[Callable] = []

        # Initialize database if persistence enabled
        if self.enable_persistence:
            self._init_database()

        # Initialize health metrics
        self._init_health_metrics()

        logger.info("Scraping monitor initialized")

    def _init_database(self):
        """Initialize SQLite database for persistence."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    total_sources INTEGER,
                    successful_sources INTEGER,
                    failed_sources INTEGER,
                    total_articles INTEGER,
                    articles_per_minute REAL,
                    avg_response_time REAL,
                    error_rate REAL,
                    circuit_breakers_open INTEGER,
                    rate_limit_hits INTEGER,
                    unique_domains INTEGER,
                    duplicate_articles_filtered INTEGER
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    level TEXT NOT NULL,
                    component TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    resolved BOOLEAN DEFAULT FALSE,
                    resolution_time TEXT,
                    metadata TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp)
            """)

    def _init_health_metrics(self):
        """Initialize health metrics tracking."""
        metrics = [
            HealthMetric(
                name="error_rate",
                value=0.0,
                threshold_warning=self.alert_thresholds['error_rate_warning'],
                threshold_critical=self.alert_thresholds['error_rate_critical'],
                status=HealthStatus.HEALTHY,
                last_updated=datetime.now(),
                description="Percentage of failed scraping attempts"
            ),
            HealthMetric(
                name="response_time",
                value=0.0,
                threshold_warning=self.alert_thresholds['response_time_warning'],
                threshold_critical=self.alert_thresholds['response_time_critical'],
                status=HealthStatus.HEALTHY,
                last_updated=datetime.now(),
                description="Average response time in seconds"
            ),
            HealthMetric(
                name="success_rate",
                value=1.0,
                threshold_warning=self.alert_thresholds['success_rate_warning'],
                threshold_critical=self.alert_thresholds['success_rate_critical'],
                status=HealthStatus.HEALTHY,
                last_updated=datetime.now(),
                description="Percentage of successful scraping attempts"
            ),
            HealthMetric(
                name="articles_per_minute",
                value=0.0,
                threshold_warning=self.alert_thresholds['articles_per_minute_warning'],
                threshold_critical=0.0,
                status=HealthStatus.HEALTHY,
                last_updated=datetime.now(),
                description="Articles processed per minute"
            )
        ]

        for metric in metrics:
            self.health_metrics[metric.name] = metric

    def update_metrics_from_scraper(self, scraper_report: Dict):
        """Update metrics from enhanced scraper report."""
        summary = scraper_report.get('summary', {})

        self.current_metrics.total_sources = summary.get('total_attempts', 0)
        self.current_metrics.successful_sources = int(
            self.current_metrics.total_sources * summary.get('success_rate', 0)
        )
        self.current_metrics.failed_sources = (
            self.current_metrics.total_sources - self.current_metrics.successful_sources
        )
        self.current_metrics.total_articles = summary.get('total_articles_fetched', 0)
        self.current_metrics.error_rate = 1.0 - summary.get('success_rate', 0)
        self.current_metrics.circuit_breakers_open = summary.get('domains_with_circuit_breakers_open', 0)
        self.current_metrics.unique_domains = summary.get('unique_domains_attempted', 0)

        # Calculate articles per minute based on recent activity
        if self.metrics_history:
            recent_metrics = list(self.metrics_history)[-10:]  # Last 10 minutes
            if len(recent_metrics) > 1:
                time_diff = (recent_metrics[-1].timestamp - recent_metrics[0].timestamp).total_seconds() / 60
                article_diff = recent_metrics[-1].total_articles - recent_metrics[0].total_articles
                if time_diff > 0:
                    self.current_metrics.articles_per_minute = article_diff / time_diff

        # Update health metrics
        self._update_health_metrics()

        # Store in history
        self.metrics_history.append(self.current_metrics)

        # Persist to database
        if self.enable_persistence:
            self._persist_metrics()

        # Check for alerts
        self._check_alerts()

        logger.debug(f"Metrics updated: {self.current_metrics.total_articles} articles, "
                    f"{self.current_metrics.error_rate:.2%} error rate")

    def _update_health_metrics(self):
        """Update health metrics based on current data."""
        now = datetime.now()

        # Error rate
        error_metric = self.health_metrics['error_rate']
        error_metric.value = self.current_metrics.error_rate
        error_metric.last_updated = now
        if error_metric.value >= error_metric.threshold_critical:
            error_metric.status = HealthStatus.CRITICAL
        elif error_metric.value >= error_metric.threshold_warning:
            error_metric.status = HealthStatus.DEGRADED
        else:
            error_metric.status = HealthStatus.HEALTHY

        # Response time
        response_metric = self.health_metrics['response_time']
        response_metric.value = self.current_metrics.avg_response_time
        response_metric.last_updated = now
        if response_metric.value >= response_metric.threshold_critical:
            response_metric.status = HealthStatus.CRITICAL
        elif response_metric.value >= response_metric.threshold_warning:
            response_metric.status = HealthStatus.DEGRADED
        else:
            response_metric.status = HealthStatus.HEALTHY

        # Success rate
        success_rate = 1.0 - self.current_metrics.error_rate
        success_metric = self.health_metrics['success_rate']
        success_metric.value = success_rate
        success_metric.last_updated = now
        if success_rate <= success_metric.threshold_critical:
            success_metric.status = HealthStatus.CRITICAL
        elif success_rate <= success_metric.threshold_warning:
            success_metric.status = HealthStatus.DEGRADED
        else:
            success_metric.status = HealthStatus.HEALTHY

        # Articles per minute
        articles_metric = self.health_metrics['articles_per_minute']
        articles_metric.value = self.current_metrics.articles_per_minute
        articles_metric.last_updated = now
        if articles_metric.value <= articles_metric.threshold_critical:
            articles_metric.status = HealthStatus.CRITICAL
        elif articles_metric.value <= articles_metric.threshold_warning:
            articles_metric.status = HealthStatus.DEGRADED
        else:
            articles_metric.status = HealthStatus.HEALTHY

    def _check_alerts(self):
        """Check for alert conditions and trigger alerts."""
        now = datetime.now()

        # Error rate alerts
        if self.current_metrics.error_rate >= self.alert_thresholds['error_rate_critical']:
            self._trigger_alert(
                "high_error_rate_critical",
                AlertLevel.CRITICAL,
                "scraper",
                f"Critical error rate: {self.current_metrics.error_rate:.2%} "
                f"(threshold: {self.alert_thresholds['error_rate_critical']:.2%})"
            )
        elif self.current_metrics.error_rate >= self.alert_thresholds['error_rate_warning']:
            self._trigger_alert(
                "high_error_rate_warning",
                AlertLevel.WARNING,
                "scraper",
                f"High error rate: {self.current_metrics.error_rate:.2%} "
                f"(threshold: {self.alert_thresholds['error_rate_warning']:.2%})"
            )
        else:
            self._resolve_alert("high_error_rate_critical")
            self._resolve_alert("high_error_rate_warning")

        # Response time alerts
        if self.current_metrics.avg_response_time >= self.alert_thresholds['response_time_critical']:
            self._trigger_alert(
                "slow_response_critical",
                AlertLevel.CRITICAL,
                "scraper",
                f"Critical response time: {self.current_metrics.avg_response_time:.1f}s "
                f"(threshold: {self.alert_thresholds['response_time_critical']:.1f}s)"
            )
        elif self.current_metrics.avg_response_time >= self.alert_thresholds['response_time_warning']:
            self._trigger_alert(
                "slow_response_warning",
                AlertLevel.WARNING,
                "scraper",
                f"Slow response time: {self.current_metrics.avg_response_time:.1f}s "
                f"(threshold: {self.alert_thresholds['response_time_warning']:.1f}s)"
            )
        else:
            self._resolve_alert("slow_response_critical")
            self._resolve_alert("slow_response_warning")

        # Circuit breaker alerts
        if self.current_metrics.circuit_breakers_open >= self.alert_thresholds['circuit_breakers_critical']:
            self._trigger_alert(
                "circuit_breakers_open",
                AlertLevel.ERROR,
                "circuit_breaker",
                f"Multiple circuit breakers open: {self.current_metrics.circuit_breakers_open} domains"
            )
        else:
            self._resolve_alert("circuit_breakers_open")

        # Low productivity alerts
        if (self.current_metrics.articles_per_minute <=
            self.alert_thresholds['articles_per_minute_warning'] and
            self.current_metrics.total_sources > 10):  # Only alert if we're actually trying to scrape
            self._trigger_alert(
                "low_productivity",
                AlertLevel.WARNING,
                "productivity",
                f"Low article productivity: {self.current_metrics.articles_per_minute:.1f} articles/min"
            )
        else:
            self._resolve_alert("low_productivity")

    def _trigger_alert(self, alert_id: str, level: AlertLevel, component: str, message: str):
        """Trigger a new alert or update existing one."""
        if alert_id not in self.active_alerts:
            alert = Alert(
                id=alert_id,
                level=level,
                component=component,
                message=message,
                timestamp=datetime.now(),
                metadata={'metrics': asdict(self.current_metrics)}
            )

            self.active_alerts[alert_id] = alert
            self.alert_history.append(alert)

            # Persist alert
            if self.enable_persistence:
                self._persist_alert(alert)

            # Notify callbacks
            for callback in self.alert_callbacks:
                try:
                    callback(alert)
                except Exception as e:
                    logger.error(f"Alert callback failed: {e}")

            logger.warning(f"ALERT [{level.value.upper()}] {component}: {message}")

    def _resolve_alert(self, alert_id: str):
        """Resolve an active alert."""
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.resolved = True
            alert.resolution_time = datetime.now()

            # Update in database
            if self.enable_persistence:
                self._update_alert_resolution(alert)

            # Remove from active alerts
            del self.active_alerts[alert_id]

            logger.info(f"Alert resolved: {alert_id}")

    def _persist_metrics(self):
        """Persist current metrics to database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO metrics (
                        timestamp, total_sources, successful_sources, failed_sources,
                        total_articles, articles_per_minute, avg_response_time,
                        error_rate, circuit_breakers_open, rate_limit_hits,
                        unique_domains, duplicate_articles_filtered
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.current_metrics.timestamp.isoformat(),
                    self.current_metrics.total_sources,
                    self.current_metrics.successful_sources,
                    self.current_metrics.failed_sources,
                    self.current_metrics.total_articles,
                    self.current_metrics.articles_per_minute,
                    self.current_metrics.avg_response_time,
                    self.current_metrics.error_rate,
                    self.current_metrics.circuit_breakers_open,
                    self.current_metrics.rate_limit_hits,
                    self.current_metrics.unique_domains,
                    self.current_metrics.duplicate_articles_filtered
                ))
        except Exception as e:
            logger.error(f"Failed to persist metrics: {e}")

    def _persist_alert(self, alert: Alert):
        """Persist alert to database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO alerts (
                        id, level, component, message, timestamp, resolved, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    alert.id,
                    alert.level.value,
                    alert.component,
                    alert.message,
                    alert.timestamp.isoformat(),
                    alert.resolved,
                    json.dumps(alert.metadata) if alert.metadata else None
                ))
        except Exception as e:
            logger.error(f"Failed to persist alert: {e}")

    def _update_alert_resolution(self, alert: Alert):
        """Update alert resolution in database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE alerts SET resolved = ?, resolution_time = ?
                    WHERE id = ?
                """, (
                    alert.resolved,
                    alert.resolution_time.isoformat() if alert.resolution_time else None,
                    alert.id
                ))
        except Exception as e:
            logger.error(f"Failed to update alert resolution: {e}")

    def get_overall_health_status(self) -> HealthStatus:
        """Get overall system health status."""
        if not self.health_metrics:
            return HealthStatus.HEALTHY

        # Count status types
        status_counts = defaultdict(int)
        for metric in self.health_metrics.values():
            status_counts[metric.status] += 1

        # Determine overall status
        if status_counts[HealthStatus.CRITICAL] > 0:
            return HealthStatus.CRITICAL
        elif status_counts[HealthStatus.UNHEALTHY] > 0:
            return HealthStatus.UNHEALTHY
        elif status_counts[HealthStatus.DEGRADED] > 0:
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.HEALTHY

    def get_health_report(self) -> Dict:
        """Get comprehensive health report."""
        overall_status = self.get_overall_health_status()

        health_metrics = {}
        for name, metric in self.health_metrics.items():
            health_metrics[name] = {
                'value': metric.value,
                'status': metric.status.value,
                'threshold_warning': metric.threshold_warning,
                'threshold_critical': metric.threshold_critical,
                'last_updated': metric.last_updated.isoformat(),
                'description': metric.description
            }

        active_alerts = [
            {
                'id': alert.id,
                'level': alert.level.value,
                'component': alert.component,
                'message': alert.message,
                'timestamp': alert.timestamp.isoformat()
            }
            for alert in self.active_alerts.values()
        ]

        # Performance trends
        trends = self._calculate_trends()

        return {
            'overall_status': overall_status.value,
            'health_metrics': health_metrics,
            'active_alerts': active_alerts,
            'current_metrics': asdict(self.current_metrics),
            'trends': trends,
            'last_updated': datetime.now().isoformat()
        }

    def _calculate_trends(self) -> Dict:
        """Calculate performance trends."""
        if len(self.metrics_history) < 2:
            return {}

        recent_metrics = list(self.metrics_history)[-60:]  # Last hour

        if len(recent_metrics) < 2:
            return {}

        # Calculate trends
        error_rates = [m.error_rate for m in recent_metrics]
        response_times = [m.avg_response_time for m in recent_metrics]
        articles_per_min = [m.articles_per_minute for m in recent_metrics]

        def calculate_trend(values):
            if len(values) < 2:
                return 0.0
            return (values[-1] - values[0]) / len(values)

        return {
            'error_rate_trend': calculate_trend(error_rates),
            'response_time_trend': calculate_trend(response_times),
            'productivity_trend': calculate_trend(articles_per_min)
        }

    def add_alert_callback(self, callback: Callable[[Alert], None]):
        """Add callback for alert notifications."""
        self.alert_callbacks.append(callback)

    def get_metrics_history(self, hours: int = 24) -> List[Dict]:
        """Get metrics history for specified hours."""
        cutoff_time = datetime.now() - timedelta(hours=hours)

        if self.enable_persistence:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT * FROM metrics
                        WHERE timestamp >= ?
                        ORDER BY timestamp
                    """, (cutoff_time.isoformat(),))

                    columns = [desc[0] for desc in cursor.description]
                    return [dict(zip(columns, row)) for row in cursor.fetchall()]
            except Exception as e:
                logger.error(f"Failed to fetch metrics history: {e}")

        # Fallback to in-memory history
        return [
            asdict(m) for m in self.metrics_history
            if m.timestamp >= cutoff_time
        ]

    def cleanup_old_data(self, days: int = 30):
        """Clean up old data from database."""
        if not self.enable_persistence:
            return

        cutoff_time = datetime.now() - timedelta(days=days)

        try:
            with sqlite3.connect(self.db_path) as conn:
                # Clean up old metrics
                result = conn.execute("""
                    DELETE FROM metrics WHERE timestamp < ?
                """, (cutoff_time.isoformat(),))

                # Clean up resolved alerts
                alert_cutoff = datetime.now() - timedelta(days=7)  # Keep alerts for 7 days
                conn.execute("""
                    DELETE FROM alerts
                    WHERE resolved = TRUE AND resolution_time < ?
                """, (alert_cutoff.isoformat(),))

                logger.info(f"Cleaned up {result.rowcount} old metrics records")

        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")


# Factory function for easy integration
def create_scraping_monitor(**kwargs) -> ScrapingMonitor:
    """Create a configured scraping monitor instance."""
    return ScrapingMonitor(**kwargs)

# Example alert callback for console output
def console_alert_callback(alert: Alert):
    """Simple console alert callback."""
    level_colors = {
        AlertLevel.INFO: '\033[94m',      # Blue
        AlertLevel.WARNING: '\033[93m',   # Yellow
        AlertLevel.ERROR: '\033[91m',     # Red
        AlertLevel.CRITICAL: '\033[95m'   # Magenta
    }

    color = level_colors.get(alert.level, '')
    reset = '\033[0m'

    print(f"{color}[{alert.level.value.upper()}] {alert.component}: {alert.message}{reset}")