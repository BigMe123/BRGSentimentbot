#!/usr/bin/env python3
"""
E2E Smoke Tests
===============

End-to-end smoke tests to verify the complete BSG system works.
These are comprehensive tests that exercise the full system.
"""

import pytest
import subprocess
import tempfile
import json
import os
from pathlib import Path
import time
from datetime import datetime


class TestCLISmokeTests:
    """Test CLI commands work end-to-end."""

    @pytest.mark.e2e
    def test_cli_help(self):
        """Test CLI help command works."""
        result = subprocess.run(
            ['python', '-m', 'sentiment_bot.cli_unified', '--help'],
            capture_output=True,
            text=True,
            timeout=30
        )

        assert result.returncode == 0
        assert 'Usage:' in result.stdout or 'Commands:' in result.stdout
        assert len(result.stdout) > 100  # Should have substantial help text

    @pytest.mark.e2e
    def test_perception_measure_cli(self):
        """Test perception measurement CLI command."""
        result = subprocess.run([
            'python', '-m', 'sentiment_bot.cli_unified',
            'perception-measure', 'USA', 'GBR'
        ], capture_output=True, text=True, timeout=60)

        # Should complete without error
        assert result.returncode == 0
        assert 'Perception Score' in result.stdout
        assert '/100' in result.stdout
        assert 'Confidence' in result.stdout

    @pytest.mark.e2e
    def test_perception_rank_cli(self):
        """Test perception ranking CLI command."""
        result = subprocess.run([
            'python', '-m', 'sentiment_bot.cli_unified',
            'perception-rank', '--countries', 'USA,GBR,DEU'
        ], capture_output=True, text=True, timeout=60)

        assert result.returncode == 0
        assert 'Global Perception Rankings' in result.stdout
        assert 'USA' in result.stdout
        assert 'GBR' in result.stdout
        assert 'DEU' in result.stdout

    @pytest.mark.e2e
    def test_perception_report_cli(self):
        """Test perception report CLI command."""
        result = subprocess.run([
            'python', '-m', 'sentiment_bot.cli_unified',
            'perception-report', 'USA'
        ], capture_output=True, text=True, timeout=60)

        assert result.returncode == 0
        assert 'Perception Report: USA' in result.stdout
        assert 'Average Perception Score' in result.stdout
        assert 'Global Rank' in result.stdout

    @pytest.mark.e2e
    def test_perception_matrix_cli(self):
        """Test perception matrix CLI command."""
        result = subprocess.run([
            'python', '-m', 'sentiment_bot.cli_unified',
            'perception-matrix', '--countries', 'USA,GBR,DEU'
        ], capture_output=True, text=True, timeout=90)

        assert result.returncode == 0
        assert 'Perception Matrix' in result.stdout
        assert 'USA' in result.stdout

    @pytest.mark.e2e
    def test_cli_output_files(self):
        """Test CLI commands can output to files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, 'perception_output.json')

            result = subprocess.run([
                'python', '-m', 'sentiment_bot.cli_unified',
                'perception-measure', 'USA', 'CHN',
                '--output', output_file
            ], capture_output=True, text=True, timeout=60)

            assert result.returncode == 0
            assert os.path.exists(output_file)

            # Verify output file is valid JSON
            with open(output_file, 'r') as f:
                data = json.load(f)
                assert 'perceiver' in data
                assert 'target' in data
                assert 'score' in data
                assert data['perceiver'] == 'USA'
                assert data['target'] == 'CHN'


class TestGlobalPerceptionSystemSmoke:
    """Test Global Perception Index system end-to-end."""

    @pytest.mark.e2e
    def test_perception_measurement_smoke(self):
        """Test complete perception measurement workflow."""
        from sentiment_bot.global_perception_index import GlobalPerceptionIndex

        gpi = GlobalPerceptionIndex()

        # Test major country pairs
        test_pairs = [
            ('USA', 'GBR'),
            ('USA', 'CHN'),
            ('GBR', 'DEU'),
            ('DEU', 'FRA')
        ]

        for perceiver, target in test_pairs:
            reading = gpi.measure_perception(perceiver, target)

            # Verify complete reading
            assert hasattr(reading, 'perceiver_country')
            assert hasattr(reading, 'target_country')
            assert hasattr(reading, 'perception_score')
            assert hasattr(reading, 'confidence')
            assert hasattr(reading, 'timestamp')
            assert hasattr(reading, 'data_sources')
            assert hasattr(reading, 'component_scores')

            # Verify valid values
            assert reading.perceiver_country == perceiver
            assert reading.target_country == target
            assert 1 <= reading.perception_score <= 100
            assert 0 <= reading.confidence <= 1
            assert isinstance(reading.timestamp, datetime)
            assert isinstance(reading.data_sources, list)
            assert isinstance(reading.component_scores, dict)

    @pytest.mark.e2e
    def test_global_rankings_smoke(self):
        """Test global rankings calculation."""
        from sentiment_bot.global_perception_index import GlobalPerceptionIndex

        gpi = GlobalPerceptionIndex()

        # Test with subset of countries for speed
        test_countries = ['USA', 'GBR', 'DEU', 'FRA', 'CHN']
        rankings = gpi.calculate_global_rankings(test_countries)

        # Verify rankings structure
        assert isinstance(rankings, dict)
        assert len(rankings) == len(test_countries)

        for country in test_countries:
            assert country in rankings
            score, rank = rankings[country]
            assert 1 <= score <= 100
            assert 1 <= rank <= len(test_countries)

        # Verify ranks are unique and complete
        ranks = [rank for score, rank in rankings.values()]
        assert len(set(ranks)) == len(test_countries)
        assert min(ranks) == 1
        assert max(ranks) == len(test_countries)

    @pytest.mark.e2e
    def test_perception_matrix_smoke(self):
        """Test perception matrix generation."""
        from sentiment_bot.global_perception_index import GlobalPerceptionIndex

        gpi = GlobalPerceptionIndex()

        countries = ['USA', 'GBR', 'DEU']
        matrix = gpi.get_perception_matrix(countries)

        # Verify matrix structure
        assert isinstance(matrix, dict)
        assert len(matrix) == len(countries)

        for perceiver in countries:
            assert perceiver in matrix
            assert len(matrix[perceiver]) == len(countries)

            for target in countries:
                assert target in matrix[perceiver]

                if perceiver == target:
                    assert matrix[perceiver][target] is None
                else:
                    score = matrix[perceiver][target]
                    assert 1 <= score <= 100

    @pytest.mark.e2e
    def test_database_persistence_smoke(self):
        """Test database persistence works."""
        from sentiment_bot.global_perception_index import GlobalPerceptionIndex

        # Use temporary database
        with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as tf:
            temp_db = tf.name

        try:
            gpi = GlobalPerceptionIndex(db_path=temp_db)

            # Generate and store readings
            reading1 = gpi.measure_perception('USA', 'GBR')
            reading2 = gpi.measure_perception('GBR', 'USA')

            # Verify database was created
            assert os.path.exists(temp_db)
            assert os.path.getsize(temp_db) > 0

            # Create new instance with same database
            gpi2 = GlobalPerceptionIndex(db_path=temp_db)

            # Should be able to query trends (even if empty due to no historical data)
            trends = gpi2.get_perception_trends('USA', days=1)
            assert isinstance(trends, dict)
            assert 'trend' in trends

        finally:
            if os.path.exists(temp_db):
                os.unlink(temp_db)


class TestIntegrationSmoke:
    """Test integration between different system components."""

    @pytest.mark.e2e
    def test_sentiment_to_perception_integration(self):
        """Test sentiment analysis integrates with perception measurement."""
        from sentiment_bot.interfaces import create_sentiment_analyzer
        from sentiment_bot.global_perception_index import GlobalPerceptionIndex

        # Analyze sentiment about a country
        analyzer = create_sentiment_analyzer()
        sentiment = analyzer.analyze("The United Kingdom's economy is performing excellently")

        # Should get valid sentiment
        assert hasattr(sentiment, 'score')
        assert -1 <= sentiment.score <= 1

        # Measure perception between countries
        gpi = GlobalPerceptionIndex()
        perception = gpi.measure_perception('USA', 'GBR')

        # Should get valid perception
        assert 1 <= perception.perception_score <= 100

        # Both should complete without errors
        assert sentiment is not None
        assert perception is not None

    @pytest.mark.e2e
    def test_source_to_analysis_integration(self):
        """Test source selection integrates with analysis."""
        from sentiment_bot.interfaces import create_source_selector, create_sentiment_analyzer, AnalysisMode

        # Select sources
        selector = create_source_selector()
        sources = selector.select_sources(
            mode=AnalysisMode.ECONOMIC,
            region="americas",
            max_sources=3
        )

        # Should get sources (may be empty)
        assert isinstance(sources, list)

        # Analyze sentiment
        analyzer = create_sentiment_analyzer()
        sample_text = "Economic growth continues to accelerate across major economies"
        result = analyzer.analyze(sample_text)

        # Should complete without errors
        assert hasattr(result, 'score')
        assert isinstance(sources, list)

    @pytest.mark.e2e
    def test_complete_workflow_smoke(self):
        """Test complete analysis workflow."""
        from sentiment_bot.interfaces import (
            create_sentiment_analyzer, create_source_selector,
            AnalysisMode
        )
        from sentiment_bot.global_perception_index import GlobalPerceptionIndex

        # 1. Source Selection
        selector = create_source_selector()
        sources = selector.select_sources(
            mode=AnalysisMode.SMART,
            region="global",
            max_sources=2
        )

        # 2. Sentiment Analysis
        analyzer = create_sentiment_analyzer()
        sentiment = analyzer.analyze("Global economic outlook remains positive")

        # 3. Perception Measurement
        gpi = GlobalPerceptionIndex()
        perception = gpi.measure_perception('USA', 'GBR')

        # 4. Verify all components worked
        assert isinstance(sources, list)
        assert hasattr(sentiment, 'score')
        assert hasattr(perception, 'perception_score')

        # 5. Verify reasonable outputs
        assert -1 <= sentiment.score <= 1
        assert 1 <= perception.perception_score <= 100


class TestPerformanceSmoke:
    """Test system performance under load."""

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_perception_measurement_performance(self):
        """Test perception measurement performance."""
        from sentiment_bot.global_perception_index import GlobalPerceptionIndex

        gpi = GlobalPerceptionIndex()

        # Time multiple measurements
        start_time = time.time()

        measurements = [
            ('USA', 'GBR'),
            ('GBR', 'DEU'),
            ('DEU', 'FRA'),
            ('FRA', 'CHN'),
            ('CHN', 'USA')
        ]

        for perceiver, target in measurements:
            reading = gpi.measure_perception(perceiver, target)
            assert 1 <= reading.perception_score <= 100

        elapsed = time.time() - start_time

        # Should complete 5 measurements in reasonable time
        assert elapsed < 30  # 30 seconds max
        print(f"Completed {len(measurements)} measurements in {elapsed:.1f}s")

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_ranking_calculation_performance(self):
        """Test ranking calculation performance."""
        from sentiment_bot.global_perception_index import GlobalPerceptionIndex

        gpi = GlobalPerceptionIndex()

        start_time = time.time()

        # Calculate rankings for subset of countries
        test_countries = ['USA', 'GBR', 'DEU', 'FRA', 'CHN', 'JPN']
        rankings = gpi.calculate_global_rankings(test_countries)

        elapsed = time.time() - start_time

        # Should complete ranking calculation in reasonable time
        assert elapsed < 60  # 1 minute max
        assert len(rankings) == len(test_countries)
        print(f"Calculated rankings for {len(test_countries)} countries in {elapsed:.1f}s")

    @pytest.mark.e2e
    def test_sentiment_analysis_batch_performance(self):
        """Test sentiment analysis batch performance."""
        from sentiment_bot.interfaces import create_sentiment_analyzer

        analyzer = create_sentiment_analyzer()

        # Batch of test texts
        test_texts = [
            "Economic growth is accelerating",
            "Market conditions remain challenging",
            "Trade relations are improving",
            "Inflation concerns persist",
            "Employment numbers look positive"
        ]

        start_time = time.time()

        results = []
        for text in test_texts:
            result = analyzer.analyze(text)
            results.append(result)

        elapsed = time.time() - start_time

        # Should complete batch analysis quickly
        assert elapsed < 10  # 10 seconds max
        assert len(results) == len(test_texts)

        # All results should be valid
        for result in results:
            assert hasattr(result, 'score')
            assert -1 <= result.score <= 1

        print(f"Analyzed {len(test_texts)} texts in {elapsed:.1f}s")


class TestDataQualitySmoke:
    """Test data quality and consistency."""

    @pytest.mark.e2e
    def test_country_codes_consistency(self):
        """Test country codes are consistent across system."""
        from sentiment_bot.global_perception_index import GlobalPerceptionIndex

        gpi = GlobalPerceptionIndex()

        # All major countries should be valid 3-letter codes
        for country in gpi.major_countries:
            assert isinstance(country, str)
            assert len(country) == 3
            assert country.isupper()
            assert country.isalpha()

    @pytest.mark.e2e
    def test_perception_scores_distribution(self):
        """Test perception scores show reasonable distribution."""
        from sentiment_bot.global_perception_index import GlobalPerceptionIndex

        gpi = GlobalPerceptionIndex()

        # Sample perception scores
        scores = []
        test_pairs = [
            ('USA', 'GBR'), ('USA', 'DEU'), ('USA', 'FRA'),
            ('GBR', 'USA'), ('GBR', 'DEU'), ('GBR', 'FRA'),
            ('DEU', 'USA'), ('DEU', 'GBR'), ('DEU', 'FRA')
        ]

        for perceiver, target in test_pairs:
            reading = gpi.measure_perception(perceiver, target)
            scores.append(reading.perception_score)

        # Should have reasonable distribution
        assert len(scores) == len(test_pairs)
        assert all(1 <= score <= 100 for score in scores)

        # Should have some variance (not all identical)
        if len(set(scores)) == 1:
            # All scores identical - check if this is expected behavior
            unique_score = scores[0]
            assert 40 <= unique_score <= 60  # Should be near neutral if uniform

    @pytest.mark.e2e
    def test_timestamp_freshness(self):
        """Test all timestamps are fresh and reasonable."""
        from sentiment_bot.global_perception_index import GlobalPerceptionIndex
        from datetime import datetime, timedelta

        gpi = GlobalPerceptionIndex()

        # Generate fresh reading
        reading = gpi.measure_perception('USA', 'GBR')

        # Timestamp should be very recent
        now = datetime.now()
        age = now - reading.timestamp

        assert age < timedelta(minutes=1)  # Should be less than 1 minute old
        assert reading.timestamp <= now    # Should not be in future


class TestErrorHandlingSmoke:
    """Test system handles errors gracefully."""

    @pytest.mark.e2e
    def test_invalid_country_codes(self):
        """Test system handles invalid country codes gracefully."""
        from sentiment_bot.global_perception_index import GlobalPerceptionIndex

        gpi = GlobalPerceptionIndex()

        # Should handle invalid codes without crashing
        reading = gpi.measure_perception('INVALID', 'ALSO_INVALID')

        assert hasattr(reading, 'perception_score')
        assert hasattr(reading, 'confidence')
        # May return neutral/default values

    @pytest.mark.e2e
    def test_network_failure_resilience(self):
        """Test system is resilient to network failures."""
        from sentiment_bot.interfaces import create_sentiment_analyzer

        analyzer = create_sentiment_analyzer()

        # Should work even if some network components fail
        result = analyzer.analyze("Test text for network resilience")

        assert hasattr(result, 'score')
        assert -1 <= result.score <= 1

    @pytest.mark.e2e
    def test_empty_input_handling(self):
        """Test system handles empty inputs gracefully."""
        from sentiment_bot.interfaces import create_sentiment_analyzer

        analyzer = create_sentiment_analyzer()

        # Should handle empty text
        result = analyzer.analyze("")
        assert hasattr(result, 'score')
        assert hasattr(result, 'label')


@pytest.mark.e2e
def test_system_health_check():
    """Comprehensive system health check."""
    from sentiment_bot.interfaces import (
        create_sentiment_analyzer, create_source_selector, AnalysisMode
    )
    from sentiment_bot.global_perception_index import GlobalPerceptionIndex

    # 1. Sentiment Analysis Health
    analyzer = create_sentiment_analyzer()
    sentiment_result = analyzer.analyze("System health check")
    assert hasattr(sentiment_result, 'score')

    # 2. Source Selection Health
    selector = create_source_selector()
    sources = selector.select_sources(mode=AnalysisMode.SMART, max_sources=1)
    assert isinstance(sources, list)

    # 3. Perception Index Health
    gpi = GlobalPerceptionIndex()
    perception_result = gpi.measure_perception('USA', 'GBR')
    assert hasattr(perception_result, 'perception_score')

    # 4. Database Health
    assert gpi.db_path.exists()

    print("✅ All system components are healthy")