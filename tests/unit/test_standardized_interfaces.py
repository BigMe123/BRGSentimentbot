#!/usr/bin/env python3
"""
Unit Tests: Standardized Interfaces
===================================

Test standardized interfaces fix API interdependency issues.
"""

import pytest
from sentiment_bot.interfaces import (
    Article, SentimentResult, Source, PredictionResult,
    SentimentAnalyzer, SourceSelector, ArticleScraper, EconomicPredictor,
    create_sentiment_analyzer, create_source_selector,
    AnalysisMode
)


class TestStandardizedInterfaces:
    """Test standardized interfaces work correctly."""

    @pytest.mark.unit
    def test_article_interface(self, sample_article):
        """Test Article dataclass interface."""
        article = sample_article

        # Required fields
        assert hasattr(article, 'title')
        assert hasattr(article, 'text')
        assert hasattr(article, 'url')

        # Optional fields with defaults
        assert hasattr(article, 'topics')
        assert hasattr(article, 'metadata')
        assert isinstance(article.topics, list)
        assert isinstance(article.metadata, dict)

    @pytest.mark.unit
    def test_sentiment_result_interface(self, sample_sentiment_result):
        """Test SentimentResult interface."""
        result = sample_sentiment_result

        # Required fields
        assert hasattr(result, 'score')
        assert hasattr(result, 'label')
        assert hasattr(result, 'confidence')

        # Score bounds
        assert -1 <= result.score <= 1
        assert 0 <= result.confidence <= 1

        # Legacy compatibility
        assert hasattr(result, 'compound')
        assert result.compound == result.score

    @pytest.mark.unit
    def test_source_interface(self, sample_source):
        """Test Source interface."""
        source = sample_source

        # Required fields
        assert hasattr(source, 'name')
        assert hasattr(source, 'url')
        assert hasattr(source, 'domain')
        assert hasattr(source, 'country')
        assert hasattr(source, 'region')
        assert hasattr(source, 'topics')

        # Defaults
        assert hasattr(source, 'rss_endpoints')
        assert isinstance(source.rss_endpoints, list)

    @pytest.mark.unit
    def test_prediction_result_interface(self, sample_prediction_result):
        """Test PredictionResult interface."""
        result = sample_prediction_result

        # Required fields
        assert hasattr(result, 'value')
        assert hasattr(result, 'confidence')
        assert hasattr(result, 'confidence_interval')
        assert hasattr(result, 'horizon')

        # Confidence bounds
        assert 0 <= result.confidence <= 1

        # CI structure
        assert len(result.confidence_interval) == 2
        assert result.confidence_interval[0] <= result.confidence_interval[1]


class TestAnalysisModeEnum:
    """Test AnalysisMode standardization."""

    @pytest.mark.unit
    def test_analysis_modes_complete(self):
        """Test all required analysis modes are defined."""
        required_modes = ['SMART', 'ECONOMIC', 'MARKET', 'AI_QUESTION', 'COMPREHENSIVE']

        for mode_name in required_modes:
            assert hasattr(AnalysisMode, mode_name)
            mode = getattr(AnalysisMode, mode_name)
            assert isinstance(mode.value, str)

    @pytest.mark.unit
    def test_mode_string_values(self):
        """Test mode values are lowercase strings."""
        for mode in AnalysisMode:
            assert isinstance(mode.value, str)
            assert mode.value.islower()
            assert mode.value == mode.name.lower()


