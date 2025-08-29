"""
Health Monitoring & Auto-Tuning System
Tracks source performance and automatically adjusts priorities.
"""

import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
import statistics

from .skb_catalog import get_catalog, SourceRecord

logger = logging.getLogger(__name__)

@dataclass
class SourceMetrics:
    """Performance metrics for a single source."""
    domain: str
    
    # Success metrics
    fetch_attempts: int = 0
    fetch_successes: int = 0
    fetch_failures: int = 0
    
    # Yield metrics
    total_articles: int = 0
    fresh_articles: int = 0  # <24h old
    total_words: int = 0
    fresh_words: int = 0
    
    # Latency metrics (rolling window)
    latencies: deque = field(default_factory=lambda: deque(maxlen=100))
    
    # Error tracking
    error_types: Dict[str, int] = field(default_factory=dict)
    last_error: Optional[str] = None
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    
    # Relevance metrics
    relevance_scores: deque = field(default_factory=lambda: deque(maxlen=100))
    articles_dropped: int = 0
    
    @property
    def success_rate(self) -> float:
        if self.fetch_attempts == 0:
            return 0.0
        return self.fetch_successes / self.fetch_attempts
    
    @property
    def freshness_rate(self) -> float:
        if self.total_articles == 0:
            return 0.0
        return self.fresh_articles / self.total_articles
    
    @property
    def avg_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return statistics.mean(self.latencies)
    
    @property
    def avg_yield(self) -> float:
        if self.fetch_successes == 0:
            return 0.0
        return self.fresh_words / max(1, self.fetch_successes)
    
    @property
    def avg_relevance(self) -> float:
        if not self.relevance_scores:
            return 0.5
        return statistics.mean(self.relevance_scores)
    
    @property
    def health_score(self) -> float:
        """Overall health score (0-1)."""
        score = 0.0
        
        # Success rate (40% weight)
        score += self.success_rate * 0.4
        
        # Freshness (30% weight)
        score += self.freshness_rate * 0.3
        
        # Yield (20% weight)
        yield_normalized = min(1.0, self.avg_yield / 1000)  # Normalize to 1000 words
        score += yield_normalized * 0.2
        
        # Low latency bonus (10% weight)
        if self.avg_latency > 0:
            latency_score = max(0, 1.0 - (self.avg_latency / 10000))  # 10s baseline
            score += latency_score * 0.1
        
        return score


