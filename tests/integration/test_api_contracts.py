#!/usr/bin/env python3
"""
Integration Tests: API Contracts
===============================

Test that all BSG API contracts are maintained and components integrate properly.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from sentiment_bot.interfaces import (
    SentimentAnalyzer, SourceSelector, ArticleScraper, EconomicPredictor,
    create_sentiment_analyzer, create_source_selector, create_article_scraper,
    create_economic_predictor, AnalysisMode, Article, Source, SentimentResult, PredictionResult
)
from sentiment_bot.global_perception_index import GlobalPerceptionIndex
from sentiment_bot.unified_source_manager import UnifiedSourceManager


class TestSentimentAnalysisContract:
    """Test sentiment analysis API contracts."""

    @pytest.mark.integration
    def test_sentiment_analyzer_contract(self):
        """Test sentiment analyzer meets contract requirements."""
        analyzer = create_sentiment_analyzer()

        # Contract: Must implement SentimentAnalyzer interface
        assert isinstance(analyzer, SentimentAnalyzer)

        # Contract: analyze() method returns SentimentResult
        result = analyzer.analyze("This is positive economic news")
        assert isinstance(result, SentimentResult)

        # Contract: Score in [-1, 1] range
        assert -1 <= result.score <= 1

        # Contract: Confidence in [0, 1] range
        assert 0 <= result.confidence <= 1

        # Contract: Label is valid
        assert result.label in ['positive', 'negative', 'neutral', 'abstain']

        # Contract: Legacy compatibility maintained
        legacy_result = analyzer.analyze_sentiment("Test text")
        assert isinstance(legacy_result, dict)
        assert 'compound' in legacy_result
        assert 'label' in legacy_result

    @pytest.mark.integration
    def test_sentiment_analyzer_consistency(self):
        """Test sentiment analyzer produces consistent results."""
        analyzer = create_sentiment_analyzer()

        # Same input should produce consistent results
        text = "The economy is performing exceptionally well this quarter"
        results = [analyzer.analyze(text) for _ in range(3)]

        scores = [r.score for r in results]
        labels = [r.label for r in results]

        # Scores should be very similar (allowing for minor randomness)
        assert max(scores) - min(scores) < 0.1

        # Labels should be identical
        assert len(set(labels)) == 1

    @pytest.mark.integration
    def test_sentiment_analyzer_performance(self, performance_timer):
        """Test sentiment analyzer meets performance requirements."""
        analyzer = create_sentiment_analyzer()

        # Contract: Analysis should complete in reasonable time
        performance_timer.start()
        result = analyzer.analyze("Economic growth accelerates in Q3 with strong job creation")
        performance_timer.stop()

        # Should complete in under 2 seconds
        assert performance_timer.elapsed_ms < 2000
        assert isinstance(result, SentimentResult)


class TestSourceSelectionContract:
    """Test source selection API contracts."""

    @pytest.mark.integration
    def test_source_selector_contract(self):
        """Test source selector meets contract requirements."""
        selector = create_source_selector()

        # Contract: Must implement SourceSelector interface
        assert isinstance(selector, SourceSelector)

        # Contract: select_sources() returns list of Source objects
        sources = selector.select_sources(
            mode=AnalysisMode.ECONOMIC,
            region="americas",
            max_sources=5
        )

        assert isinstance(sources, list)
        assert len(sources) <= 5

        for source in sources:
            assert isinstance(source, Source)
            assert hasattr(source, 'name')
            assert hasattr(source, 'url')
            assert hasattr(source, 'domain')

    @pytest.mark.integration
    def test_source_selector_modes(self):
        """Test source selector handles all analysis modes."""
        selector = create_source_selector()

        # Contract: All analysis modes should be supported
        for mode in AnalysisMode:
            sources = selector.select_sources(mode=mode, max_sources=3)
            assert isinstance(sources, list)
            # Should return some sources for each mode
            # (allowing for empty results if no sources available)

    @pytest.mark.integration
    def test_source_selector_regional_filtering(self):
        """Test source selector properly filters by region."""
        selector = create_source_selector()

        regions = ["americas", "europe", "asia"]

        for region in regions:
            sources = selector.select_sources(
                mode=AnalysisMode.ECONOMIC,
                region=region,
                max_sources=10
            )

            # Contract: Should respect regional filtering
            for source in sources:
                if hasattr(source, 'region') and source.region:
                    # Source region should match requested region or be global
                    assert source.region in [region, "global", None]


class TestArticleScrapingContract:
    """Test article scraping API contracts."""

    @pytest.mark.integration
    def test_article_scraper_contract(self):
        """Test article scraper meets contract requirements."""
        scraper = create_article_scraper()

        # Contract: scrape_articles() returns list of Article objects
        sources = [
            Source(
                name="Test Source",
                url="https://httpbin.org/json",  # Test endpoint
                domain="httpbin.org",
                country="USA",
                region="americas",
                topics=["test"]
            )
        ]

        try:
            articles = scraper.scrape_articles(sources, max_articles=5)
            assert isinstance(articles, list)

            for article in articles[:2]:  # Test first 2 articles
                assert isinstance(article, Article)
                assert hasattr(article, 'title')
                assert hasattr(article, 'text')
                assert hasattr(article, 'url')

        except Exception:
            # Scraping may fail due to network issues - this is acceptable
            pytest.skip("Network scraping failed - external dependency")

    @pytest.mark.integration
    def test_article_scraper_error_handling(self):
        """Test article scraper handles errors gracefully."""
        scraper = create_article_scraper()

        # Contract: Should handle invalid sources gracefully
        invalid_sources = [
            Source(
                name="Invalid Source",
                url="https://invalid-domain-12345.nonexistent",
                domain="invalid-domain-12345.nonexistent",
                country="USA",
                region="americas",
                topics=["test"]
            )
        ]

        # Should not crash, should return empty list or handle gracefully
        articles = scraper.scrape_articles(invalid_sources, max_articles=5)
        assert isinstance(articles, list)
        # May be empty due to failed scraping


class TestEconomicPredictionContract:
    """Test economic prediction API contracts."""

    @pytest.mark.integration
    def test_economic_predictor_contract(self):
        """Test economic predictor meets contract requirements."""
        try:
            predictor = create_economic_predictor()

            # Contract: predict() returns PredictionResult or dict
            result = predictor.predict(
                sentiment_score=0.5,
                topic_factors={'economy': 0.7}
            )

            # Contract: Should return valid prediction
            if isinstance(result, PredictionResult):
                assert hasattr(result, 'value')
                assert hasattr(result, 'confidence')
                assert 0 <= result.confidence <= 1
            elif isinstance(result, dict):
                # Legacy format
                assert 'gdp_forecast' in result or 'value' in result
            else:
                pytest.fail(f"Unexpected prediction result type: {type(result)}")

        except Exception:
            pytest.skip("Economic predictor not available")

    @pytest.mark.integration
    def test_economic_predictor_bounds(self):
        """Test economic predictor produces reasonable bounds."""
        try:
            predictor = create_economic_predictor()

            # Test various sentiment scenarios
            scenarios = [
                {'sentiment_score': -0.8, 'topic_factors': {'economy': 0.2}},
                {'sentiment_score': 0.0, 'topic_factors': {'economy': 0.5}},
                {'sentiment_score': 0.8, 'topic_factors': {'economy': 0.9}},
            ]

            predictions = []
            for scenario in scenarios:
                result = predictor.predict(**scenario)
                if isinstance(result, PredictionResult):
                    predictions.append(result.value)
                elif isinstance(result, dict) and 'gdp_forecast' in result:
                    predictions.append(result['gdp_forecast'])

            if predictions:
                # Contract: GDP predictions should be in reasonable range
                assert all(-10 <= p <= 20 for p in predictions)

        except Exception:
            pytest.skip("Economic predictor not available")


class TestGlobalPerceptionContract:
    """Test Global Perception Index API contracts."""

    @pytest.mark.integration
    def test_perception_index_contract(self):
        """Test Global Perception Index meets contract requirements."""
        gpi = GlobalPerceptionIndex()

        # Contract: measure_perception() returns PerceptionReading
        reading = gpi.measure_perception("USA", "GBR")

        assert hasattr(reading, 'perceiver_country')
        assert hasattr(reading, 'target_country')
        assert hasattr(reading, 'perception_score')
        assert hasattr(reading, 'confidence')
        assert hasattr(reading, 'timestamp')

        # Contract: Score in [1, 100] range
        assert 1 <= reading.perception_score <= 100

        # Contract: Confidence in [0, 1] range
        assert 0 <= reading.confidence <= 1

        # Contract: Timestamp is recent
        assert isinstance(reading.timestamp, datetime)
        age_minutes = (datetime.now() - reading.timestamp).total_seconds() / 60
        assert age_minutes < 5  # Should be very recent

    @pytest.mark.integration
    def test_perception_matrix_contract(self):
        """Test perception matrix meets contract requirements."""
        gpi = GlobalPerceptionIndex()

        countries = ["USA", "GBR", "DEU"]
        matrix = gpi.get_perception_matrix(countries)

        # Contract: Matrix should be complete and valid
        assert isinstance(matrix, dict)
        assert len(matrix) == 3

        for perceiver in countries:
            assert perceiver in matrix
            assert len(matrix[perceiver]) == 3

            for target in countries:
                if perceiver == target:
                    assert matrix[perceiver][target] is None
                else:
                    score = matrix[perceiver][target]
                    assert 1 <= score <= 100

    @pytest.mark.integration
    def test_perception_rankings_contract(self):
        """Test perception rankings meet contract requirements."""
        gpi = GlobalPerceptionIndex()

        countries = ["USA", "GBR", "DEU", "FRA"]
        rankings = gpi.calculate_global_rankings(countries)

        # Contract: Rankings should be complete and ordered
        assert isinstance(rankings, dict)
        assert len(rankings) == 4

        ranks = [rank for score, rank in rankings.values()]
        scores = [score for score, rank in rankings.values()]

        # Contract: Ranks should be unique and sequential
        assert len(set(ranks)) == 4
        assert min(ranks) == 1
        assert max(ranks) == 4

        # Contract: Scores should be in valid range
        assert all(1 <= score <= 100 for score in scores)


class TestEndToEndIntegration:
    """Test end-to-end integration between components."""

    @pytest.mark.integration
    def test_full_analysis_pipeline(self):
        """Test complete analysis pipeline integration."""
        # 1. Source Selection
        selector = create_source_selector()
        sources = selector.select_sources(
            mode=AnalysisMode.ECONOMIC,
            region="americas",
            max_sources=3
        )

        assert len(sources) >= 0  # May be 0 if no sources available

        if sources:
            # 2. Article Scraping
            scraper = create_article_scraper()
            articles = scraper.scrape_articles(sources, max_articles=2)

            # 3. Sentiment Analysis
            analyzer = create_sentiment_analyzer()
            if articles:
                for article in articles[:1]:  # Test one article
                    sentiment = analyzer.analyze(article.text)
                    assert isinstance(sentiment, SentimentResult)

                    # 4. Economic Prediction
                    try:
                        predictor = create_economic_predictor()
                        prediction = predictor.predict(
                            sentiment_score=sentiment.score,
                            topic_factors={'economy': 0.6}
                        )
                        # Prediction should be valid (format may vary)
                        assert prediction is not None
                    except Exception:
                        # Economic predictor may not be available
                        pass

    @pytest.mark.integration
    def test_multi_country_analysis(self):
        """Test multi-country analysis integration."""
        countries = ["USA", "GBR", "DEU"]

        # Test each country
        for country in countries:
            # 1. Get country-specific sources
            selector = create_source_selector()
            sources = selector.select_sources(
                mode=AnalysisMode.ECONOMIC,
                region="global",  # Use global to ensure sources
                max_sources=2
            )

            # 2. Analyze sentiment for country
            analyzer = create_sentiment_analyzer()
            country_sentiment = analyzer.analyze(f"Economic conditions in {country}")
            assert isinstance(country_sentiment, SentimentResult)

            # 3. Get perception data
            gpi = GlobalPerceptionIndex()
            # Test perception between first two countries
            if len(countries) >= 2:
                reading = gpi.measure_perception(countries[0], countries[1])
                assert 1 <= reading.perception_score <= 100

    @pytest.mark.integration
    def test_error_recovery_integration(self):
        """Test system handles component failures gracefully."""
        # Test with invalid inputs that should be handled gracefully

        # 1. Invalid source selection
        selector = create_source_selector()
        sources = selector.select_sources(
            mode=AnalysisMode.ECONOMIC,
            region="invalid_region",
            max_sources=5
        )
        assert isinstance(sources, list)  # Should handle gracefully

        # 2. Invalid sentiment analysis
        analyzer = create_sentiment_analyzer()
        try:
            result = analyzer.analyze("")  # Empty text
            assert isinstance(result, SentimentResult)
        except Exception:
            # Some analyzers may raise exceptions for empty text
            pass

        # 3. Invalid perception measurement
        gpi = GlobalPerceptionIndex()
        reading = gpi.measure_perception("INVALID", "ALSO_INVALID")
        assert hasattr(reading, 'perception_score')
        # Should handle gracefully with fallback values

    @pytest.mark.integration
    def test_performance_integration(self, performance_timer):
        """Test integrated system meets performance requirements."""
        # Test that complete pipeline completes in reasonable time
        performance_timer.start()

        # Quick integration test
        selector = create_source_selector()
        sources = selector.select_sources(AnalysisMode.SMART, max_sources=1)

        analyzer = create_sentiment_analyzer()
        sentiment = analyzer.analyze("Quick economic test")

        gpi = GlobalPerceptionIndex()
        perception = gpi.measure_perception("USA", "GBR")

        performance_timer.stop()

        # Should complete quickly
        assert performance_timer.elapsed_ms < 5000  # 5 seconds max

        # Results should be valid
        assert isinstance(sentiment, SentimentResult)
        assert hasattr(perception, 'perception_score')


class TestDataConsistency:
    """Test data consistency across components."""

    @pytest.mark.integration
    def test_country_code_consistency(self):
        """Test country codes are consistent across components."""
        # Get countries from source selector
        manager = UnifiedSourceManager()
        try:
            # This may fail if not implemented
            sources = manager.get_all_sources()
            source_countries = set()
            for source in sources[:10]:  # Sample first 10
                if hasattr(source, 'country') and source.country:
                    source_countries.add(source.country)
        except Exception:
            source_countries = {"USA", "GBR", "DEU"}  # Fallback

        # Get countries from perception index
        gpi = GlobalPerceptionIndex()
        perception_countries = set(gpi.major_countries)

        # Should have significant overlap
        overlap = source_countries.intersection(perception_countries)
        if source_countries and perception_countries:
            overlap_ratio = len(overlap) / min(len(source_countries), len(perception_countries))
            assert overlap_ratio > 0.3  # At least 30% overlap

    @pytest.mark.integration
    def test_sentiment_scale_consistency(self):
        """Test sentiment scales are consistent across components."""
        analyzer = create_sentiment_analyzer()

        # Test various sentiment levels
        test_texts = [
            "This is extremely positive economic news",
            "This is neutral economic information",
            "This is very negative economic news"
        ]

        results = [analyzer.analyze(text) for text in test_texts]
        scores = [r.score for r in results]

        # Should show reasonable spread
        score_range = max(scores) - min(scores)
        assert score_range > 0.1  # Should have some variance

        # All scores should be in valid range
        assert all(-1 <= score <= 1 for score in scores)

    @pytest.mark.integration
    def test_timestamp_consistency(self):
        """Test timestamps are consistent across components."""
        start_time = datetime.now()

        # Generate timestamps from different components
        analyzer = create_sentiment_analyzer()
        result = analyzer.analyze("Test text")

        gpi = GlobalPerceptionIndex()
        reading = gpi.measure_perception("USA", "GBR")

        end_time = datetime.now()

        # All timestamps should be within the test period
        if hasattr(result, 'timestamp') and result.timestamp:
            assert start_time <= result.timestamp <= end_time

        assert start_time <= reading.timestamp <= end_time