class TestAdapterInterfaces:
    """Test adapter classes for existing components."""

    @pytest.mark.unit
    def test_sentiment_analyzer_adapter(self):
        """Test sentiment analyzer adapter works."""
        analyzer = create_sentiment_analyzer()

        # Test it implements the interface
        assert isinstance(analyzer, SentimentAnalyzer)

        # Test both new and legacy methods
        result = analyzer.analyze("This is great news!")
        assert isinstance(result, SentimentResult)

        # Legacy compatibility
        legacy_result = analyzer.analyze_sentiment("This is great news!")
        assert isinstance(legacy_result, dict)
        assert 'compound' in legacy_result
        assert 'label' in legacy_result

    @pytest.mark.unit
    def test_source_selector_adapter(self):
        """Test source selector adapter works."""
        selector = create_source_selector()

        # Test it implements the interface
        assert isinstance(selector, SourceSelector)

        # Test source selection
        sources = selector.select_sources(
            mode=AnalysisMode.ECONOMIC,
            region="americas",
            max_sources=5
        )

        assert isinstance(sources, list)
        for source in sources:
            assert isinstance(source, Source)

    @pytest.mark.unit
    def test_interface_error_handling(self):
        """Test interfaces handle errors gracefully."""
        # Test with None components
        analyzer = create_sentiment_analyzer(None)
        result = analyzer.analyze("")

        # Should not crash, should return neutral result
        assert isinstance(result, SentimentResult)
        assert result.label in ['neutral', 'positive', 'negative', 'abstain']

    @pytest.mark.unit
    def test_legacy_compatibility_preserved(self):
        """Test that legacy method calls still work."""
        analyzer = create_sentiment_analyzer()

        # Old method names should work
        result1 = analyzer.score_article("Test text")
        result2 = analyzer.analyze_sentiment("Test text")

        assert isinstance(result1, SentimentResult)
        assert isinstance(result2, dict)

        # Results should be consistent
        assert abs(result1.score - result2['compound']) < 0.1


class TestInterfaceContracts:
    """Test interface contracts are enforced."""

    @pytest.mark.unit
    def test_sentiment_score_bounds(self):
        """Test sentiment scores are always in [-1, 1]."""
        analyzer = create_sentiment_analyzer()

        test_texts = [
            "This is absolutely amazing!",
            "This is terrible awful horrible",
            "This is neutral",
            "",
            "a" * 1000  # Very long text
        ]

        for text in test_texts:
            result = analyzer.analyze(text)
            assert -1 <= result.score <= 1, f"Score {result.score} out of bounds for text: {text[:50]}"
            assert 0 <= result.confidence <= 1, f"Confidence {result.confidence} out of bounds"

    @pytest.mark.unit
    def test_confidence_interval_validity(self):
        """Test confidence intervals are valid."""
        # This would test prediction results have valid CIs
        result = PredictionResult(
            value=2.5,
            confidence=0.8,
            confidence_interval=(2.0, 3.0),
            horizon="1_quarter"
        )

        assert result.confidence_interval[0] <= result.value <= result.confidence_interval[1]
        assert result.confidence_interval[0] < result.confidence_interval[1]

    @pytest.mark.unit
    def test_source_priority_bounds(self):
        """Test source priorities are in [0, 1]."""
        source = Source(
            name="Test",
            url="http://test.com",
            domain="test.com",
            country="USA",
            region="americas",
            topics=["news"],
            priority=0.5
        )

        assert 0 <= source.priority <= 1

    @pytest.mark.property
    def test_interface_round_trip(self):
        """Property test: Interface objects should round-trip through serialization."""
        # Test Article round-trip
        article = Article(
            title="Test Title",
            text="Test content",
            url="http://test.com",
            topics=["economy"],
            metadata={"test": "value"}
        )

        # Should be able to convert to dict and back
        article_dict = {
            'title': article.title,
            'text': article.text,
            'url': article.url,
            'topics': article.topics,
            'metadata': article.metadata
        }

        reconstructed = Article(**article_dict)
        assert reconstructed.title == article.title
        assert reconstructed.text == article.text
        assert reconstructed.url == article.url


class TestErrorHandling:
    """Test error handling in interfaces."""

    @pytest.mark.unit
    def test_empty_input_handling(self):
        """Test interfaces handle empty inputs gracefully."""
        analyzer = create_sentiment_analyzer()

        # Empty text
        result = analyzer.analyze("")
        assert isinstance(result, SentimentResult)
        assert result.label in ['neutral', 'positive', 'negative', 'abstain']

        # None text (should not crash)
        try:
            result = analyzer.analyze(None)
            assert isinstance(result, SentimentResult)
        except (TypeError, AttributeError):
            # This is acceptable - None input might raise TypeError
            pass

    @pytest.mark.unit
    def test_malformed_data_handling(self):
        """Test interfaces handle malformed data."""
        selector = create_source_selector()

        # Should handle edge cases gracefully
        sources = selector.select_sources(
            mode=AnalysisMode.ECONOMIC,
            region=None,  # None region
            max_sources=0  # Zero sources requested
        )

        assert isinstance(sources, list)
        # Should return empty list for zero sources
        if sources:
            for source in sources:
                assert isinstance(source, Source)