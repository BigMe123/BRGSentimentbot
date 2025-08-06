"""Async orchestration of fetching and analysis."""

from __future__ import annotations

import asyncio

from rich.console import Console
from rich.live import Live

from . import config
from .analyzer import aggregate, analyze
from .fetcher import download_and_parse, gather_feed_entries

console = Console()


async def run_once() -> None:
    """Fetch, analyse and print a single snapshot."""

    entries = await gather_feed_entries(config.RSS_FEEDS)
    entries = entries[: config.MAX_ARTICLES_PER_CYCLE]

    articles = []
    for entry in entries:
        try:
            parsed = await download_and_parse(entry.url)
        except Exception:
            continue
        articles.append(parsed)

    results = [analyze(a.text) for a in articles]
    snapshot = aggregate(results)
    console.print(
        f"Volatility {snapshot.volatility_score:.3f} (confidence {snapshot.confidence:.2f})"
    )


async def run_live(interval: int = 30) -> None:
    """Continuously run :func:`run_once` every ``interval`` minutes."""

    with Live(console=console, refresh_per_second=1):
        while True:
            await run_once()
            await asyncio.sleep(interval * 60)
