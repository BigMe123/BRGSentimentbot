# tests/test_interactive_random.py

import pathlib
import sys
import types
import random
from datetime import datetime, timedelta
import pytest  # optional, handy for pytest.fail or future assertions

# ensure package root on path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# Stub modules to avoid heavy imports / side effects
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

# Minimal config surface the code expects
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

# Lightweight analyzer stub (no-op display, simple analyze/aggregate)
analyzer_stub = types.ModuleType("sentiment_bot.analyzer")
sys.modules["sentiment_bot.analyzer"] = analyzer_stub
analyzer_stub.display_analysis_results = lambda *a, **k: None
analyzer_stub.display_ingestion_summary = lambda *a, **k: None

# Import after stubbing
import sentiment_bot.interactive as interactive  # noqa: E402
from sentiment_bot.interactive import (  # noqa: E402
    REGION_CHOICES,
    TOPIC_CHOICES,
    WINDOW_CHOICES,
)
from sentiment_bot.cli import interactive as cli_interactive  # noqa: E402


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


def _fake_articles():
    # two simple items that cover different topics/regions
    return [
        Article("Africa oil", "energy africa", "http://a"),
        Article("Asia trade", "trade asia", "http://b"),
    ]


async def fake_gather_rss():
    arts = _fake_articles()
    return arts, {"total": len(arts)}


def fake_analyze(text: str) -> Analysis:
    # deterministic: "energy" => higher score, else lower
    return Analysis(0.5 if "energy" in text else 0.1)


def fake_aggregate(results):
    class Snap:
        volatility = 0.5
        confidence = 0.9
        triggers = ["energy"]

    return Snap()


# Wire stubs
sys.modules["sentiment_bot.fetcher"].gather_rss = fake_gather_rss
analyzer_stub.analyze = fake_analyze
analyzer_stub.aggregate = fake_aggregate

# Expose CLI interactive function so the test calls the real flow
interactive.run_interactive_mode = cli_interactive


def test_run_interactive_mode_random(monkeypatch):
    # Deterministic randomness for CI
    random.seed(42)

    # Choose indices from actual menus; skip index 0 if that's "all"
    region_idx = random.randint(1, len(REGION_CHOICES) - 1)
    topic_idx = random.randint(1, len(TOPIC_CHOICES) - 1)
    window_idx = random.randint(1, len(WINDOW_CHOICES))

    # Simulated answers; include "Exit" in case the loop shows a post-run menu
    answers = iter([str(region_idx), str(topic_idx), str(window_idx), "Exit"])

    # The CLI uses Rich's Prompt.ask; patch it to feed our choices
    monkeypatch.setattr("sentiment_bot.cli.Prompt.ask", lambda *a, **k: next(answers))

    # Should complete a cycle without throwing
    interactive.run_interactive_mode()