class HealthMonitor:
    """Monitors source health and performs auto-tuning."""
    
    def __init__(self):
        self.catalog = get_catalog()
        self.metrics: Dict[str, SourceMetrics] = {}
        self.run_history: deque = deque(maxlen=100)
        
        # Auto-tuning thresholds
        self.promotion_threshold = 0.7  # Health score for promotion
        self.demotion_threshold = 0.3   # Health score for demotion
        self.parking_threshold = 0.1    # Health score for parking
        
    def record_fetch_result(self,
                           domain: str,
                           success: bool,
                           latency_ms: float,
                           error_type: Optional[str] = None):
        """Record fetch attempt result."""
        
        if domain not in self.metrics:
            self.metrics[domain] = SourceMetrics(domain=domain)
        
        metrics = self.metrics[domain]
        metrics.fetch_attempts += 1
        
        if success:
            metrics.fetch_successes += 1
            metrics.last_success = datetime.now()
        else:
            metrics.fetch_failures += 1
            metrics.last_failure = datetime.now()
            if error_type:
                metrics.error_types[error_type] = metrics.error_types.get(error_type, 0) + 1
                metrics.last_error = error_type
        
        metrics.latencies.append(latency_ms)
    
    def record_article_metrics(self,
                              domain: str,
                              total_articles: int,
                              fresh_articles: int,
                              total_words: int,
                              fresh_words: int):
        """Record article yield metrics."""
        
        if domain not in self.metrics:
            self.metrics[domain] = SourceMetrics(domain=domain)
        
        metrics = self.metrics[domain]
        metrics.total_articles += total_articles
        metrics.fresh_articles += fresh_articles
        metrics.total_words += total_words
        metrics.fresh_words += fresh_words
    
    def record_relevance(self,
                        domain: str,
                        relevance_score: float,
                        dropped: bool = False):
        """Record relevance scoring."""
        
        if domain not in self.metrics:
            self.metrics[domain] = SourceMetrics(domain=domain)
        
        metrics = self.metrics[domain]
        metrics.relevance_scores.append(relevance_score)
        
        if dropped:
            metrics.articles_dropped += 1
    
    def auto_tune_sources(self, dry_run: bool = False) -> Dict[str, List[str]]:
        """
        Automatically tune source priorities based on performance.
        
        Returns:
            Dict of actions taken: promoted, demoted, parked
        """
        actions = {
            'promoted': [],
            'demoted': [],
            'parked': []
        }
        
        for domain, metrics in self.metrics.items():
            # Skip if not enough data
            if metrics.fetch_attempts < 5:
                continue
            
            health_score = metrics.health_score
            
            # Check for parking (dead sources)
            if health_score < self.parking_threshold:
                # Check if consistently failing
                if metrics.fetch_failures >= 10 and metrics.success_rate < 0.1:
                    logger.info(f"Parking dead source {domain} (health: {health_score:.2f})")
                    if not dry_run:
                        self.catalog.park_source(domain)
                    actions['parked'].append(domain)
                    continue
            
            # Get current source priority
            sources = self.catalog.get_sources_by_criteria(
                policies=['allow'],
                limit=10000
            )
            
            current_source = None
            for source in sources:
                if source.domain == domain:
                    current_source = source
                    break
            
            if not current_source:
                continue
            
            # Auto-tune priority
            old_priority = current_source.priority
            new_priority = old_priority
            
            if health_score > self.promotion_threshold:
                # Promote high-performing sources
                new_priority = min(1.0, old_priority * 1.1)
                if new_priority > old_priority:
                    actions['promoted'].append(domain)
            
            elif health_score < self.demotion_threshold:
                # Demote poor-performing sources
                new_priority = max(0.1, old_priority * 0.9)
                if new_priority < old_priority:
                    actions['demoted'].append(domain)
            
            # Update catalog with new metrics
            if not dry_run:
                self.catalog.update_source_stats(
                    domain=domain,
                    yield_words=metrics.avg_yield,
                    success=metrics.success_rate > 0.5,
                    error_msg=metrics.last_error
                )
        
        # Log summary
        if actions['promoted']:
            logger.info(f"Promoted {len(actions['promoted'])} sources")
        if actions['demoted']:
            logger.info(f"Demoted {len(actions['demoted'])} sources")
        if actions['parked']:
            logger.info(f"Parked {len(actions['parked'])} dead sources")
        
        return actions
    
    def get_run_metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics for the current run."""
        
        total_sources = len(self.metrics)
        if total_sources == 0:
            return {}
        
        # Aggregate metrics
        total_attempts = sum(m.fetch_attempts for m in self.metrics.values())
        total_successes = sum(m.fetch_successes for m in self.metrics.values())
        total_articles = sum(m.total_articles for m in self.metrics.values())
        fresh_articles = sum(m.fresh_articles for m in self.metrics.values())
        fresh_words = sum(m.fresh_words for m in self.metrics.values())
        
        # Calculate averages
        avg_latency = statistics.mean(
            m.avg_latency for m in self.metrics.values() if m.latencies
        ) if any(m.latencies for m in self.metrics.values()) else 0
        
        avg_relevance = statistics.mean(
            m.avg_relevance for m in self.metrics.values() if m.relevance_scores
        ) if any(m.relevance_scores for m in self.metrics.values()) else 0
        
        # Error distribution
        all_errors = defaultdict(int)
        for m in self.metrics.values():
            for error_type, count in m.error_types.items():
                all_errors[error_type] += count
        
        return {
            'total_sources': total_sources,
            'fetch_attempts': total_attempts,
            'fetch_success_rate': total_successes / total_attempts if total_attempts > 0 else 0,
            'total_articles': total_articles,
            'fresh_articles': fresh_articles,
            'freshness_rate': fresh_articles / total_articles if total_articles > 0 else 0,
            'fresh_words': fresh_words,
            'avg_latency_ms': avg_latency,
            'avg_relevance': avg_relevance,
            'error_distribution': dict(all_errors),
            'sources_by_health': self._categorize_by_health()
        }
    
    def _categorize_by_health(self) -> Dict[str, int]:
        """Categorize sources by health score."""
        categories = {
            'excellent': 0,  # >0.8
            'good': 0,       # 0.6-0.8
            'fair': 0,       # 0.4-0.6
            'poor': 0,       # 0.2-0.4
            'critical': 0    # <0.2
        }
        
        for metrics in self.metrics.values():
            if metrics.fetch_attempts < 3:
                continue  # Not enough data
            
            health = metrics.health_score
            if health > 0.8:
                categories['excellent'] += 1
            elif health > 0.6:
                categories['good'] += 1
            elif health > 0.4:
                categories['fair'] += 1
            elif health > 0.2:
                categories['poor'] += 1
            else:
                categories['critical'] += 1
        
        return categories
    
    def get_source_report(self, domain: str) -> Optional[Dict[str, Any]]:
        """Get detailed health report for a specific source."""
        
        if domain not in self.metrics:
            return None
        
        metrics = self.metrics[domain]
        
        return {
            'domain': domain,
            'health_score': metrics.health_score,
            'fetch_attempts': metrics.fetch_attempts,
            'success_rate': metrics.success_rate,
            'avg_latency_ms': metrics.avg_latency,
            'freshness_rate': metrics.freshness_rate,
            'avg_yield_words': metrics.avg_yield,
            'avg_relevance': metrics.avg_relevance,
            'articles_dropped': metrics.articles_dropped,
            'error_types': dict(metrics.error_types),
            'last_success': metrics.last_success.isoformat() if metrics.last_success else None,
            'last_failure': metrics.last_failure.isoformat() if metrics.last_failure else None,
            'last_error': metrics.last_error
        }
    
    def export_metrics(self) -> Dict[str, Any]:
        """Export all metrics for analysis."""
        return {
            'timestamp': datetime.now().isoformat(),
            'run_metrics': self.get_run_metrics(),
            'source_metrics': {
                domain: self.get_source_report(domain)
                for domain in self.metrics.keys()
            }
        }


# Global instance
_monitor_instance = None

def get_monitor() -> HealthMonitor:
    """Get global health monitor instance."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = HealthMonitor()
    return _monitor_instance