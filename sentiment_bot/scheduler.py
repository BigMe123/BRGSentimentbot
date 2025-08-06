"""Async orchestration of the bot's workflow."""

from __future__ import annotations

import asyncio
from datetime import datetime

from rich.console import Console

from . import analyzer, fetcher, rules
from .config import settings

console = Console()


async def _cycle() -> analyzer.Snapshot:
    articles = await fetcher.gather_all_sources()
    topics = [t.lower() for t in settings.TOPICS]
    if topics:
        filtered: list[fetcher.ArticleData] = []
        for art in articles:
            haystack = f"{art.title} {art.text}".lower()
            if any(t in haystack for t in topics):
                filtered.append(art)
        if filtered:
            articles = filtered

    console.print("Fetched Articles:")
    for art in articles:
        console.print(f" - {art.title}")
    console.print()
    analyses = [analyzer.analyze(a.text) for a in articles]
    snapshot = analyzer.aggregate(analyses)
    snapshot.ts = datetime.utcnow().isoformat()
    alerts = rules.apply_rules(snapshot)
    if alerts:
        console.print("\n".join(alerts))
    return snapshot


async def run_once() -> analyzer.Snapshot:
    snap = await _cycle()
    console.print(
        f"Volatility {snap.volatility:.3f} (confidence {snap.confidence:.2f})"
    )
    return snap


async def run_live(interval: int | None = None) -> None:
    interval = interval or settings.INTERVAL
    while True:
        await run_once()
        await asyncio.sleep(interval * 60)
