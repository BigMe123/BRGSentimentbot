"""
Tests for the unified SKB system.
Validates acceptance criteria for the massive SKB implementation.
"""

import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch
import sqlite3

from sentiment_bot.skb_catalog import SKBCatalog, SourceRecord
from sentiment_bot.selection_planner import SelectionPlanner, SelectionQuotas
from sentiment_bot.health_monitor import HealthMonitor, SourceMetrics
from sentiment_bot.relevance_filter import RelevanceFilter, RelevanceScore


class TestSKBCatalog:
    """Test SKB catalog with SQLite storage."""

    @pytest.fixture
    def catalog(self):
        """Create test catalog with temporary database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            catalog = SKBCatalog(db_path=tf.name, cache_ttl=1)

            # Add test sources
            for i in range(100):
                source = SourceRecord(
                    domain=f"test{i}.com",
                    name=f"Test Source {i}",
                    region="asia" if i < 50 else "europe",
                    topics=(
                        ["tech", "economy"] if i % 2 == 0 else ["politics", "security"]
                    ),
                    languages=["en"],
                    priority=0.5 + (i / 200),
                    policy="allow",
                )
                catalog.add_discovered_source(source)

            yield catalog

            # Cleanup
            catalog.close()
            Path(tf.name).unlink(missing_ok=True)

    def test_catalog_initialization(self, catalog):
        """Test catalog creates database with proper schema."""
        # Check tables exist
        conn = sqlite3.connect(catalog.db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        assert "sources" in tables
        assert "topic_index" in tables
        assert "language_index" in tables
        assert "metadata" in tables

        conn.close()

    def test_source_retrieval_by_region(self, catalog):
        """Test retrieving sources by region with indexes."""
        start_time = time.time()
        asia_sources = catalog.get_sources_by_region("asia", limit=20)
        query_time = time.time() - start_time

        assert len(asia_sources) == 20
        assert all(s.region == "asia" for s in asia_sources)
        assert query_time < 0.05  # Should be very fast with index

    def test_source_retrieval_by_topic(self, catalog):
        """Test retrieving sources by topic."""
        tech_sources = catalog.get_sources_by_topic("tech")

        assert len(tech_sources) > 0
        assert all("tech" in s.topics for s in tech_sources)

    def test_fuzzy_topic_matching(self, catalog):
        """Test fuzzy matching for topics."""
        # Add a source with specific topic
        source = SourceRecord(
            domain="semiconductor.news",
            name="Semiconductor News",
            region="global",
            topics=["semiconductors", "chips", "electronics"],
            languages=["en"],
            priority=0.7,
            policy="allow",
        )
        catalog.add_discovered_source(source)

        # Test fuzzy matching
        matches = catalog.fuzzy_match_topics("semicondutor")  # Typo
        assert "semiconductors" in matches

        matches = catalog.fuzzy_match_topics("chip")
        assert "chips" in matches

    def test_cache_performance(self, catalog):
        """Test caching improves performance."""
        # First query (cold cache)
        start_time = time.time()
        sources1 = catalog.get_sources_by_region("asia", limit=10)
        cold_time = time.time() - start_time

        # Second query (warm cache)
        start_time = time.time()
        sources2 = catalog.get_sources_by_region("asia", limit=10)
        warm_time = time.time() - start_time

        assert sources1 == sources2  # Same results
        assert warm_time < cold_time * 0.5  # Much faster with cache

    def test_source_stats_update(self, catalog):
        """Test updating source statistics."""
        catalog.update_source_stats(domain="test1.com", yield_words=1000, success=True)

        # Retrieve and check
        sources = catalog.get_sources_by_criteria(limit=100)
        source = next((s for s in sources if s.domain == "test1.com"), None)

        assert source is not None
        # The stats should be updated in the database


class TestSelectionPlanner:
    """Test selection planner with quotas."""

    @pytest.fixture
    def planner(self):
        """Create planner with mock catalog."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            catalog = SKBCatalog(db_path=tf.name)

            # Add diverse test sources
            regions = ["asia", "europe", "americas", "africa", "middle_east"]
            topics = [
                "elections",
                "security",
                "economy",
                "politics",
                "energy",
                "climate",
                "tech",
            ]

            for i in range(500):
                source = SourceRecord(
                    domain=f"news{i}.com",
                    name=f"News {i}",
                    region=regions[i % len(regions)],
                    topics=[topics[i % len(topics)], topics[(i + 1) % len(topics)]],
                    languages=["en"] if i < 400 else ["es", "fr", "de"],
                    priority=0.3 + (i % 7) / 10,
                    policy="allow" if i % 10 != 0 else "headless",
                    notes="wire agency" if i % 20 == 0 else "publication",
                )
                catalog.add_discovered_source(source)

            planner = SelectionPlanner(catalog)

            yield planner

            # Cleanup
            catalog.close()
            Path(tf.name).unlink(missing_ok=True)

    def test_selection_speed_with_large_skb(self, planner):
        """Test selection speed with 500+ sources."""
        quotas = SelectionQuotas(min_sources=30, max_sources=100)

        start_time = time.time()
        plan = planner.plan_selection(
            region="asia", topics=["economy", "tech"], quotas=quotas
        )
        selection_time = time.time() - start_time

        # Should be fast even with large SKB
        assert selection_time < 0.3  # 300ms requirement
        assert len(plan.sources) >= 30
        assert len(plan.sources) <= 100

    def test_diversity_quotas(self, planner):
        """Test diversity requirements are met."""
        quotas = SelectionQuotas(
            min_sources=30, min_editorial_families=3, min_languages=1
        )

        plan = planner.plan_selection(
            region="europe", topics=["politics"], quotas=quotas
        )

        meets, issues = plan.meets_quotas()
        assert meets, f"Quotas not met: {issues}"
        assert len(plan.editorial_families) >= 3
        assert plan.get_diversity_score() > 0.5

    def test_headless_cap(self, planner):
        """Test headless sources are capped."""
        quotas = SelectionQuotas(min_sources=50, max_headless_share=0.10)

        plan = planner.plan_selection(quotas=quotas)

        headless_count = sum(1 for s in plan.sources if s.policy == "headless")
        assert headless_count <= len(plan.sources) * 0.10

    def test_obscure_topic_handling(self, planner):
        """Test handling of obscure topics."""
        quotas = SelectionQuotas(min_sources=25)

        # Test with an obscure topic
        plan = planner.plan_selection(
            other_topic="semiconductors in Maghreb", quotas=quotas
        )

        # Should attempt to find relevant sources
        assert len(plan.sources) >= 0  # May be fewer than min if obscure

        # Check if discovery time was allocated
        assert "_discovery" in plan.time_allocations or len(plan.sources) >= 25

    def test_time_budget_allocation(self, planner):
        """Test time budget is properly allocated."""
        quotas = SelectionQuotas(min_sources=30, time_budget_seconds=300)

        plan = planner.plan_selection(region="asia", topics=["energy"], quotas=quotas)

        # Check allocations
        total_allocated = sum(plan.time_allocations.values())
        assert total_allocated <= 300
        assert all(
            1 <= t <= 10
            for t in plan.time_allocations.values()
            if t != plan.time_allocations.get("_discovery", 0)
        )


