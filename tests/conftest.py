#!/usr/bin/env python3
"""
BSG Test Configuration and Fixtures
===================================

Global test configuration, fixtures, and utilities.
"""

import pytest
import asyncio
import tempfile
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any
import numpy as np
import pandas as pd

# Import test interfaces
from sentiment_bot.interfaces import (
    Article, SentimentResult, Source, PredictionResult,
    AnalysisMode, create_sentiment_analyzer
)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_article():
    """Sample article for testing."""
    return Article(
        title="Economic Growth Accelerates in Q3",
        text="The latest economic data shows strong growth with GDP expanding at an annualized rate of 3.2%. Consumer spending remains robust while business investment continues to grow.",
        url="https://example.com/economic-growth",
        published_at=datetime.now(),
        source="TestNews",
        country="USA",
        region="americas",
        topics=["economy", "growth"],
        sentiment_score=0.6,
        metadata={"confidence": 0.8}
    )


@pytest.fixture
def sample_articles():
    """Multiple sample articles for testing."""
    return [
        Article(
            title="Strong Economic Performance",
            text="Economic indicators show robust performance across all sectors.",
            url="https://example.com/1",
            sentiment_score=0.7,
            country="USA"
        ),
        Article(
            title="Market Concerns Emerge",
            text="Recent market volatility raises concerns about future economic stability.",
            url="https://example.com/2",
            sentiment_score=-0.4,
            country="USA"
        ),
        Article(
            title="Neutral Economic Outlook",
            text="Economic conditions remain stable with mixed indicators.",
            url="https://example.com/3",
            sentiment_score=0.1,
            country="USA"
        )
    ]


@pytest.fixture
def sample_source():
    """Sample source for testing."""
    return Source(
        name="Test Economic News",
        url="https://example.com/rss",
        domain="example.com",
        country="USA",
        region="americas",
        topics=["economy", "business"],
        priority=0.8,
        rss_endpoints=["https://example.com/feed.xml"]
    )


@pytest.fixture
def sample_sources():
    """Multiple sample sources for testing."""
    return [
        Source(
            name="US Economic Times",
            url="https://usnews.com/rss",
            domain="usnews.com",
            country="USA",
            region="americas",
            topics=["economy", "politics"],
            priority=0.9
        ),
        Source(
            name="European Business Daily",
            url="https://eurobiz.com/feed",
            domain="eurobiz.com",
            country="germany",
            region="europe",
            topics=["business", "finance"],
            priority=0.8
        ),
        Source(
            name="Global Market Watch",
            url="https://globalmarket.com/rss",
            domain="globalmarket.com",
            country="global",
            region="global",
            topics=["markets", "finance"],
            priority=0.95
        )
    ]


@pytest.fixture
def sample_sentiment_result():
    """Sample sentiment result for testing."""
    return SentimentResult(
        score=0.65,
        label="positive",
        confidence=0.85,
        components={
            "vader": 0.6,
            "bert": 0.7,
            "ensemble": 0.65
        }
    )


@pytest.fixture
def sample_prediction_result():
    """Sample prediction result for testing."""
    return PredictionResult(
        value=2.8,
        confidence=0.75,
        confidence_interval=(2.2, 3.4),
        horizon="1_quarter",
        drivers=["strong consumer spending", "business investment growth"],
        methodology="bridge_equation",
        metadata={"model_version": "v1.0", "features_used": 12}
    )


@pytest.fixture
def mock_rss_feed():
    """Mock RSS feed data for testing."""
    return {
        "feed": {
            "title": "Test News Feed",
            "link": "https://example.com",
            "description": "Test RSS feed for unit tests",
            "language": "en"
        },
        "entries": [
            {
                "title": "Economic Growth Continues",
                "link": "https://example.com/article1",
                "description": "GDP growth remains strong this quarter",
                "published": "Mon, 15 Sep 2025 10:00:00 GMT",
                "summary": "Economic indicators show continued growth"
            },
            {
                "title": "Market Volatility Increases",
                "link": "https://example.com/article2",
                "description": "Stock markets show increased volatility",
                "published": "Mon, 15 Sep 2025 11:00:00 GMT",
                "summary": "Markets react to economic uncertainty"
            }
        ]
    }


@pytest.fixture
def mock_economic_data():
    """Mock economic data for testing."""
    dates = pd.date_range(start='2020-01-01', end='2024-12-31', freq='Q')
    return pd.DataFrame({
        'date': dates,
        'gdp_growth': np.random.normal(2.5, 1.0, len(dates)),
        'unemployment': np.random.normal(4.0, 0.5, len(dates)),
        'inflation': np.random.normal(2.0, 0.3, len(dates)),
        'sentiment': np.random.normal(0.1, 0.2, len(dates))
    })


@pytest.fixture
def mock_sentiment_data():
    """Mock sentiment data for testing."""
    return {
        'overall': 0.3,
        'economic': 0.4,
        'employment': 0.2,
        'inflation': -0.1,
        'market': 0.5,
        'trade': 0.1
    }


# Test utilities
class TestDataValidator:
    """Validate test data quality."""

    @staticmethod
    def validate_article(article: Article) -> bool:
        """Validate article has required fields."""
        return (
            bool(article.title) and
            bool(article.text) and
            bool(article.url) and
            article.sentiment_score is not None and
            -1 <= article.sentiment_score <= 1
        )

    @staticmethod
    def validate_source(source: Source) -> bool:
        """Validate source has required fields."""
        return (
            bool(source.name) and
            bool(source.url) and
            bool(source.domain) and
            bool(source.country) and
            bool(source.region) and
            0 <= source.priority <= 1
        )

    @staticmethod
    def validate_prediction(prediction: PredictionResult) -> bool:
        """Validate prediction result."""
        return (
            prediction.value is not None and
            0 <= prediction.confidence <= 1 and
            len(prediction.confidence_interval) == 2 and
            prediction.confidence_interval[0] <= prediction.confidence_interval[1]
        )


# Performance test helpers
@pytest.fixture
def performance_timer():
    """Timer for performance tests."""
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None

        def start(self):
            self.start_time = datetime.now()

        def stop(self):
            self.end_time = datetime.now()

        @property
        def elapsed_ms(self):
            if self.start_time and self.end_time:
                return (self.end_time - self.start_time).total_seconds() * 1000
            return None

    return Timer()


# Test markers and categories
pytest_plugins = ["pytest_asyncio"]

# Global test configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "requires_network: mark test as requiring network access"
    )
    config.addinivalue_line(
        "markers", "requires_api_key: mark test as requiring API keys"
    )
    config.addinivalue_line(
        "markers", "expensive: mark test as computationally expensive"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add automatic markers."""
    for item in items:
        # Add slow marker to tests that take >1s
        if "slow" not in item.keywords:
            if any(marker in item.name.lower() for marker in ["integration", "e2e", "performance"]):
                item.add_marker(pytest.mark.slow)

        # Add network marker to tests that use external APIs
        if any(keyword in item.name.lower() for keyword in ["rss", "api", "fetch", "scrape"]):
            item.add_marker(pytest.mark.requires_network)