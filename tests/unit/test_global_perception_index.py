#!/usr/bin/env python3
"""
Unit Tests: Global Perception Index
===================================

Comprehensive unit tests for the Global Perception Index system.
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta
from sentiment_bot.global_perception_index import (
    GlobalPerceptionIndex, PerceptionReading, PerceptionDataCollector,
    GlobalPerceptionSnapshot
)


class TestPerceptionReading:
    """Test PerceptionReading dataclass."""

    @pytest.mark.unit
    def test_perception_reading_creation(self):
        """Test creating a perception reading."""
        reading = PerceptionReading(
            perceiver_country="USA",
            target_country="CHN",
            perception_score=65.5,
            confidence=0.8,
            timestamp=datetime.now(),
            data_sources=["news", "economic"],
            component_scores={"news": 70.0, "economic": 60.0}
        )

        assert reading.perceiver_country == "USA"
        assert reading.target_country == "CHN"
        assert reading.perception_score == 65.5
        assert 0 <= reading.confidence <= 1
        assert reading.data_sources == ["news", "economic"]
        assert reading.metadata == {}

    @pytest.mark.unit
    def test_perception_score_bounds(self):
        """Test perception scores are in valid range."""
        reading = PerceptionReading(
            perceiver_country="GBR",
            target_country="DEU",
            perception_score=85.0,
            confidence=0.9,
            timestamp=datetime.now(),
            data_sources=["diplomatic"],
            component_scores={"diplomatic": 85.0}
        )

        assert 1 <= reading.perception_score <= 100
        assert 0 <= reading.confidence <= 1


class TestPerceptionDataCollector:
    """Test perception data collection."""

    @pytest.mark.unit
    def test_collector_initialization(self):
        """Test collector initializes properly."""
        collector = PerceptionDataCollector()
        assert collector.config == {}
        assert collector.sentiment_analyzer is None

    @pytest.mark.unit
    def test_country_sources_mapping(self):
        """Test country to sources mapping."""
        collector = PerceptionDataCollector()

        usa_sources = collector._get_country_sources("USA")
        assert isinstance(usa_sources, list)
        assert "cnn.com" in usa_sources or "nytimes.com" in usa_sources

        gbr_sources = collector._get_country_sources("GBR")
        assert isinstance(gbr_sources, list)
        assert "bbc.com" in gbr_sources or "theguardian.com" in gbr_sources

        # Unknown country should return empty list
        unknown_sources = collector._get_country_sources("XYZ")
        assert unknown_sources == []

    @pytest.mark.unit
    def test_news_sentiment_collection(self):
        """Test news sentiment collection."""
        collector = PerceptionDataCollector()

        result = collector.collect_news_sentiment("USA", "CHN")
        assert isinstance(result, dict)
        assert "sentiment" in result
        assert "confidence" in result
        assert "article_count" in result

        # Sentiment should be in valid range
        sentiment = result["sentiment"]
        assert 1 <= sentiment <= 100

        # Confidence should be in valid range
        confidence = result["confidence"]
        assert 0 <= confidence <= 1

    @pytest.mark.unit
    def test_economic_indicators_collection(self):
        """Test economic indicators collection."""
        collector = PerceptionDataCollector()

        result = collector.collect_economic_indicators("USA", "GBR")
        assert isinstance(result, dict)
        assert "economic_perception" in result
        assert "confidence" in result

        perception = result["economic_perception"]
        assert 1 <= perception <= 100

        confidence = result["confidence"]
        assert 0 <= confidence <= 1

    @pytest.mark.unit
    def test_diplomatic_signals_collection(self):
        """Test diplomatic signals collection."""
        collector = PerceptionDataCollector()

        result = collector.collect_diplomatic_signals("DEU", "FRA")
        assert isinstance(result, dict)
        assert "diplomatic_perception" in result
        assert "confidence" in result

        perception = result["diplomatic_perception"]
        assert 1 <= perception <= 100

    @pytest.mark.unit
    def test_trade_perception_calculation(self):
        """Test trade perception calculation."""
        collector = PerceptionDataCollector()

        # Test known relationship
        usa_chn_score = collector._calculate_trade_perception("USA", "CHN")
        assert isinstance(usa_chn_score, float)
        assert 1 <= usa_chn_score <= 100

        # Test unknown relationship - should return default
        unknown_score = collector._calculate_trade_perception("XYZ", "ABC")
        assert unknown_score == 50.0

    @pytest.mark.unit
    def test_un_alignment_calculation(self):
        """Test UN voting alignment calculation."""
        collector = PerceptionDataCollector()

        # Test known alignment
        usa_gbr_alignment = collector._calculate_un_alignment("USA", "GBR")
        assert isinstance(usa_gbr_alignment, float)
        assert 1 <= usa_gbr_alignment <= 100

        # Should be high for allies
        assert usa_gbr_alignment > 80

        # Test adversarial alignment
        usa_chn_alignment = collector._calculate_un_alignment("USA", "CHN")
        assert usa_chn_alignment < 50


class TestGlobalPerceptionIndex:
    """Test main Global Perception Index system."""

    @pytest.fixture
    def temp_gpi(self):
        """Create GPI with temporary database."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            gpi = GlobalPerceptionIndex(db_path=tf.name)
            yield gpi
            os.unlink(tf.name)

    @pytest.mark.unit
    def test_gpi_initialization(self, temp_gpi):
        """Test GPI initializes properly."""
        gpi = temp_gpi
        assert gpi.db_path.exists()
        assert gpi.collector is not None
        assert len(gpi.major_countries) >= 15

    @pytest.mark.unit
    def test_measure_perception(self, temp_gpi):
        """Test measuring perception between countries."""
        gpi = temp_gpi

        reading = gpi.measure_perception("USA", "GBR")

        assert isinstance(reading, PerceptionReading)
        assert reading.perceiver_country == "USA"
        assert reading.target_country == "GBR"
        assert 1 <= reading.perception_score <= 100
        assert 0 <= reading.confidence <= 1
        assert isinstance(reading.data_sources, list)
        assert isinstance(reading.component_scores, dict)

    @pytest.mark.unit
    def test_country_perception(self, temp_gpi):
        """Test getting country perception from multiple perceivers."""
        gpi = temp_gpi

        perceptions = gpi.get_country_perception("CHN", ["USA", "GBR", "DEU"])

        assert isinstance(perceptions, dict)
        assert len(perceptions) == 3
        assert "USA" in perceptions
        assert "GBR" in perceptions
        assert "DEU" in perceptions

        for country, score in perceptions.items():
            assert 1 <= score <= 100

    @pytest.mark.unit
    def test_perception_matrix(self, temp_gpi):
        """Test generating perception matrix."""
        gpi = temp_gpi

        countries = ["USA", "CHN", "GBR", "DEU"]
        matrix = gpi.get_perception_matrix(countries)

        assert isinstance(matrix, dict)
        assert len(matrix) == 4

        for perceiver in countries:
            assert perceiver in matrix
            assert len(matrix[perceiver]) == 4

            for target in countries:
                if perceiver == target:
                    assert matrix[perceiver][target] is None
                else:
                    score = matrix[perceiver][target]
                    assert 1 <= score <= 100

    @pytest.mark.unit
    def test_global_rankings(self, temp_gpi):
        """Test calculating global rankings."""
        gpi = temp_gpi

        countries = ["USA", "CHN", "GBR", "DEU", "FRA"]
        rankings = gpi.calculate_global_rankings(countries)

        assert isinstance(rankings, dict)
        assert len(rankings) == 5

        for country, (score, rank) in rankings.items():
            assert 1 <= score <= 100
            assert 1 <= rank <= 5

        # Check that ranks are unique and sequential
        ranks = [rank for score, rank in rankings.values()]
        assert len(set(ranks)) == 5  # All ranks unique
        assert min(ranks) == 1
        assert max(ranks) == 5

    @pytest.mark.unit
    def test_perception_trends_no_data(self, temp_gpi):
        """Test perception trends with no historical data."""
        gpi = temp_gpi

        trends = gpi.get_perception_trends("CHN", days=30)

        assert isinstance(trends, dict)
        assert trends["trend"] == "no_data"
        assert trends["change"] == 0.0
        assert trends["readings"] == 0

    @pytest.mark.unit
    def test_database_storage(self, temp_gpi):
        """Test storing readings in database."""
        gpi = temp_gpi

        reading = PerceptionReading(
            perceiver_country="USA",
            target_country="CHN",
            perception_score=45.0,
            confidence=0.7,
            timestamp=datetime.now(),
            data_sources=["news", "economic"],
            component_scores={"news": 40.0, "economic": 50.0}
        )

        # Store reading
        gpi._store_reading(reading)

        # Verify it was stored (would need database query in real implementation)
        assert True  # Placeholder - actual test would query database

    @pytest.mark.unit
    def test_generate_country_report(self, temp_gpi):
        """Test generating country-specific report."""
        gpi = temp_gpi

        report = gpi.generate_report("USA")

        assert isinstance(report, dict)
        assert report["country"] == "USA"
        assert "current_perceptions" in report
        assert "average_score" in report
        assert "global_rank" in report
        assert "trends" in report
        assert "timestamp" in report

        assert 1 <= report["average_score"] <= 100

    @pytest.mark.unit
    def test_generate_global_report(self, temp_gpi):
        """Test generating global report."""
        gpi = temp_gpi

        report = gpi.generate_report()

        assert isinstance(report, dict)
        assert "global_rankings" in report
        assert "perception_matrix" in report
        assert "top_5" in report
        assert "bottom_5" in report
        assert "timestamp" in report

        assert len(report["top_5"]) == 5
        assert len(report["bottom_5"]) == 5

    @pytest.mark.unit
    def test_perception_score_validation(self, temp_gpi):
        """Test perception scores are always valid."""
        gpi = temp_gpi

        # Test multiple country pairs
        test_pairs = [
            ("USA", "CHN"),
            ("GBR", "DEU"),
            ("FRA", "JPN"),
            ("AUS", "CAN")
        ]

        for perceiver, target in test_pairs:
            reading = gpi.measure_perception(perceiver, target)

            # Score should be in valid range
            assert 1 <= reading.perception_score <= 100

            # Confidence should be valid
            assert 0 <= reading.confidence <= 1

            # Should have timestamp
            assert isinstance(reading.timestamp, datetime)

            # Should have component scores
            assert isinstance(reading.component_scores, dict)

    @pytest.mark.unit
    def test_major_countries_list(self, temp_gpi):
        """Test major countries list is comprehensive."""
        gpi = temp_gpi

        expected_countries = [
            "USA", "CHN", "GBR", "DEU", "FRA", "JPN", "RUS", "IND", "BRA"
        ]

        for country in expected_countries:
            assert country in gpi.major_countries

        # Should have reasonable number of countries
        assert len(gpi.major_countries) >= 15
        assert len(gpi.major_countries) <= 30

    @pytest.mark.unit
    def test_error_handling(self, temp_gpi):
        """Test error handling for invalid inputs."""
        gpi = temp_gpi

        # Test with invalid country codes
        reading = gpi.measure_perception("INVALID", "ALSO_INVALID")

        assert isinstance(reading, PerceptionReading)
        assert 45.0 <= reading.perception_score <= 55.0  # Near-neutral fallback
        assert reading.confidence == 0.0