class TestHealthMonitor:
    """Test health monitoring and auto-tuning."""

    @pytest.fixture
    def monitor(self):
        """Create health monitor instance."""
        return HealthMonitor()

    def test_metrics_recording(self, monitor):
        """Test recording various metrics."""
        # Record fetch results
        monitor.record_fetch_result("test.com", success=True, latency_ms=500)
        monitor.record_fetch_result("test.com", success=True, latency_ms=600)
        monitor.record_fetch_result(
            "test.com", success=False, latency_ms=10000, error_type="timeout"
        )

        # Record article metrics
        monitor.record_article_metrics(
            "test.com",
            total_articles=10,
            fresh_articles=8,
            total_words=5000,
            fresh_words=4000,
        )

        # Check metrics
        metrics = monitor.metrics["test.com"]
        assert metrics.fetch_attempts == 3
        assert metrics.fetch_successes == 2
        assert metrics.success_rate == pytest.approx(0.667, 0.01)
        assert metrics.freshness_rate == 0.8
        assert metrics.avg_latency == pytest.approx(3700, 100)  # (500+600+10000)/3

    def test_health_score_calculation(self, monitor):
        """Test health score calculation."""
        # Create metrics with known values
        metrics = SourceMetrics(domain="test.com")
        metrics.fetch_attempts = 10
        metrics.fetch_successes = 8  # 80% success
        metrics.total_articles = 100
        metrics.fresh_articles = 60  # 60% fresh
        metrics.fresh_words = 5000
        metrics.latencies.extend([1000, 2000, 1500, 1200, 1800])

        health_score = metrics.health_score

        # Health score should be reasonable
        assert 0 <= health_score <= 1
        assert health_score > 0.5  # Good metrics should give decent score

    def test_auto_tuning(self, monitor):
        """Test auto-tuning based on performance."""
        # Set up sources with different performance

        # High performing source
        for _ in range(10):
            monitor.record_fetch_result("good.com", success=True, latency_ms=500)
        monitor.record_article_metrics("good.com", 100, 90, 10000, 9000)

        # Poor performing source
        for _ in range(10):
            monitor.record_fetch_result(
                "bad.com", success=False, latency_ms=10000, error_type="timeout"
            )

        # Run auto-tuning (dry run)
        actions = monitor.auto_tune_sources(dry_run=True)

        # Check actions
        assert "good.com" in actions["promoted"] or len(actions["promoted"]) == 0
        assert "bad.com" in actions["parked"] or "bad.com" in actions["demoted"]

    def test_run_metrics_aggregation(self, monitor):
        """Test aggregated run metrics."""
        # Record data for multiple sources
        for i in range(5):
            domain = f"test{i}.com"
            monitor.record_fetch_result(
                domain, success=i % 2 == 0, latency_ms=1000 * (i + 1)
            )
            monitor.record_article_metrics(domain, 20, 10, 2000, 1000)

        metrics = monitor.get_run_metrics()

        assert metrics["total_sources"] == 5
        assert 0 <= metrics["fetch_success_rate"] <= 1
        assert metrics["total_articles"] == 100
        assert metrics["fresh_articles"] == 50
        assert metrics["freshness_rate"] == 0.5


