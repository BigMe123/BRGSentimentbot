"""
Tests for connector system.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path

from sentiment_bot.connectors.base import Connector
from sentiment_bot.connectors.reddit import RedditRSS
from sentiment_bot.connectors.google_news import GoogleNewsRSS
from sentiment_bot.connectors.hackernews import HackerNewsConnector
from sentiment_bot.ingest.registry import ConnectorRegistry, CONNECTORS
from sentiment_bot.ingest.utils import make_id, parse_date, clean_text, strip_html


class TestConnectorBase:
    """Test base connector functionality."""

    def test_base_connector_interface(self):
        """Test that base connector has required interface."""
        connector = Connector()
        assert hasattr(connector, "name")
        assert hasattr(connector, "fetch")
        assert connector.name == "base"

    @pytest.mark.asyncio
    async def test_base_fetch_not_implemented(self):
        """Test that base fetch raises NotImplementedError."""
        connector = Connector()
        with pytest.raises(NotImplementedError):
            async for _ in connector.fetch():
                pass


class TestConnectorUtils:
    """Test utility functions."""

    def test_make_id(self):
        """Test ID generation."""
        # Same inputs should produce same ID
        id1 = make_id("source", "item1")
        id2 = make_id("source", "item1")
        assert id1 == id2

        # Different inputs should produce different IDs
        id3 = make_id("source", "item2")
        assert id1 != id3

        # Should handle multiple parts
        id4 = make_id("source", "sub", "item")
        assert len(id4) > 0

    def test_parse_date(self):
        """Test date parsing."""
        from datetime import datetime

        # Test various formats
        date1 = parse_date("2024-01-15")
        assert isinstance(date1, datetime)
        assert date1.year == 2024

        date2 = parse_date("2024-01-15T10:30:00Z")
        assert isinstance(date2, datetime)

        # Test None returns current time
        date3 = parse_date(None)
        assert isinstance(date3, datetime)

        # Test invalid string returns current time
        date4 = parse_date("invalid")
        assert isinstance(date4, datetime)

    def test_clean_text(self):
        """Test text cleaning."""
        # Test basic cleaning
        text = "  Hello   World  \n\n\n  Test  "
        cleaned = clean_text(text)
        assert cleaned == "Hello World\n\nTest"

        # Test empty/None
        assert clean_text("") == ""
        assert clean_text(None) == ""

        # Test whitespace normalization
        text2 = "Line1\n\n\n\n\nLine2"
        cleaned2 = clean_text(text2)
        assert cleaned2 == "Line1\n\nLine2"

    def test_strip_html(self):
        """Test HTML stripping."""
        # Test basic HTML removal
        html = "<p>Hello <b>World</b></p>"
        stripped = strip_html(html)
        assert stripped == "Hello World"

        # Test with attributes
        html2 = '<a href="test.com">Link</a> text'
        stripped2 = strip_html(html2)
        assert stripped2 == "Link text"

        # Test empty/None
        assert strip_html("") == ""
        assert strip_html(None) == ""


class TestRedditConnector:
    """Test Reddit RSS connector."""

    def test_reddit_initialization(self):
        """Test Reddit connector initialization."""
        connector = RedditRSS(subreddits=["test1", "test2"], sort="hot", limit=50)
        assert connector.name == "reddit"
        assert len(connector.subreddits) == 2
        assert connector.sort == "hot"
        assert connector.limit == 50

    def test_reddit_url_construction(self):
        """Test Reddit RSS URL construction."""
        connector = RedditRSS(subreddits=["worldnews"], sort="new")
        urls = connector._get_feed_urls()
        assert len(urls) == 1
        assert "worldnews" in urls[0]
        assert "new.rss" in urls[0]

    @pytest.mark.asyncio
    async def test_reddit_fetch_mock(self):
        """Test Reddit fetch with mocked response."""
        connector = RedditRSS(subreddits=["test"], limit=1)

        # Mock the RSS fetch
        mock_feed = {
            "entries": [
                {
                    "id": "test123",
                    "title": "Test Post",
                    "link": "https://reddit.com/r/test/comments/123",
                    "author": "testuser",
                    "published_parsed": (2024, 1, 15, 10, 0, 0, 0, 0, 0),
                    "summary": "Test content",
                }
            ]
        }

        with patch("feedparser.parse", return_value=mock_feed):
            items = []
            async for item in connector.fetch():
                items.append(item)

            assert len(items) == 1
            assert items[0]["title"] == "Test Post"
            assert items[0]["source"] == "reddit"
            assert items[0]["subsource"] == "test"


class TestGoogleNewsConnector:
    """Test Google News RSS connector."""

    def test_google_news_initialization(self):
        """Test Google News connector initialization."""
        connector = GoogleNewsRSS(
            queries=["AI", "climate"], editions=["US", "UK"], max_per_query=25
        )
        assert connector.name == "google_news"
        assert len(connector.queries) == 2
        assert len(connector.editions) == 2
        assert connector.max_per_query == 25

    def test_google_news_url_construction(self):
        """Test Google News RSS URL construction."""
        connector = GoogleNewsRSS(queries=["test"], editions=["US"])

        # Test query URL
        query_url = connector._build_query_url("test query", "US", "en")
        assert "news.google.com/rss/search" in query_url
        assert "q=test+query" in query_url
        assert "hl=en" in query_url
        assert "gl=US" in query_url

        # Test topic URL
        topic_url = connector._build_topic_url("TECHNOLOGY", "US", "en")
        assert "news.google.com/rss/topics" in topic_url
        assert "TECHNOLOGY" in topic_url


class TestHackerNewsConnector:
    """Test Hacker News connector."""

    def test_hackernews_initialization(self):
        """Test HN connector initialization."""
        connector = HackerNewsConnector(
            categories=["top", "new"], max_stories=50, fetch_comments=True
        )
        assert connector.name == "hackernews"
        assert len(connector.categories) == 2
        assert connector.max_stories == 50
        assert connector.fetch_comments is True

    @pytest.mark.asyncio
    async def test_hackernews_api_urls(self):
        """Test HN API URL construction."""
        connector = HackerNewsConnector()

        # Check base URL
        assert connector.base_url == "https://hacker-news.firebaseio.com/v0"

        # Check story list URLs
        for category in ["top", "new", "best", "ask", "show", "job"]:
            url = f"{connector.base_url}/{category}stories.json"
            assert category in url


class TestConnectorRegistry:
    """Test connector registry."""

    def test_registry_available_connectors(self):
        """Test that all connectors are registered."""
        expected = [
            "reddit",
            "google_news",
            "hackernews",
            "stackexchange",
            "mastodon",
            "bluesky",
            "youtube",
            "wikipedia",
            "gdelt",
            "generic_web",
            "twitter",
        ]

        for name in expected:
            assert name in CONNECTORS
            assert CONNECTORS[name] is not None

    def test_registry_load_config(self):
        """Test loading configuration."""
        # Create test config
        test_config = """
