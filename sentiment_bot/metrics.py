"""
Observability metrics and alerts for the pipeline.
Implements Phase 5 of the performance optimization plan.
"""

import time
import logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from collections import deque
import statistics
import json

logger = logging.getLogger(__name__)


@dataclass
class MetricSnapshot:
    """Point-in-time metric snapshot."""
    timestamp: float
    name: str
    value: float
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class Alert:
    """Alert triggered by metric threshold."""
    timestamp: float
    severity: str  # 'warning', 'error', 'critical'
    metric: str
    condition: str
    value: float
    threshold: float
    message: str


class MetricsCollector:
    """
    Collects and tracks pipeline metrics with alerting.
    
    Tracks all required SLO metrics:
    - Fetch success rate (>80%)
    - P95 fetch latency (<8s)
    - Headless usage rate (<10%)
    - Source concentration (top-1 <30%, top-3 <60%)
    - Freshness (>60% published <24h)
    """
    
    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        
        # Metric windows for percentile calculations
        self.fetch_latencies: deque = deque(maxlen=window_size)
        self.doc_lengths: deque = deque(maxlen=window_size)
        self.article_ages: deque = deque(maxlen=window_size)
        
        # Counters
        self.counters = {
            'unique_domains': set(),
            'articles_ingested': 0,
            'words_ingested': 0,
            'fetch_attempts': 0,
            'fetch_successes': 0,
            'fetch_timeouts': 0,
            'fetch_errors': 0,
            'headless_uses': 0,
            'robots_denied': 0,
            'circuit_opens': 0,
            'dedup_drops': 0,
            'fresh_articles': 0,
            'stale_articles': 0,
        }
        
        # Domain-specific metrics
        self.domain_metrics: Dict[str, Dict[str, Any]] = {}
        self.domain_words: Dict[str, int] = {}
        
        # Alerts
        self.alerts: List[Alert] = []
        self.alert_callbacks: List[Callable[[Alert], None]] = []
        
        # Start time
        self.start_time = time.time()
    
    def record_fetch(
        self,
        domain: str,
        success: bool,
        latency_ms: int,
        status: str,
        headless: bool = False
    ):
        """Record a fetch attempt."""
        self.counters['fetch_attempts'] += 1
        self.counters['unique_domains'].add(domain)
        
        if success:
            self.counters['fetch_successes'] += 1
            self.fetch_latencies.append(latency_ms)
        else:
            if status == 'timeout':
                self.counters['fetch_timeouts'] += 1
            elif status == 'robots_denied':
                self.counters['robots_denied'] += 1
            else:
                self.counters['fetch_errors'] += 1
        
        if headless:
            self.counters['headless_uses'] += 1
        
        # Update domain metrics
        if domain not in self.domain_metrics:
            self.domain_metrics[domain] = {
                'attempts': 0,
                'successes': 0,
                'timeouts': 0,
                'errors': 0,
                'total_latency': 0,
                'headless_uses': 0,
            }
        
        dm = self.domain_metrics[domain]
        dm['attempts'] += 1
        if success:
            dm['successes'] += 1
            dm['total_latency'] += latency_ms
        elif status == 'timeout':
            dm['timeouts'] += 1
        else:
            dm['errors'] += 1
        
        if headless:
            dm['headless_uses'] += 1
    
    def record_article(
        self,
        domain: str,
        word_count: int,
        published: Optional[datetime],
        was_deduped: bool = False
    ):
        """Record an article ingestion."""
        if was_deduped:
            self.counters['dedup_drops'] += 1
            return
        
        self.counters['articles_ingested'] += 1
        self.counters['words_ingested'] += word_count
        self.doc_lengths.append(word_count)
        
        # Track domain words for skew calculation
        if domain not in self.domain_words:
            self.domain_words[domain] = 0
        self.domain_words[domain] += word_count
        
        # Track freshness
        if published:
            now = datetime.now(timezone.utc)
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            
            age_hours = (now - published).total_seconds() / 3600
            self.article_ages.append(age_hours)
            
            if age_hours <= 24:
                self.counters['fresh_articles'] += 1
            else:
                self.counters['stale_articles'] += 1
    
    def record_circuit_open(self, domain: str):
        """Record a circuit breaker opening."""
        self.counters['circuit_opens'] += 1
        logger.warning(f"Circuit opened for {domain}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Calculate all metrics."""
        metrics = {}
        
        # Basic counts
        metrics['unique_domains'] = len(self.counters['unique_domains'])
        metrics['articles_ingested'] = self.counters['articles_ingested']
        metrics['words_ingested'] = self.counters['words_ingested']
        
        # Fetch metrics
        if self.counters['fetch_attempts'] > 0:
            metrics['fetch_success_rate'] = (
                self.counters['fetch_successes'] / self.counters['fetch_attempts']
            )
            metrics['timeout_rate'] = (
                self.counters['fetch_timeouts'] / self.counters['fetch_attempts']
            )
            metrics['headless_usage_rate'] = (
                self.counters['headless_uses'] / self.counters['fetch_attempts']
            )
        else:
            metrics['fetch_success_rate'] = 0
            metrics['timeout_rate'] = 0
            metrics['headless_usage_rate'] = 0
        
        # Latency percentiles
        if self.fetch_latencies:
            sorted_latencies = sorted(self.fetch_latencies)
            metrics['p50_fetch_latency_ms'] = sorted_latencies[len(sorted_latencies) // 2]
            metrics['p95_fetch_latency_ms'] = sorted_latencies[int(len(sorted_latencies) * 0.95)]
            metrics['p99_fetch_latency_ms'] = sorted_latencies[int(len(sorted_latencies) * 0.99)]
            metrics['avg_fetch_latency_ms'] = statistics.mean(self.fetch_latencies)
        else:
            metrics['p50_fetch_latency_ms'] = 0
            metrics['p95_fetch_latency_ms'] = 0
            metrics['p99_fetch_latency_ms'] = 0
            metrics['avg_fetch_latency_ms'] = 0
        
        # Document length metrics
        if self.doc_lengths:
            sorted_lengths = sorted(self.doc_lengths)
            metrics['avg_doc_length'] = statistics.mean(self.doc_lengths)
            metrics['p95_doc_length'] = sorted_lengths[int(len(sorted_lengths) * 0.95)]
        else:
            metrics['avg_doc_length'] = 0
            metrics['p95_doc_length'] = 0
        
        # Source concentration (word share)
        total_words = sum(self.domain_words.values())
        if total_words > 0:
            word_shares = [
                (domain, words / total_words)
                for domain, words in self.domain_words.items()
            ]
            word_shares.sort(key=lambda x: x[1], reverse=True)
            
            metrics['top1_source_share'] = word_shares[0][1] if word_shares else 0
            metrics['top3_source_share'] = sum(s[1] for s in word_shares[:3])
            metrics['top1_source_domain'] = word_shares[0][0] if word_shares else None
        else:
            metrics['top1_source_share'] = 0
            metrics['top3_source_share'] = 0
            metrics['top1_source_domain'] = None
        
        # Freshness metrics
        total_articles = (
            self.counters['fresh_articles'] + self.counters['stale_articles']
        )
        if total_articles > 0:
            metrics['fraction_published_24h'] = (
                self.counters['fresh_articles'] / total_articles
            )
        else:
            metrics['fraction_published_24h'] = 0
        
        if self.article_ages:
            metrics['median_article_age_hours'] = statistics.median(self.article_ages)
        else:
            metrics['median_article_age_hours'] = 0
        
        # Dedup and circuit metrics
        metrics['dedup_drop_rate'] = (
            self.counters['dedup_drops'] / 
            (self.counters['articles_ingested'] + self.counters['dedup_drops'])
            if self.counters['articles_ingested'] + self.counters['dedup_drops'] > 0
            else 0
        )
        metrics['robots_denied_count'] = self.counters['robots_denied']
        metrics['circuit_opened_count'] = self.counters['circuit_opens']
        
        # Runtime
        metrics['runtime_seconds'] = time.time() - self.start_time
        
        return metrics
    
    def check_alerts(self) -> List[Alert]:
        """Check metrics against SLO thresholds and generate alerts."""
        metrics = self.get_metrics()
        new_alerts = []
        
        # Define alert conditions
        alert_conditions = [
            # Error level alerts
            ('error', 'fetch_success_rate', '<', 0.70, 
             "Fetch success rate critically low"),
            ('error', 'p95_fetch_latency_ms', '>', 8000,
             "P95 fetch latency exceeds 8s SLO"),
            ('error', 'top1_source_share', '>', 0.30,
             "Single source dominates >30% of content"),
            ('error', 'top3_source_share', '>', 0.60,
             "Top 3 sources dominate >60% of content"),
            ('error', 'fraction_published_24h', '<', 0.60,
             "Less than 60% of articles are fresh (<24h)"),
            ('error', 'timeout_rate', '>', 0.15,
             "Timeout rate exceeds 15%"),
            ('error', 'headless_usage_rate', '>', 0.10,
             "Headless browser usage exceeds 10%"),
            
            # Warning level alerts
            ('warning', 'fetch_success_rate', '<', 0.80,
             "Fetch success rate below 80% target"),
            ('warning', 'p95_fetch_latency_ms', '>', 6000,
             "P95 fetch latency approaching SLO (>6s)"),
            ('warning', 'top1_source_share', '>', 0.25,
             "Single source approaching dominance threshold"),
            ('warning', 'fraction_published_24h', '<', 0.70,
             "Freshness declining below 70%"),
        ]
        
        for severity, metric_name, operator, threshold, message in alert_conditions:
            if metric_name not in metrics:
                continue
            
            value = metrics[metric_name]
            triggered = False
            
            if operator == '<' and value < threshold:
                triggered = True
            elif operator == '>' and value > threshold:
                triggered = True
            
            if triggered:
                alert = Alert(
                    timestamp=time.time(),
                    severity=severity,
                    metric=metric_name,
                    condition=f"{operator} {threshold}",
                    value=value,
                    threshold=threshold,
                    message=f"{message}: {metric_name}={value:.3f}"
                )
                new_alerts.append(alert)
                self.alerts.append(alert)
                
                # Trigger callbacks
                for callback in self.alert_callbacks:
                    try:
                        callback(alert)
                    except Exception as e:
                        logger.error(f"Alert callback error: {e}")
        
        return new_alerts
    
    def add_alert_callback(self, callback: Callable[[Alert], None]):
        """Add a callback for when alerts are triggered."""
        self.alert_callbacks.append(callback)
    
    def get_summary(self) -> str:
        """Get a human-readable summary of metrics."""
        metrics = self.get_metrics()
        
        summary = [
            "=== Pipeline Metrics Summary ===",
            f"Runtime: {metrics['runtime_seconds']:.1f}s",
            f"Domains: {metrics['unique_domains']}",
            f"Articles: {metrics['articles_ingested']}",
            f"Words: {metrics['words_ingested']:,}",
            "",
            "=== Fetch Performance ===",
            f"Success Rate: {metrics['fetch_success_rate']:.1%}",
            f"P95 Latency: {metrics['p95_fetch_latency_ms']}ms",
            f"Timeout Rate: {metrics['timeout_rate']:.1%}",
            f"Headless Usage: {metrics['headless_usage_rate']:.1%}",
            "",
            "=== Content Quality ===",
            f"Fresh (<24h): {metrics['fraction_published_24h']:.1%}",
            f"Median Age: {metrics['median_article_age_hours']:.1f}h",
            f"Avg Doc Length: {metrics['avg_doc_length']:.0f} words",
            f"Dedup Rate: {metrics['dedup_drop_rate']:.1%}",
            "",
            "=== Source Distribution ===",
            f"Top Source: {metrics.get('top1_source_domain', 'N/A')} "
            f"({metrics['top1_source_share']:.1%})",
            f"Top 3 Share: {metrics['top3_source_share']:.1%}",
            "",
            "=== Circuit Breakers ===",
            f"Circuits Opened: {metrics['circuit_opened_count']}",
            f"Robots Denied: {metrics['robots_denied_count']}",
        ]
        
        # Add alerts if any
        recent_alerts = [a for a in self.alerts if time.time() - a.timestamp < 300]
        if recent_alerts:
            summary.append("")
            summary.append("=== Recent Alerts ===")
            for alert in recent_alerts[-5:]:
                summary.append(
                    f"[{alert.severity.upper()}] {alert.message}"
                )
        
        return "\n".join(summary)
    
    def export_metrics(self, format: str = 'json') -> str:
        """Export metrics in various formats."""
        metrics = self.get_metrics()
        
        if format == 'json':
            return json.dumps(metrics, indent=2)
        elif format == 'prometheus':
            lines = []
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    lines.append(f"pipeline_{key} {value}")
            return "\n".join(lines)
        else:
            return str(metrics)