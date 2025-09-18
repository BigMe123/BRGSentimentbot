"""
Performance monitoring system for tracking model accuracy and system health.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np
from collections import defaultdict, deque
import logging

logger = logging.getLogger(__name__)


@dataclass
class PredictionRecord:
    """Record of a single prediction."""
    timestamp: datetime
    model_type: str  # gdp, cpi, employment
    country: str
    prediction: float
    actual: Optional[float]
    confidence_interval: Optional[Tuple[float, float]]
    features_used: Optional[Dict[str, Any]]
    error: Optional[float] = None
    squared_error: Optional[float] = None
    directional_accuracy: Optional[bool] = None


@dataclass
class PerformanceMetrics:
    """Aggregated performance metrics."""
    mape: float  # Mean Absolute Percentage Error
    rmse: float  # Root Mean Square Error
    mae: float  # Mean Absolute Error
    directional_accuracy: float  # % of correct direction predictions
    confidence_coverage: float  # % of actuals within confidence intervals
    bias: float  # Average prediction - actual
    sample_size: int
    last_updated: datetime


@dataclass
class SystemHealth:
    """System health metrics."""
    uptime_percentage: float
    avg_response_time_ms: float
    error_rate: float
    memory_usage_mb: float
    cpu_usage_percent: float
    active_feeds: int
    degraded_feeds: int
    quarantined_feeds: int


@dataclass
class Alert:
    """Performance or system alert."""
    timestamp: datetime
    severity: str  # info, warning, critical
    type: str  # performance_degradation, system_error, feed_failure
    model: Optional[str]
    country: Optional[str]
    message: str
    metrics: Dict[str, Any]


class PerformanceMonitor:
    """
    Monitors performance of economic models and system health.

    Features:
    - Real-time tracking of prediction accuracy
    - Performance degradation detection
    - System health monitoring
    - Alert generation
    - Historical performance analysis
    """

    def __init__(self, db_path: str = "state/performance_monitor.db",
                 alert_thresholds: Optional[Dict[str, float]] = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.alert_thresholds = alert_thresholds or {
            "mape_warning": 0.05,  # 5% error
            "mape_critical": 0.10,  # 10% error
            "directional_accuracy_warning": 0.60,  # Below 60% accuracy
            "error_rate_warning": 0.05,  # 5% system errors
            "response_time_warning": 1000,  # 1 second
        }

        # In-memory buffers for recent data
        self.recent_predictions = defaultdict(lambda: deque(maxlen=100))
        self.recent_errors = deque(maxlen=1000)
        self.recent_response_times = deque(maxlen=1000)

        self._init_database()

    def _init_database(self):
        """Initialize performance monitoring database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Predictions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                model_type TEXT NOT NULL,
                country TEXT NOT NULL,
                prediction REAL NOT NULL,
                actual REAL,
                confidence_low REAL,
                confidence_high REAL,
                features TEXT,
                error REAL,
                squared_error REAL,
                directional_accuracy INTEGER
            )
        """)

        # Performance metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS performance_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                model_type TEXT NOT NULL,
                country TEXT NOT NULL,
                mape REAL,
                rmse REAL,
                mae REAL,
                directional_accuracy REAL,
                confidence_coverage REAL,
                bias REAL,
                sample_size INTEGER
            )
        """)

        # System health table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_health (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                uptime_percentage REAL,
                avg_response_time_ms REAL,
                error_rate REAL,
                memory_usage_mb REAL,
                cpu_usage_percent REAL,
                active_feeds INTEGER,
                degraded_feeds INTEGER,
                quarantined_feeds INTEGER
            )
        """)

        # Alerts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                severity TEXT NOT NULL,
                type TEXT NOT NULL,
                model TEXT,
                country TEXT,
                message TEXT NOT NULL,
                metrics TEXT
            )
        """)

        conn.commit()
        conn.close()

    def track_prediction(self, model_type: str, country: str, prediction: float,
                        actual: Optional[float] = None,
                        confidence_interval: Optional[Tuple[float, float]] = None,
                        features: Optional[Dict[str, Any]] = None):
        """Track a model prediction."""

        record = PredictionRecord(
            timestamp=datetime.now(),
            model_type=model_type,
            country=country,
            prediction=prediction,
            actual=actual,
            confidence_interval=confidence_interval,
            features_used=features
        )

        # Calculate error metrics if actual is available
        if actual is not None:
            record.error = prediction - actual
            record.squared_error = record.error ** 2
            # For directional accuracy, need previous actual
            # This is simplified - in production would track properly
            record.directional_accuracy = (prediction > 0) == (actual > 0)

        # Store in memory buffer
        key = f"{model_type}_{country}"
        self.recent_predictions[key].append(record)

        # Store in database
        self._save_prediction(record)

        # Check for alerts
        if actual is not None:
            self._check_performance_alerts(model_type, country)

    def _save_prediction(self, record: PredictionRecord):
        """Save prediction to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO predictions (
                timestamp, model_type, country, prediction, actual,
                confidence_low, confidence_high, features,
                error, squared_error, directional_accuracy
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.timestamp,
            record.model_type,
            record.country,
            record.prediction,
            record.actual,
            record.confidence_interval[0] if record.confidence_interval else None,
            record.confidence_interval[1] if record.confidence_interval else None,
            json.dumps(record.features_used) if record.features_used else None,
            record.error,
            record.squared_error,
            record.directional_accuracy
        ))

        conn.commit()
        conn.close()

    def calculate_metrics(self, model_type: str, country: str,
                         lookback_days: int = 30) -> Optional[PerformanceMetrics]:
        """Calculate performance metrics for a model/country combination."""

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get recent predictions with actuals
        cursor.execute("""
            SELECT prediction, actual, confidence_low, confidence_high, directional_accuracy
            FROM predictions
            WHERE model_type = ? AND country = ?
                AND actual IS NOT NULL
                AND timestamp >= datetime('now', '-{} days')
            ORDER BY timestamp DESC
        """.format(lookback_days), (model_type, country))

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return None

        predictions = np.array([r[0] for r in rows])
        actuals = np.array([r[1] for r in rows])
        conf_lows = np.array([r[2] for r in rows if r[2] is not None])
        conf_highs = np.array([r[3] for r in rows if r[3] is not None])
        directional = [r[4] for r in rows if r[4] is not None]

        # Calculate metrics
        errors = predictions - actuals
        mape = np.mean(np.abs(errors / (actuals + 1e-10))) * 100
        rmse = np.sqrt(np.mean(errors ** 2))
        mae = np.mean(np.abs(errors))
        bias = np.mean(errors)

        # Directional accuracy
        dir_accuracy = np.mean(directional) if directional else 0

        # Confidence interval coverage
        coverage = 0
        if len(conf_lows) > 0 and len(conf_highs) > 0:
            within_interval = (actuals[-len(conf_lows):] >= conf_lows) & \
                            (actuals[-len(conf_highs):] <= conf_highs)
            coverage = np.mean(within_interval)

        return PerformanceMetrics(
            mape=mape,
            rmse=rmse,
            mae=mae,
            directional_accuracy=dir_accuracy,
            confidence_coverage=coverage,
            bias=bias,
            sample_size=len(rows),
            last_updated=datetime.now()
        )

    def track_system_health(self, uptime_pct: float, avg_response_ms: float,
                           error_rate: float, memory_mb: float, cpu_pct: float,
                           active_feeds: int, degraded_feeds: int, quarantined_feeds: int):
        """Track system health metrics."""

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO system_health (
                uptime_percentage, avg_response_time_ms, error_rate,
                memory_usage_mb, cpu_usage_percent,
                active_feeds, degraded_feeds, quarantined_feeds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            uptime_pct, avg_response_ms, error_rate,
            memory_mb, cpu_pct,
            active_feeds, degraded_feeds, quarantined_feeds
        ))

        conn.commit()
        conn.close()

        # Check system health alerts
        self._check_system_alerts(error_rate, avg_response_ms)

    def _check_performance_alerts(self, model_type: str, country: str):
        """Check if performance has degraded enough to trigger alerts."""

        metrics = self.calculate_metrics(model_type, country, lookback_days=7)
        if not metrics:
            return

        alerts = []

        # Check MAPE threshold
        if metrics.mape > self.alert_thresholds["mape_critical"]:
            alerts.append(Alert(
                timestamp=datetime.now(),
                severity="critical",
                type="performance_degradation",
                model=model_type,
                country=country,
                message=f"Critical: {model_type} model for {country} MAPE is {metrics.mape:.1f}%",
                metrics={"mape": metrics.mape, "sample_size": metrics.sample_size}
            ))
        elif metrics.mape > self.alert_thresholds["mape_warning"]:
            alerts.append(Alert(
                timestamp=datetime.now(),
                severity="warning",
                type="performance_degradation",
                model=model_type,
                country=country,
                message=f"Warning: {model_type} model for {country} MAPE is {metrics.mape:.1f}%",
                metrics={"mape": metrics.mape, "sample_size": metrics.sample_size}
            ))

        # Check directional accuracy
        if metrics.directional_accuracy < self.alert_thresholds["directional_accuracy_warning"]:
            alerts.append(Alert(
                timestamp=datetime.now(),
                severity="warning",
                type="performance_degradation",
                model=model_type,
                country=country,
                message=f"Low directional accuracy: {metrics.directional_accuracy:.1%}",
                metrics={"directional_accuracy": metrics.directional_accuracy}
            ))

        # Save alerts
        for alert in alerts:
            self._save_alert(alert)

    def _check_system_alerts(self, error_rate: float, avg_response_ms: float):
        """Check system health and generate alerts if needed."""

        alerts = []

        if error_rate > self.alert_thresholds["error_rate_warning"]:
            alerts.append(Alert(
                timestamp=datetime.now(),
                severity="warning",
                type="system_error",
                model=None,
                country=None,
                message=f"High error rate: {error_rate:.1%}",
                metrics={"error_rate": error_rate}
            ))

        if avg_response_ms > self.alert_thresholds["response_time_warning"]:
            alerts.append(Alert(
                timestamp=datetime.now(),
                severity="warning",
                type="system_performance",
                model=None,
                country=None,
                message=f"Slow response time: {avg_response_ms:.0f}ms",
                metrics={"response_time_ms": avg_response_ms}
            ))

        for alert in alerts:
            self._save_alert(alert)

    def _save_alert(self, alert: Alert):
        """Save alert to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO alerts (severity, type, model, country, message, metrics)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            alert.severity,
            alert.type,
            alert.model,
            alert.country,
            alert.message,
            json.dumps(alert.metrics)
        ))

        conn.commit()
        conn.close()

        # Log alert
        if alert.severity == "critical":
            logger.error(alert.message)
        else:
            logger.warning(alert.message)

    def check_alerts(self, hours_back: int = 1) -> List[Dict[str, Any]]:
        """Get recent alerts."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT timestamp, severity, type, model, country, message, metrics
            FROM alerts
            WHERE timestamp >= datetime('now', '-{} hours')
            ORDER BY timestamp DESC
        """.format(hours_back))

        alerts = []
        for row in cursor.fetchall():
            alerts.append({
                "timestamp": row[0],
                "severity": row[1],
                "type": row[2],
                "model": row[3],
                "country": row[4],
                "message": row[5],
                "metrics": json.loads(row[6]) if row[6] else {}
            })

        conn.close()
        return alerts

    def get_current_metrics(self) -> Dict[str, Dict[str, PerformanceMetrics]]:
        """Get current performance metrics for all models."""

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get unique model/country combinations
        cursor.execute("""
            SELECT DISTINCT model_type, country
            FROM predictions
            WHERE actual IS NOT NULL
                AND timestamp >= datetime('now', '-30 days')
        """)

        metrics = defaultdict(dict)
        for model_type, country in cursor.fetchall():
            perf = self.calculate_metrics(model_type, country)
            if perf:
                metrics[model_type][country] = perf

        conn.close()
        return dict(metrics)

    def generate_performance_report(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """Generate comprehensive performance report."""

        report = {
            "generated_at": datetime.now().isoformat(),
            "performance_metrics": {},
            "system_health": {},
            "recent_alerts": [],
            "summary": {}
        }

        # Get performance metrics
        metrics = self.get_current_metrics()
        for model_type, countries in metrics.items():
            report["performance_metrics"][model_type] = {}
            for country, perf in countries.items():
                report["performance_metrics"][model_type][country] = {
                    "mape": perf.mape,
                    "rmse": perf.rmse,
                    "directional_accuracy": perf.directional_accuracy,
                    "confidence_coverage": perf.confidence_coverage,
                    "sample_size": perf.sample_size
                }

        # Get latest system health
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM system_health
            ORDER BY timestamp DESC
            LIMIT 1
        """)

        health_row = cursor.fetchone()
        if health_row:
            report["system_health"] = {
                "uptime_percentage": health_row[2],
                "avg_response_time_ms": health_row[3],
                "error_rate": health_row[4],
                "active_feeds": health_row[6],
                "degraded_feeds": health_row[7],
                "quarantined_feeds": health_row[8]
            }

        conn.close()

        # Get recent alerts
        report["recent_alerts"] = self.check_alerts(hours_back=24)

        # Generate summary
        if metrics:
            all_mapes = []
            for model_countries in metrics.values():
                for perf in model_countries.values():
                    all_mapes.append(perf.mape)

            report["summary"] = {
                "avg_mape": np.mean(all_mapes) if all_mapes else 0,
                "models_tracked": len(metrics),
                "total_predictions": sum(
                    perf.sample_size
                    for model_countries in metrics.values()
                    for perf in model_countries.values()
                ),
                "critical_alerts": len([a for a in report["recent_alerts"] if a["severity"] == "critical"])
            }

        # Save report if path provided
        if output_path:
            with open(output_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)

        return report