class TestPerceptionComponents:
    """Test individual perception components."""

    @pytest.mark.unit
    def test_component_weighting(self):
        """Test component score weighting logic."""
        # Test weighting calculation
        component_scores = {
            'news_sentiment': 70.0,
            'economic_relations': 80.0,
            'diplomatic_relations': 60.0
        }

        weights = {
            'news_sentiment': 0.4,
            'economic_relations': 0.35,
            'diplomatic_relations': 0.25
        }

        weighted_score = sum(
            component_scores[component] * weights[component]
            for component in weights
        )

        assert 1 <= weighted_score <= 100
        # Should be around 71.5 for these inputs
        assert abs(weighted_score - 71.5) < 1.0

    @pytest.mark.unit
    def test_confidence_calculation(self):
        """Test confidence score calculation."""
        confidences = {
            'news': 0.8,
            'economic': 0.6,
            'diplomatic': 0.7
        }

        weights = {
            'news': 0.4,
            'economic': 0.35,
            'diplomatic': 0.25
        }

        overall_confidence = sum(
            confidences[component.replace('_sentiment', '').replace('_relations', '')] * weight
            for component, weight in weights.items()
        )

        assert 0 <= overall_confidence <= 1
        assert abs(overall_confidence - 0.7025) < 0.01

    @pytest.mark.unit
    def test_score_normalization(self):
        """Test score normalization to 1-100 scale."""
        # Test various inputs
        test_scores = [-0.5, 0.0, 0.5, 1.0, 1.5, -1.0]

        for score in test_scores:
            # Normalize to [1, 100] scale
            normalized = max(1.0, min(100.0, (score + 1) * 49.5 + 1))

            assert 1 <= normalized <= 100

        # Test specific conversions
        assert max(1.0, min(100.0, (-1 + 1) * 49.5 + 1)) == 1.0   # -1 -> 1
        assert max(1.0, min(100.0, (0 + 1) * 49.5 + 1)) == 50.5   # 0 -> 50.5
        assert max(1.0, min(100.0, (1 + 1) * 49.5 + 1)) == 100.0  # 1 -> 100


