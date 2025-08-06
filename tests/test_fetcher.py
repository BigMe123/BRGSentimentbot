import asyncio
import pathlib
import sys
import types
from unittest.mock import patch

# Ensure package root on path for direct pytest invocation
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sentiment_cli_bot.bot.fetcher import gather_feed_entries


def test_gather_feed_entries_dedup() -> None:
    """Similar titles and identical URLs should be deduplicated."""

    def fake_parse(url: str) -> types.SimpleNamespace:  # pragma: no cover - helper
        entries = [
            {"title": "Example Title", "link": "http://example.com/a"},
            {"title": "Example   Title", "link": "http://example.com/a"},
        ]
        return types.SimpleNamespace(entries=entries)

    with patch("feedparser.parse", side_effect=fake_parse):
        entries = asyncio.run(gather_feed_entries(["http://feed"]))
    assert len(entries) == 1
