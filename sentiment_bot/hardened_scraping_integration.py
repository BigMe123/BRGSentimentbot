#!/usr/bin/env python3
"""
Hardened Scraping Integration
============================

Integrates enhanced scraping capabilities into the existing BSG system with
comprehensive error handling, monitoring, and fallback mechanisms.
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime, timedelta
import json
from pathlib import Path

from .enhanced_stable_scraper import EnhancedStableScraper, create_enhanced_scraper
from .scraping_monitor import ScrapingMonitor, create_scraping_monitor, console_alert_callback
from .stable_scraper import StableScraper  # Fallback scraper
from .unified_source_manager import get_unified_sources
from .unified_source_selector import UnifiedSourceSelector, AnalysisMode

logger = logging.getLogger(__name__)

class HardenedScrapingManager:
    """
    Production-ready scraping manager with comprehensive error handling.

    Features:
    - Enhanced scraper with circuit breakers and rate limiting
    - Real-time monitoring and alerting
    - Automatic fallback to stable scraper
    - Performance optimization
    - Comprehensive error tracking
    """

    def __init__(self,
                 enable_monitoring: bool = True,
                 enable_fallback: bool = True,
                 max_concurrent: int = 50,
                 rate_limit: float = 10.0,
                 timeout: int = 15,
                 alert_callbacks: List[Callable] = None):
        """Initialize hardened scraping manager."""

        # Primary enhanced scraper
        self.enhanced_scraper = create_enhanced_scraper(
            max_concurrent=max_concurrent,
            rate_limit=rate_limit,
            timeout=timeout,
            enable_circuit_breakers=True,
            content_validation=True
        )

        # Fallback scraper
        self.fallback_scraper = StableScraper(
            max_retries=2,
            timeout=timeout,
            max_workers=min(max_concurrent, 20)
        ) if enable_fallback else None

        # Monitoring system
        self.monitor = create_scraping_monitor() if enable_monitoring else None
        if self.monitor:
            # Add default console callback
            self.monitor.add_alert_callback(console_alert_callback)

            # Add any custom callbacks
            if alert_callbacks:
                for callback in alert_callbacks:
                    self.monitor.add_alert_callback(callback)

        # Source managers
        self.source_manager = get_unified_sources()
        self.source_selector = UnifiedSourceSelector("config/master_sources_production.yaml")

        # Performance tracking
        self.scraping_stats = {
            'total_runs': 0,
            'successful_runs': 0,
            'fallback_used': 0,
            'avg_articles_per_run': 0.0,
            'avg_sources_per_run': 0.0,
            'last_run_time': None
        }

        logger.info("Hardened scraping manager initialized")

    async def fetch_articles_comprehensive(self,
                                         sources: List[Dict] = None,
                                         max_sources: int = 100,
                                         progress_callback: Callable = None,
                                         display_manager = None) -> Dict[str, Any]:
        """
        Comprehensive article fetching with error handling and monitoring.

        Returns:
            Dict containing articles, metadata, and performance stats
        """
        run_start_time = datetime.now()
        self.scraping_stats['total_runs'] += 1

        try:
            # Get sources if not provided
            if sources is None:
                # Use production sources with comprehensive selection
                selection = self.source_selector.select_for_mode(
                    AnalysisMode.SMART,
                    region=None,
                    min_sources=min(10, max_sources),
                    max_sources=max_sources
                )
                sources = selection.sources

            if not sources:
                logger.warning("No sources available for scraping")
                return self._create_empty_result("No sources available")

            # Limit sources to prevent overload
            if len(sources) > max_sources:
                sources = sources[:max_sources]
                logger.info(f"Limited to {max_sources} sources")

            logger.info(f"Starting comprehensive fetch from {len(sources)} sources")

            # Update display if provided
            if display_manager:
                display_manager.update_stage_progress(
                    display_manager.current_stage,
                    activity=f"Initializing enhanced scraper for {len(sources)} sources"
                )

            # Primary attempt with enhanced scraper
            result = await self._attempt_enhanced_scraping(
                sources, progress_callback, display_manager
            )

            # Check if we got reasonable results
            if self._is_result_acceptable(result, sources):
                logger.info(f"Enhanced scraping successful: {len(result.get('articles', []))} articles")
                self.scraping_stats['successful_runs'] += 1

                # Update monitoring
                if self.monitor:
                    scraper_report = self.enhanced_scraper.get_comprehensive_report()
                    self.monitor.update_metrics_from_scraper(scraper_report)

                return self._finalize_result(result, sources, run_start_time, "enhanced")

            # Fallback to stable scraper if available
            elif self.fallback_scraper:
                logger.warning("Enhanced scraper results unsatisfactory, trying fallback")

                if display_manager:
                    display_manager.update_stage_progress(
                        display_manager.current_stage,
                        activity="Enhanced scraper failed, using fallback scraper"
                    )

                fallback_result = await self._attempt_fallback_scraping(
                    sources, progress_callback, display_manager
                )

                if self._is_result_acceptable(fallback_result, sources):
                    logger.info(f"Fallback scraping successful: {len(fallback_result.get('articles', []))} articles")
                    self.scraping_stats['fallback_used'] += 1
                    return self._finalize_result(fallback_result, sources, run_start_time, "fallback")

            # Both scrapers failed
            logger.error("Both enhanced and fallback scrapers failed")
            return self._create_failure_result(sources, run_start_time)

        except Exception as e:
            logger.error(f"Critical error in comprehensive fetching: {e}")
            return self._create_failure_result(sources, run_start_time, str(e))

    async def _attempt_enhanced_scraping(self,
                                       sources: List[Dict],
                                       progress_callback: Callable,
                                       display_manager) -> Dict[str, Any]:
        """Attempt scraping with enhanced scraper."""
        try:
            # Enhanced progress callback that works with our monitoring
            def enhanced_progress_callback(completed, total, successful, failed, articles):
                if self.monitor:
                    # Update monitoring with real-time data
                    pass  # Monitoring is updated via scraper report

                # Call original callback
                if progress_callback:
                    progress_callback(completed, total, failed)

            # Fetch articles
            articles = await self.enhanced_scraper.fetch_multiple_sources_enhanced(
                sources,
                progress_callback=enhanced_progress_callback,
                display_manager=display_manager
            )

            return {
                'articles': articles,
                'scraper_type': 'enhanced',
                'scraper_report': self.enhanced_scraper.get_comprehensive_report()
            }

        except Exception as e:
            logger.error(f"Enhanced scraper failed: {e}")
            return {'articles': [], 'error': str(e)}

    async def _attempt_fallback_scraping(self,
                                       sources: List[Dict],
                                       progress_callback: Callable,
                                       display_manager) -> Dict[str, Any]:
        """Attempt scraping with fallback scraper."""
        try:
            # Convert async sources to sync format for stable scraper
            def sync_progress_callback(completed, total, failed):
                if display_manager:
                    display_manager.update_stage_progress(
                        display_manager.current_stage,
                        completed_items=completed,
                        total_items=total,
                        activity=f"Fallback scraper: {completed}/{total} ({failed} failed)"
                    )

                if progress_callback:
                    progress_callback(completed, total, failed)

            # Use sync scraper in thread pool
            loop = asyncio.get_event_loop()
            articles = await loop.run_in_executor(
                None,
                self.fallback_scraper.fetch_multiple_sources,
                sources,
                sync_progress_callback
            )

            return {
                'articles': articles,
                'scraper_type': 'fallback',
                'scraper_report': self.fallback_scraper.get_error_report()
            }

        except Exception as e:
            logger.error(f"Fallback scraper failed: {e}")
            return {'articles': [], 'error': str(e)}

    def _is_result_acceptable(self, result: Dict, sources: List[Dict]) -> bool:
        """Check if scraping result is acceptable."""
        if not result or 'articles' not in result:
            return False

        articles = result['articles']

        # Must have some articles
        if not articles:
            return False

        # Must have reasonable success rate
        min_articles_threshold = max(1, len(sources) * 0.1)  # At least 10% of sources should produce articles

        return len(articles) >= min_articles_threshold

    def _finalize_result(self,
                        result: Dict,
                        sources: List[Dict],
                        start_time: datetime,
                        scraper_type: str) -> Dict[str, Any]:
        """Finalize and enrich the scraping result."""
        articles = result.get('articles', [])
        duration = datetime.now() - start_time

        # Update stats
        self.scraping_stats['avg_articles_per_run'] = (
            (self.scraping_stats['avg_articles_per_run'] * (self.scraping_stats['total_runs'] - 1) + len(articles))
            / self.scraping_stats['total_runs']
        )

        self.scraping_stats['avg_sources_per_run'] = (
            (self.scraping_stats['avg_sources_per_run'] * (self.scraping_stats['total_runs'] - 1) + len(sources))
            / self.scraping_stats['total_runs']
        )

        self.scraping_stats['last_run_time'] = datetime.now()

        # Enrich result
        enriched_result = {
            'articles': articles,
            'metadata': {
                'total_sources': len(sources),
                'articles_fetched': len(articles),
                'scraper_used': scraper_type,
                'duration_seconds': duration.total_seconds(),
                'articles_per_source': len(articles) / len(sources) if sources else 0,
                'timestamp': datetime.now().isoformat(),
                'success': True
            },
            'performance': {
                'duration': duration.total_seconds(),
                'articles_per_second': len(articles) / duration.total_seconds() if duration.total_seconds() > 0 else 0,
                'sources_per_second': len(sources) / duration.total_seconds() if duration.total_seconds() > 0 else 0
            },
            'scraper_report': result.get('scraper_report', {}),
            'health_status': self.monitor.get_overall_health_status().value if self.monitor else "unknown"
        }

        logger.info(
            f"Scraping completed: {len(articles)} articles from {len(sources)} sources "
            f"in {duration.total_seconds():.1f}s using {scraper_type} scraper"
        )

        return enriched_result

    def _create_empty_result(self, reason: str) -> Dict[str, Any]:
        """Create empty result with metadata."""
        return {
            'articles': [],
            'metadata': {
                'total_sources': 0,
                'articles_fetched': 0,
                'scraper_used': 'none',
                'duration_seconds': 0,
                'timestamp': datetime.now().isoformat(),
                'success': False,
                'failure_reason': reason
            },
            'performance': {'duration': 0},
            'scraper_report': {},
            'health_status': 'unknown'
        }

    def _create_failure_result(self,
                             sources: List[Dict],
                             start_time: datetime,
                             error: str = None) -> Dict[str, Any]:
        """Create failure result with error information."""
        duration = datetime.now() - start_time

        return {
            'articles': [],
            'metadata': {
                'total_sources': len(sources) if sources else 0,
                'articles_fetched': 0,
                'scraper_used': 'failed',
                'duration_seconds': duration.total_seconds(),
                'timestamp': datetime.now().isoformat(),
                'success': False,
                'failure_reason': error or "All scrapers failed"
            },
            'performance': {'duration': duration.total_seconds()},
            'scraper_report': self.enhanced_scraper.get_comprehensive_report() if self.enhanced_scraper else {},
            'health_status': self.monitor.get_overall_health_status().value if self.monitor else "critical"
        }

    def get_health_report(self) -> Dict[str, Any]:
        """Get comprehensive health report."""
        base_report = {
            'scraping_stats': self.scraping_stats,
            'enhanced_scraper_available': self.enhanced_scraper is not None,
            'fallback_scraper_available': self.fallback_scraper is not None,
            'monitoring_enabled': self.monitor is not None,
            'timestamp': datetime.now().isoformat()
        }

        if self.monitor:
            base_report.update(self.monitor.get_health_report())

        return base_report

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get detailed performance metrics."""
        metrics = {
            'stats': self.scraping_stats,
            'enhanced_scraper_report': None,
            'fallback_scraper_report': None
        }

        if self.enhanced_scraper:
            metrics['enhanced_scraper_report'] = self.enhanced_scraper.get_comprehensive_report()

        if self.fallback_scraper:
            metrics['fallback_scraper_report'] = self.fallback_scraper.get_error_report()

        return metrics

    def reset_tracking(self):
        """Reset all tracking and monitoring data."""
        if self.enhanced_scraper:
            self.enhanced_scraper.reset_tracking()

        if self.monitor:
            # Reset monitor tracking would need to be implemented
            pass

        self.scraping_stats = {
            'total_runs': 0,
            'successful_runs': 0,
            'fallback_used': 0,
            'avg_articles_per_run': 0.0,
            'avg_sources_per_run': 0.0,
            'last_run_time': None
        }

        logger.info("All tracking data reset")

    async def test_scraping_health(self, test_sources: int = 5) -> Dict[str, Any]:
        """Perform health check on scraping system."""
        logger.info("Running scraping health test...")

        # Get a small set of sources for testing
        # Get test sources from production set
        selection = self.source_selector.select_for_mode(
            AnalysisMode.SMART,
            min_sources=1,
            max_sources=test_sources
        )
        test_source_list = selection.sources

        if not test_source_list:
            return {
                'healthy': False,
                'error': 'No sources available for testing',
                'timestamp': datetime.now().isoformat()
            }

        try:
            # Run a quick test scrape
            result = await self.fetch_articles_comprehensive(
                sources=test_source_list,
                max_sources=test_sources
            )

            success = result.get('metadata', {}).get('success', False)
            articles_count = len(result.get('articles', []))

            health_report = {
                'healthy': success and articles_count > 0,
                'test_sources': len(test_source_list),
                'articles_fetched': articles_count,
                'scraper_used': result.get('metadata', {}).get('scraper_used'),
                'duration': result.get('metadata', {}).get('duration_seconds'),
                'timestamp': datetime.now().isoformat()
            }

            if self.monitor:
                health_report['monitoring_status'] = self.monitor.get_overall_health_status().value

            return health_report

        except Exception as e:
            return {
                'healthy': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }


# Factory function for easy integration
def create_hardened_scraping_manager(**kwargs) -> HardenedScrapingManager:
    """Create a configured hardened scraping manager."""
    return HardenedScrapingManager(**kwargs)

# Integration functions for existing codebase
async def fetch_articles_with_enhanced_scraping(
    sources: List[Dict] = None,
    max_sources: int = 100,
    progress_callback: Callable = None,
    display_manager = None
) -> List[Dict]:
    """
    Drop-in replacement for existing article fetching with enhanced capabilities.
    Returns just the articles for backward compatibility.
    """
    manager = create_hardened_scraping_manager()

    result = await manager.fetch_articles_comprehensive(
        sources=sources,
        max_sources=max_sources,
        progress_callback=progress_callback,
        display_manager=display_manager
    )

    return result.get('articles', [])