#!/usr/bin/env python3
"""
Unit Tests: Article Freshness Filter
====================================

Test freshness parameter ranges and default configurations.
Addresses requirement: "Remove article freshness filter (make selectable 24h → forever)"
"""

import pytest
from datetime import datetime, timedelta
from sentiment_bot.cli_unified import _filter_by_freshness
from sentiment_bot.interfaces import Article


class TestFreshnessParamRanges:
    """Test freshness parameter ranges map to correct query windows."""

    @pytest.mark.unit
    def test_freshness_param_values(self):
        """Test that freshness values map to correct time windows."""
        # Test data
        now = datetime.now()
        articles = [
            {"published_at": now - timedelta(hours=12), "title": "Recent"},
            {"published_at": now - timedelta(days=2), "title": "2 days old"},
            {"published_at": now - timedelta(days=10), "title": "10 days old"},
            {"published_at": now - timedelta(days=40), "title": "40 days old"},
            {"published_at": now - timedelta(days=100), "title": "100 days old"},
            {"published_at": now - timedelta(days=400), "title": "400 days old"}
        ]

        # Test 24h filter
        fresh, stale, rate = _filter_by_freshness(articles, max_age_hours=24)
        assert len(fresh) == 1  # Only "Recent"
        assert fresh[0]["title"] == "Recent"

        # Test 3 days filter
        fresh, stale, rate = _filter_by_freshness(articles, max_age_hours=72)
        assert len(fresh) == 2  # "Recent" and "2 days old"

        # Test 7 days filter
        fresh, stale, rate = _filter_by_freshness(articles, max_age_hours=168)
        assert len(fresh) == 2  # Still only recent ones

        # Test 30 days filter
        fresh, stale, rate = _filter_by_freshness(articles, max_age_hours=720)
        assert len(fresh) == 3  # Includes "10 days old"

        # Test 90 days filter
        fresh, stale, rate = _filter_by_freshness(articles, max_age_hours=2160)
        assert len(fresh) == 4  # Includes "40 days old"

        # Test 365 days filter
        fresh, stale, rate = _filter_by_freshness(articles, max_age_hours=8760)
        assert len(fresh) == 5  # Includes "100 days old"

        # Test "forever" (0 = no filter)
        fresh, stale, rate = _filter_by_freshness(articles, max_age_hours=0)
        assert len(fresh) == 6  # All articles
        assert rate == 1.0

    @pytest.mark.unit
    def test_freshness_edge_cases(self):
        """Test edge cases for freshness filtering."""
        now = datetime.now()

        # Empty list
        fresh, stale, rate = _filter_by_freshness([], max_age_hours=24)
        assert len(fresh) == 0
        assert rate == 0

        # Articles without published_at
        articles = [{"title": "No date", "published_at": None}]
        fresh, stale, rate = _filter_by_freshness(articles, max_age_hours=24)
        assert len(fresh) == 0  # Conservative: exclude if no date
        assert stale == 1

        # Negative max_age_hours (should behave like 0)
        articles = [{"published_at": now, "title": "Recent"}]
        fresh, stale, rate = _filter_by_freshness(articles, max_age_hours=-1)
        assert len(fresh) == 1  # No filter applied
        assert rate == 1.0

    @pytest.mark.unit
    def test_freshness_rate_calculation(self):
        """Test freshness rate calculation."""
        now = datetime.now()
        articles = [
            {"published_at": now - timedelta(hours=1), "title": "Fresh 1"},
            {"published_at": now - timedelta(hours=2), "title": "Fresh 2"},
            {"published_at": now - timedelta(days=2), "title": "Stale 1"},
            {"published_at": now - timedelta(days=3), "title": "Stale 2"}
        ]

        fresh, stale, rate = _filter_by_freshness(articles, max_age_hours=24)
        assert len(fresh) == 2
        assert stale == 2
        assert rate == 0.5  # 2 fresh out of 4 total