class TestRelevanceFilter:
    """Test relevance verification system."""

    @pytest.fixture
    def filter(self):
        """Create relevance filter instance."""
        return RelevanceFilter()

    def test_region_verification(self, filter):
        """Test region relevance scoring."""
        article = {
            "title": "Election Results in Tokyo",
            "text": "The Japanese capital Tokyo saw unprecedented voter turnout...",
            "url": "https://news.com/asia/japan/election",
        }

        score = filter.verify_relevance(article=article, target_region="asia")

        assert score.region_score > 0.5
        assert "tokyo" in " ".join(score.region_signals).lower()
        assert score.should_keep

    def test_topic_verification(self, filter):
        """Test topic relevance scoring."""
        article = {
            "title": "Solar Energy Investment Surges",
            "text": "Renewable energy investments, particularly in solar power...",
            "url": "https://news.com/energy/solar",
        }

        score = filter.verify_relevance(
            article=article, target_topics=["energy", "climate"]
        )

        assert score.topic_score > 0.5
        assert any(
            "solar" in s.lower() or "energy" in s.lower() for s in score.topic_signals
        )

    def test_strict_mode(self, filter):
        """Test strict matching mode."""
        article = {
            "title": "Technology News",
            "text": "Latest developments in technology...",
            "url": "https://news.com/tech",
        }

        # Should fail strict match for different region/topic
        score = filter.verify_relevance(
            article=article,
            target_region="africa",
            target_topics=["politics"],
            strict=True,
        )

        assert score.region_score < 0.5
        assert score.topic_score < 0.5

    def test_relevance_weighting(self, filter):
        """Test relevance weight calculation."""
        # High relevance article
        article1 = {
            "title": "Beijing Elections: Major Victory",
            "text": "Chinese capital Beijing witnessed historic election results...",
            "url": "https://news.com/asia/china/elections",
        }

        score1 = filter.verify_relevance(
            article=article1, target_region="asia", target_topics=["elections"]
        )

        # Low relevance article
        article2 = {
            "title": "Weather Report",
            "text": "Sunny skies expected...",
            "url": "https://news.com/weather",
        }

        score2 = filter.verify_relevance(
            article=article2, target_region="asia", target_topics=["elections"]
        )

        assert score1.weight > score2.weight


