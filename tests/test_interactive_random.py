import pathlib
import sys
import types
import random
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# Stub modules to avoid heavy imports
for mod_name in [
    "scheduler",
    "ws_server",
    "bayesian",
    "chat_agent",
    "config",
    "fetcher",
    "gui",
    "meta_learning",
    "simulate",
    "rules",
]:
    full_name = f"sentiment_bot.{mod_name}"
    module = types.ModuleType(full_name)
    sys.modules.setdefault(full_name, module)

sys.modules["sentiment_bot.config"].settings = types.SimpleNamespace(TOPICS=[])
sys.modules["sentiment_bot.config"].REGION_MAP = {
    "africa": ["africa"],
    "asia": ["asia"],
}
sys.modules["sentiment_bot.config"].TOPIC_MAP = {
    "energy": ["energy"],
    "trade": ["trade"],
}
sys.modules["sentiment_bot.config"].WINDOWS = {
    "minute": timedelta(minutes=1),
    "day": timedelta(days=1),
}

analyzer_stub = types.ModuleType("sentiment_bot.analyzer")
sys.modules["sentiment_bot.analyzer"] = analyzer_stub
analyzer_stub.display_analysis_results = lambda *a, **k: None
analyzer_stub.display_ingestion_summary = lambda *a, **k: None

import sentiment_bot.interactive as interactive  # noqa: E402


class Article:
    def __init__(self, title: str, text: str, url: str):
        self.title = title
        self.text = text
        self.url = url
        self.published = datetime.utcnow()


class Analysis:
    def __init__(self, score: float):
        self.vader = score
        self.bert = score


async def fake_gather_rss():
    arts = [
        Article("Africa oil", "energy africa", "http://a"),
        Article("Asia trade", "trade asia", "http://b"),
    ]
    return arts, {"total": len(arts)}


def fake_analyze(text: str) -> Analysis:
    return Analysis(0.5 if "energy" in text else 0.1)


def fake_aggregate(results):
    class Snap:
        volatility = 0.5
        confidence = 0.9
        triggers = ["energy"]

    return Snap()


sys.modules["sentiment_bot.fetcher"].gather_rss = fake_gather_rss
analyzer_stub.analyze = fake_analyze
analyzer_stub.aggregate = fake_aggregate


@pytest.mark.skipif(
    not hasattr(interactive, "run_interactive_mode"),
    reason="run_interactive_mode not implemented",
)
def test_run_interactive_mode_random(monkeypatch):
    random.seed(0)
    region_idx = random.randint(1, len(interactive.REGION_CHOICES) - 1)
    topic_idx = random.randint(1, len(interactive.TOPIC_CHOICES) - 1)
    window_idx = random.randint(1, len(interactive.WINDOW_CHOICES))
    answers = iter([
        str(region_idx),
        str(topic_idx),
        str(window_idx),
        "Exit",
    ])
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))
    interactive.run_interactive_mode()