class TestDefaultFreshnessPerMode:
    """Test that default freshness is not hardcoded to 24h."""

    @pytest.mark.unit
    def test_no_hardcoded_defaults(self):
        """Test that CLI accepts different default values."""
        # This would need to test the CLI argument parsing
        # For now, verify the function doesn't force 24h
        articles = [{"published_at": datetime.now(), "title": "Test"}]

        # max_age_hours=0 should mean no filtering
        fresh, stale, rate = _filter_by_freshness(articles, max_age_hours=0)
        assert len(fresh) == 1
        assert rate == 1.0

        # Should not default to 24h if not specified
        fresh_default, stale_default, rate_default = _filter_by_freshness(articles)
        assert rate_default == 1.0  # Default should be no filter


class TestFreshnessAffectsResults:
    """Integration test: freshness affects result sets."""

    @pytest.mark.integration
    def test_freshness_changes_results(self):
        """Test that changing freshness window changes results."""
        now = datetime.now()
        articles = [
            {"published_at": now - timedelta(hours=1), "title": "Very recent"},
            {"published_at": now - timedelta(hours=25), "title": "Day old"},
            {"published_at": now - timedelta(days=8), "title": "Week old"}
        ]

        # 1 hour window
        fresh_1h, _, rate_1h = _filter_by_freshness(articles, max_age_hours=1)

        # 24 hour window
        fresh_24h, _, rate_24h = _filter_by_freshness(articles, max_age_hours=24)

        # 1 week window
        fresh_1w, _, rate_1w = _filter_by_freshness(articles, max_age_hours=168)

        # Results should be different
        assert len(fresh_1h) < len(fresh_24h) < len(fresh_1w)
        assert rate_1h < rate_24h < rate_1w

        # Specific expectations
        assert len(fresh_1h) == 1  # Only "Very recent"
        assert len(fresh_24h) == 1  # Still only "Very recent" (25h > 24h)
        assert len(fresh_1w) == 2   # "Very recent" + "Day old"

    @pytest.mark.unit
    def test_freshness_config_persistence(self):
        """Test that freshness config can be saved/loaded."""
        # This would test that CLI config persists the freshness setting
        # For now, just verify the parameter works as expected

        test_values = [0, 24, 72, 168, 720, 8760]  # forever, 1d, 3d, 1w, 1m, 1y

        articles = [{"published_at": datetime.now() - timedelta(days=i), "title": f"Article {i}"}
                   for i in range(10)]

        results = {}
        for hours in test_values:
            fresh, stale, rate = _filter_by_freshness(articles, max_age_hours=hours)
            results[hours] = len(fresh)

        # Verify monotonic increase (more hours = more articles)
        prev_count = 0
        for hours in sorted(test_values):
            if hours == 0:  # Special case: forever
                assert results[hours] == len(articles)
            else:
                assert results[hours] >= prev_count
                prev_count = results[hours]


# Property-based tests
@pytest.mark.property
class TestFreshnessProperties:
    """Property-based tests for freshness filtering."""

    def test_freshness_monotonicity(self):
        """Property: Increasing time window never decreases result count."""
        from hypothesis import given, strategies as st

        # This would use hypothesis for property testing
        # For now, a simple version:
        now = datetime.now()
        articles = [{"published_at": now - timedelta(hours=i), "title": f"Article {i}"}
                   for i in range(100)]

        time_windows = [24, 48, 72, 168, 720]
        results = []

        for hours in time_windows:
            fresh, _, _ = _filter_by_freshness(articles, max_age_hours=hours)
            results.append(len(fresh))

        # Should be monotonically non-decreasing
        for i in range(1, len(results)):
            assert results[i] >= results[i-1], f"Result count decreased: {results}"

    def test_freshness_boundary_conditions(self):
        """Property: Articles exactly at boundary are handled consistently."""
        now = datetime.now()
        boundary_time = now - timedelta(hours=24)

        articles = [
            {"published_at": boundary_time - timedelta(seconds=1), "title": "Just outside"},
            {"published_at": boundary_time, "title": "Exactly at boundary"},
            {"published_at": boundary_time + timedelta(seconds=1), "title": "Just inside"}
        ]

        fresh, stale, rate = _filter_by_freshness(articles, max_age_hours=24)

        # Should include articles at or after the boundary
        assert len(fresh) >= 2  # "Exactly at boundary" and "Just inside"
        fresh_titles = [a["title"] for a in fresh]
        assert "Just inside" in fresh_titles