sources:
  - type: reddit
    subreddits: ["test"]
    limit: 10
  - type: hackernews
    max_stories: 5
"""

        with patch("builtins.open", mock_open(read_data=test_config)):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ConnectorRegistry("test.yaml")

                assert len(registry.connectors) == 2
                assert registry.connectors[0].name == "reddit"
                assert registry.connectors[1].name == "hackernews"

    def test_registry_get_connector(self):
        """Test getting specific connector."""
        registry = ConnectorRegistry("nonexistent.yaml")  # Empty registry

        # Manually add a connector
        reddit = RedditRSS(subreddits=["test"])
        registry.connectors = [reddit]

        # Test get by name
        found = registry.get_connector("reddit")
        assert found is not None
        assert found.name == "reddit"

        # Test not found
        not_found = registry.get_connector("twitter")
        assert not_found is None

    @pytest.mark.asyncio
    async def test_registry_fetch_all(self):
        """Test fetching from all connectors."""
        registry = ConnectorRegistry("nonexistent.yaml")

        # Create mock connector
        mock_connector = AsyncMock(spec=Connector)
        mock_connector.name = "test"
        mock_connector.fetch.return_value.__aiter__.return_value = iter(
            [{"id": "1", "text": "test1"}, {"id": "2", "text": "test2"}]
        )

        registry.connectors = [mock_connector]

        # Fetch all
        items = []
        async for item in registry.fetch_all():
            items.append(item)

        assert len(items) == 2
        assert items[0]["text"] == "test1"
        assert items[1]["text"] == "test2"


def mock_open(read_data=""):
    """Helper to mock file open."""
    import builtins
    from unittest.mock import mock_open as _mock_open

    return _mock_open(read_data=read_data)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
