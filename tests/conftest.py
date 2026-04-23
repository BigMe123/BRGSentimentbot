"""Test configuration and fixtures."""

import pytest
import asyncio
import tempfile
from pathlib import Path


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_rss_feed():
    return {
        "feed": {
            "title": "Test News Feed",
            "link": "https://example.com",
            "description": "Test RSS feed",
            "language": "en",
        },
        "entries": [
            {
                "title": "Economic Growth Continues",
                "link": "https://example.com/article1",
                "description": "GDP growth remains strong this quarter",
                "published": "Mon, 15 Sep 2025 10:00:00 GMT",
                "summary": "Economic indicators show continued growth",
            },
            {
                "title": "Market Volatility Increases",
                "link": "https://example.com/article2",
                "description": "Stock markets show increased volatility",
                "published": "Mon, 15 Sep 2025 11:00:00 GMT",
                "summary": "Markets react to economic uncertainty",
            },
        ],
    }
