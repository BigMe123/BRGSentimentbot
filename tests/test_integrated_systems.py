"""
Integration tests for all five core systems:
- Economic prediction models
- RSS monitoring infrastructure
- Real-time analysis pipelines
- Historical backtesting systems
- Performance monitoring
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List
import json
import sqlite3
from pathlib import Path

from sentiment_bot.core.economic_models import UnifiedEconomicModel, EconomicForecast
from sentiment_bot.core.rss_monitor import RSSMonitor, FeedHealth
from sentiment_bot.core.realtime_pipeline import RealtimeAnalysisPipeline
from sentiment_bot.core.backtest_system import HistoricalBacktestSystem, BacktestConfig
from sentiment_bot.core.performance_monitor import PerformanceMonitor


class TestIntegratedSystems:
    """Test all five systems working together."""

    @pytest.fixture
    def economic_model(self):
        return UnifiedEconomicModel()

    @pytest.fixture
    def rss_monitor(self):
        return RSSMonitor(check_interval=60)

    @pytest.fixture
    def realtime_pipeline(self):
        return RealtimeAnalysisPipeline()

    @pytest.fixture
    def backtest_system(self):
        return HistoricalBacktestSystem()

    @pytest.fixture
    def performance_monitor(self):
        return PerformanceMonitor()

    @pytest.mark.asyncio
    async def test_end_to_end_economic_analysis(self, economic_model, rss_monitor,
                                                realtime_pipeline, performance_monitor):
        """Test complete flow from RSS ingestion to economic prediction."""

        # Step 1: Monitor RSS feeds
        test_feeds = [
            "https://feeds.bbci.co.uk/news/business/rss.xml",
            "https://www.ft.com/companies?format=rss"
        ]

        healthy_feeds = []
        for feed_url in test_feeds:
            health, items = await rss_monitor.check_feed(feed_url)
            if health.status == "healthy":
                healthy_feeds.append(feed_url)

        assert len(healthy_feeds) > 0, "Need at least one healthy feed"

        # Step 2: Process through real-time pipeline
        articles_processed = []
        async for article in realtime_pipeline.process_stream(
            healthy_feeds,
            target_region="united_kingdom",
            target_topics=["economy", "gdp", "inflation"]
        ):
            articles_processed.append(article)
            if len(articles_processed) >= 10:
                break

        assert len(articles_processed) > 0, "Should process some articles"

        # Step 3: Generate economic predictions
        sentiment_data = {
            "aggregate_sentiment": sum(a.sentiment_score for a in articles_processed) / len(articles_processed),
            "volume": len(articles_processed),
            "topics": [topic for a in articles_processed for topic in a.topics]
        }

        gdp_forecast = economic_model.forecast_gdp(
            "united_kingdom",
            sentiment_data,
            horizon="nowcast"
        )

        assert gdp_forecast.point_estimate is not None
        assert gdp_forecast.confidence_low <= gdp_forecast.point_estimate <= gdp_forecast.confidence_high

        # Step 4: Track performance
        performance_monitor.track_prediction(
            model_type="gdp",
            country="united_kingdom",
            prediction=gdp_forecast.point_estimate,
            confidence_interval=(gdp_forecast.confidence_low, gdp_forecast.confidence_high)
        )

        metrics = performance_monitor.get_current_metrics()
        assert "gdp" in metrics
        assert "united_kingdom" in metrics["gdp"]

    def test_backtest_with_real_models(self, backtest_system, economic_model):
        """Test backtesting system with actual economic models."""

        config = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2024, 1, 1),
            rebalance_frequency="monthly",
            initial_capital=1_000_000,
            countries=["united_states", "united_kingdom", "germany"],
            metrics_to_track=["gdp", "cpi", "employment"]
        )

        results = backtest_system.run_comprehensive_backtest(config)

        # Verify results structure
        assert "united_states" in results
        assert "united_kingdom" in results
        assert "germany" in results

        # Check metrics
        for country, result in results.items():
            assert result.total_return is not None
            assert result.sharpe_ratio is not None
            assert result.mape >= 0
            assert 0 <= result.directional_accuracy <= 1

    @pytest.mark.asyncio
    async def test_rss_health_monitoring_with_quarantine(self, rss_monitor):
        """Test RSS monitoring with quarantine functionality."""

        # Simulate feed failures
        bad_feed = "https://invalid.feed.example.com/rss"

        # First check - should fail
        health1, _ = await rss_monitor.check_feed(bad_feed)
        assert health1.status in ["error", "timeout"]

        # Check if quarantined after multiple failures
        for _ in range(3):
            await rss_monitor.check_feed(bad_feed)

        quarantined = await rss_monitor.is_quarantined(bad_feed)
        assert quarantined, "Feed should be quarantined after multiple failures"

        # Verify quarantine prevents immediate rechecking
        health2, _ = await rss_monitor.check_feed(bad_feed)
        assert health2.status == "quarantined"

    @pytest.mark.asyncio
    async def test_realtime_pipeline_deduplication(self, realtime_pipeline):
        """Test that real-time pipeline properly deduplicates articles."""

        # Create mock feed with duplicate content
        mock_articles = [
            {"title": "UK GDP grows 2%", "content": "The UK economy expanded..."},
            {"title": "Britain's GDP up 2%", "content": "The UK economy expanded..."},  # Duplicate
            {"title": "US inflation falls", "content": "American CPI decreased..."}
        ]

        processed = []
        for article in mock_articles:
            result = await realtime_pipeline._process_article(article)
            if result:
                processed.append(result)

        # Should deduplicate similar articles
        assert len(processed) == 2, "Should remove duplicate UK GDP article"

    def test_economic_model_ensemble(self, economic_model):
        """Test that economic model uses ensemble methods."""

        sentiment_data = {
            "aggregate_sentiment": 0.3,
            "volume": 100,
            "topics": ["growth", "recovery", "employment"]
        }

        # Test multiple horizons
        nowcast = economic_model.forecast_gdp("united_states", sentiment_data, horizon="nowcast")
        forecast_1q = economic_model.forecast_gdp("united_states", sentiment_data, horizon="1q")
        forecast_1y = economic_model.forecast_gdp("united_states", sentiment_data, horizon="1y")

        # Verify uncertainty increases with horizon
        nowcast_range = nowcast.confidence_high - nowcast.confidence_low
        forecast_1q_range = forecast_1q.confidence_high - forecast_1q.confidence_low
        forecast_1y_range = forecast_1y.confidence_high - forecast_1y.confidence_low

        assert forecast_1q_range >= nowcast_range, "Uncertainty should increase with horizon"
        assert forecast_1y_range >= forecast_1q_range, "Uncertainty should increase with horizon"

    def test_backtest_crisis_periods(self, backtest_system):
        """Test that backtesting handles crisis periods correctly."""

        # Test COVID period
        covid_config = BacktestConfig(
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2021, 1, 1),
            rebalance_frequency="weekly",  # More frequent during crisis
            initial_capital=1_000_000,
            countries=["united_states"],
            metrics_to_track=["gdp", "employment"]
        )

        results = backtest_system.run_comprehensive_backtest(covid_config)

        # During crisis, volatility should be higher
        assert results["united_states"].max_drawdown > 0.1, "Should show significant drawdown during COVID"

    @pytest.mark.asyncio
    async def test_performance_monitoring_alerts(self, performance_monitor):
        """Test performance monitoring alert system."""

        # Track predictions with degrading performance
        for i in range(10):
            error = 0.02 * (i + 1)  # Increasing error
            performance_monitor.track_prediction(
                model_type="gdp",
                country="united_states",
                prediction=2.0 + error,
                actual=2.0 if i > 0 else None
            )

        # Check for performance alerts
        alerts = performance_monitor.check_alerts()
        assert len(alerts) > 0, "Should generate alerts for degrading performance"

        # Verify alert contains relevant info
        alert = alerts[0]
        assert "gdp" in alert["model"]
        assert "performance_degradation" in alert["type"]

    def test_database_persistence(self, backtest_system, performance_monitor):
        """Test that results are properly persisted to database."""

        db_path = Path("state/backtest_results.db")

        # Run backtest
        config = BacktestConfig(
            start_date=datetime(2023, 6, 1),
            end_date=datetime(2023, 7, 1),
            rebalance_frequency="daily",
            initial_capital=100_000,
            countries=["united_kingdom"],
            metrics_to_track=["gdp"]
        )

        results = backtest_system.run_comprehensive_backtest(config)

        # Save to database
        backtest_system.save_results(results, db_path)

        # Verify persistence
        assert db_path.exists()

        # Query saved results
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM backtest_results WHERE country = ?", ("united_kingdom",))
        count = cursor.fetchone()[0]
        conn.close()

        assert count > 0, "Results should be saved to database"

    @pytest.mark.asyncio
    async def test_complete_system_integration(self, economic_model, rss_monitor,
                                              realtime_pipeline, backtest_system,
                                              performance_monitor):
        """Test all five systems working together in a realistic scenario."""

        # 1. Start monitoring RSS feeds
        feeds = ["https://feeds.bbci.co.uk/news/business/rss.xml"]
        health_status = {}

        for feed in feeds:
            health, items = await rss_monitor.check_feed(feed)
            health_status[feed] = health

        # 2. Process real-time data
        articles = []
        async for article in realtime_pipeline.process_stream(feeds, target_region="europe"):
            articles.append(article)
            if len(articles) >= 5:
                break

        # 3. Generate predictions
        if articles:
            sentiment_data = {
                "aggregate_sentiment": sum(a.sentiment_score for a in articles) / len(articles),
                "volume": len(articles),
                "topics": list(set(topic for a in articles for topic in a.topics))
            }

            forecast = economic_model.forecast_gdp("germany", sentiment_data)

            # 4. Track performance
            performance_monitor.track_prediction(
                model_type="gdp",
                country="germany",
                prediction=forecast.point_estimate
            )

            # 5. Run mini backtest
            config = BacktestConfig(
                start_date=datetime.now() - timedelta(days=30),
                end_date=datetime.now(),
                rebalance_frequency="weekly",
                initial_capital=10_000,
                countries=["germany"],
                metrics_to_track=["gdp"]
            )

            backtest_results = backtest_system.run_comprehensive_backtest(config)

            # Verify complete integration
            assert health_status[feeds[0]].status in ["healthy", "degraded", "error"]
            assert len(articles) > 0
            assert forecast.point_estimate is not None
            assert "germany" in backtest_results

            # Check performance metrics
            metrics = performance_monitor.get_current_metrics()
            assert "gdp" in metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v"])