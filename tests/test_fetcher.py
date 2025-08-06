import asyncio
import pathlib
import sys
import types
from unittest.mock import patch

# Ensure package root on path for direct pytest invocation
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sentiment_bot.fetcher import ArticleData, gather_rss


def test_gather_feed_entries_dedup() -> None:
    """Similar titles and identical URLs should be deduplicated."""

    def fake_parse(url: str) -> types.SimpleNamespace:  # pragma: no cover - helper
        entries = [
            {"title": "Example Title", "link": "http://example.com/a"},
            {"title": "Example   Title", "link": "http://example.com/a"},
        ]
        return types.SimpleNamespace(entries=entries)

    with patch(
        "sentiment_bot.fetcher.feedparser", types.SimpleNamespace(parse=fake_parse)
    ), patch(
        "sentiment_bot.fetcher.fetch_and_parse",
        side_effect=lambda url: ArticleData(url, "t", "x"),
    ):
        entries = asyncio.run(gather_rss(["http://feed"]))
    assert len(entries) == 1