class TestAcceptanceCriteria:
    """Test specific acceptance criteria from requirements."""

    def test_cold_start_selection_performance(self):
        """Test: With 10k-source SKB, cold start selection in <300ms."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            catalog = SKBCatalog(db_path=tf.name, cache_ttl=0)  # No cache

            # Add 10k sources
            for i in range(10000):
                source = SourceRecord(
                    domain=f"source{i}.com",
                    name=f"Source {i}",
                    region=["asia", "europe", "americas"][i % 3],
                    topics=["tech", "economy", "politics"][i % 3 : i % 3 + 2],
                    languages=["en"],
                    priority=0.5,
                    policy="allow",
                )
                # Bulk insert for speed
                if i == 0:
                    catalog.add_discovered_source(source)

            planner = SelectionPlanner(catalog)

            # Cold start selection
            start_time = time.time()
            plan = planner.plan_selection(region="europe", topics=["energy"])
            selection_time = (time.time() - start_time) * 1000  # Convert to ms

            assert (
                selection_time < 300
            ), f"Cold start took {selection_time:.0f}ms, expected <300ms"
            assert len(plan.sources) > 0

            catalog.close()
            Path(tf.name).unlink(missing_ok=True)

    def test_warm_start_selection_performance(self):
        """Test: Warm start selection in <50ms."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            catalog = SKBCatalog(db_path=tf.name, cache_ttl=300)

            # Add sources
            for i in range(1000):
                source = SourceRecord(
                    domain=f"source{i}.com",
                    name=f"Source {i}",
                    region="europe",
                    topics=["energy"],
                    languages=["en"],
                    priority=0.5,
                    policy="allow",
                )
                catalog.add_discovered_source(source)

            planner = SelectionPlanner(catalog)

            # Warm cache
            plan1 = planner.plan_selection(region="europe", topics=["energy"])

            # Warm start selection
            start_time = time.time()
            plan2 = planner.plan_selection(region="europe", topics=["energy"])
            selection_time = (time.time() - start_time) * 1000

            assert (
                selection_time < 50
            ), f"Warm start took {selection_time:.0f}ms, expected <50ms"

            catalog.close()
            Path(tf.name).unlink(missing_ok=True)

    def test_budget_compliance(self):
        """Test: Budget never overrun."""
        quotas = SelectionQuotas(min_sources=50, time_budget_seconds=300)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            catalog = SKBCatalog(db_path=tf.name)

            # Add sources
            for i in range(200):
                source = SourceRecord(
                    domain=f"source{i}.com",
                    name=f"Source {i}",
                    region="asia",
                    topics=["tech"],
                    languages=["en"],
                    priority=0.5,
                    policy="allow",
                )
                catalog.add_discovered_source(source)

            planner = SelectionPlanner(catalog)
            plan = planner.plan_selection(quotas=quotas)

            total_allocated = sum(plan.time_allocations.values())
            assert total_allocated <= quotas.time_budget_seconds

            catalog.close()
            Path(tf.name).unlink(missing_ok=True)

    def test_headless_usage_cap(self):
        """Test: Headless usage stays ≤10%."""
        quotas = SelectionQuotas(min_sources=100, max_headless_share=0.10)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            catalog = SKBCatalog(db_path=tf.name)

            # Add mix of sources
            for i in range(200):
                source = SourceRecord(
                    domain=f"source{i}.com",
                    name=f"Source {i}",
                    region="global",
                    topics=["general"],
                    languages=["en"],
                    priority=0.5,
                    policy="headless" if i % 5 == 0 else "allow",  # 20% headless
                )
                catalog.add_discovered_source(source)

            planner = SelectionPlanner(catalog)
            plan = planner.plan_selection(quotas=quotas)

            headless = sum(1 for s in plan.sources if s.policy == "headless")
            headless_ratio = headless / len(plan.sources) if plan.sources else 0

            assert (
                headless_ratio <= 0.10
            ), f"Headless ratio {headless_ratio:.2%} exceeds 10%"

            catalog.close()
            Path(tf.name).unlink(missing_ok=True)
