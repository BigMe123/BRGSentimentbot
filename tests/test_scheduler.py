import importlib
import asyncio

import pytest

config = importlib.reload(importlib.import_module("sentiment_bot.config"))
analyzer = importlib.reload(importlib.import_module("sentiment_bot.analyzer"))
fetcher = importlib.reload(importlib.import_module("sentiment_bot.fetcher"))
scheduler = importlib.reload(importlib.import_module("sentiment_bot.scheduler"))
scheduler.fetcher = fetcher
settings = config.settings


class Dummy(fetcher.ArticleData):
    def __init__(self, text: str, title: str = ""):
        super().__init__(url="", title=title, text=text)


async def fake_gather_all_sources():
    return [Dummy("foo news"), Dummy("bar news")]


def fake_analyze(text: str) -> analyzer.Analysis:
    return analyzer.Analysis(vader=1.0 if "foo" in text else 0.0, bert=0.0, labels=[], summary="")


def test_topic_filtering(monkeypatch):
    settings.TOPICS = ["foo"]
    monkeypatch.setattr(fetcher, "gather_all_sources", fake_gather_all_sources)
    monkeypatch.setattr(analyzer, "analyze", fake_analyze)
    snap = asyncio.run(scheduler.run_once())
    assert snap.volatility > 0
    assert snap.confidence > 0
