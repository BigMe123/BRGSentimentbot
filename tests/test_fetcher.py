import asyncio
import pathlib
import sys
import time
import types
from unittest.mock import patch

# Ensure package root on path for direct pytest invocation
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sentiment_bot.fetcher import ArticleData, _fetch_and_parse_url, gather_rss


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
        "sentiment_bot.fetcher._fetch_and_parse_url",
        side_effect=lambda url: ArticleData(url, "t", "x"),
    ):
        entries = asyncio.run(gather_rss(["http://feed"]))
    assert len(entries) == 1


def test_aiohttp_failure_falls_back_to_threaded_urlopen() -> None:
    async def _run() -> None:
        def slow_urlopen(url: str):
            time.sleep(0.1)

            class Resp:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return b"<html><title>X</title><p>Hello</p></html>"

            return Resp()

        with patch(
            "sentiment_bot.fetcher.aiohttp.ClientSession.get",
            side_effect=Exception("boom"),
        ), patch("urllib.request.urlopen", slow_urlopen):
            fetch_task = asyncio.create_task(
                _fetch_and_parse_url("http://example.com")
            )
            start = time.perf_counter()
            await asyncio.sleep(0.05)
            elapsed = time.perf_counter() - start
            assert elapsed < 0.09
            assert not fetch_task.done()
            art = await fetch_task
            assert "hello" in art.text.lower()

    asyncio.run(_run())
