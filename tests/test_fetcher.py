import asyncio
import pathlib
import sys
import types
from urllib.error import URLError
from unittest.mock import patch

import pytest

# Ensure package root on path for direct pytest invocation
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sentiment_bot.fetcher import ArticleData, gather_rss, _fetch_and_parse_url


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


def test_urlopen_uses_timeout_and_parses() -> None:
    class FakeResp:
        def read(self) -> bytes:
            return b"<html><p>Hello</p></html>"

        def __enter__(self) -> "FakeResp":  # pragma: no cover - context helper
            return self

        def __exit__(
            self, exc_type, exc, tb
        ) -> None:  # pragma: no cover - context helper
            pass

    class FakeSession:
        async def __aenter__(
            self,
        ) -> "FakeSession":  # pragma: no cover - context helper
            return self

        async def __aexit__(
            self, exc_type, exc, tb
        ) -> None:  # pragma: no cover - context helper
            pass

        def get(self, url: str, timeout: int) -> None:  # pragma: no cover - helper
            raise Exception("boom")

    def fake_urlopen(url: str, timeout: int) -> FakeResp:
        assert timeout == 10
        return FakeResp()

    fake_newspaper = types.SimpleNamespace(
        Article=lambda *args, **kwargs: (_ for _ in ()).throw(Exception("boom"))
    )

    with patch.dict(sys.modules, {"newspaper": fake_newspaper}), patch(
        "sentiment_bot.fetcher.aiohttp.ClientSession", return_value=FakeSession()
    ), patch("urllib.request.urlopen", side_effect=fake_urlopen):
        art = asyncio.run(_fetch_and_parse_url("http://example.com"))
    assert art.text.strip() == "Hello"


def test_urlopen_error_propagates() -> None:
    class FakeSession:
        async def __aenter__(
            self,
        ) -> "FakeSession":  # pragma: no cover - context helper
            return self

        async def __aexit__(
            self, exc_type, exc, tb
        ) -> None:  # pragma: no cover - context helper
            pass

        def get(self, url: str, timeout: int) -> None:  # pragma: no cover - helper
            raise Exception("boom")

    def fake_urlopen(url: str, timeout: int) -> None:
        raise URLError("fail")

    fake_newspaper = types.SimpleNamespace(
        Article=lambda *args, **kwargs: (_ for _ in ()).throw(Exception("boom"))
    )

    with patch.dict(sys.modules, {"newspaper": fake_newspaper}), patch(
        "sentiment_bot.fetcher.aiohttp.ClientSession", return_value=FakeSession()
    ), patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(URLError):
            asyncio.run(_fetch_and_parse_url("http://example.com"))