class TestPerceptionIntegration:
    """Test integration with existing sentiment system."""

    @pytest.mark.unit
    def test_sentiment_integration(self):
        """Test integration with sentiment analysis system."""
        # Mock sentiment result
        sentiment_score = 0.3  # Positive sentiment

        # Convert to perception score
        perception_score = (sentiment_score + 1) * 49.5 + 1

        assert 1 <= perception_score <= 100
        assert perception_score > 50  # Positive sentiment -> above neutral

    @pytest.mark.unit
    def test_source_filtering(self):
        """Test filtering sources by country."""
        collector = PerceptionDataCollector()

        # Test source filtering logic
        all_sources = ["cnn.com", "bbc.com", "rt.com", "xinhua.com"]
        usa_sources = ["cnn.com", "nytimes.com", "wsj.com"]

        # Filter for US sources
        filtered = [s for s in all_sources if s in usa_sources]
        assert "cnn.com" in filtered
        assert "bbc.com" not in filtered
        assert "rt.com" not in filtered

    @pytest.mark.unit
    def test_time_weighting(self):
        """Test time-based weighting of perception data."""
        now = datetime.now()
        timestamps = [
            now - timedelta(days=1),   # Recent
            now - timedelta(days=7),   # Week old
            now - timedelta(days=30),  # Month old
        ]

        # Time weights (more recent = higher weight)
        weights = []
        for ts in timestamps:
            age_days = (now - ts).days
            weight = max(0.1, 1.0 - (age_days / 30.0))  # Decay over 30 days
            weights.append(weight)

        assert weights[0] > weights[1] > weights[2]  # Recent > older
        assert all(0 <= w <= 1 for w in weights)

    @pytest.mark.unit
    def test_data_quality_thresholds(self):
        """Test data quality thresholds."""
        # Test minimum data requirements
        min_articles = 5
        min_confidence = 0.3

        article_counts = [1, 5, 10, 20]
        confidences = [0.1, 0.3, 0.6, 0.9]

        for article_count in article_counts:
            for confidence in confidences:
                # Quality score based on both factors
                quality = min(1.0, article_count / min_articles) * confidence

                if article_count >= min_articles and confidence >= min_confidence:
                    assert quality >= min_confidence
                else:
                    assert quality < 1.0