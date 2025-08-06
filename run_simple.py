
"""Offline demonstration of the sentiment analyzer on sample texts."""

from sentiment_bot import analyzer


def main() -> None:
    texts = [
        "Markets had a great day with excellent earnings and investors happy.",
        "The outlook was terrible and investors faced a bad recession.",
    ]
    analyses = [analyzer.analyze(t) for t in texts]
    snap = analyzer.aggregate(analyses)
    # Sanity checks
    assert 0 < snap.volatility < 1, "volatility should be within (0, 1)"
    assert 0 < snap.confidence < 1, "confidence should be within (0, 1)"
    assert snap.alert_level == "normal", "expected normal alert level"
    print(f"Volatility {snap.volatility:.3f} (confidence {snap.confidence:.2f})")


if __name__ == "__main__":
    main()
=======
"""Run a single sentiment analysis cycle with built-in sample articles.

This avoids network access so it works in restricted environments while
still exercising the scheduler and analysis pipeline."""

import asyncio
from sentiment_bot import fetcher, scheduler


async def _main() -> None:
    samples = [
        fetcher.ArticleData(
            url="https://example.com/good", 
            title="Markets rally",
            text="Markets had a great day with excellent earnings and investors happy."
        ),
        fetcher.ArticleData(
            url="https://example.com/bad", 
            title="Economic worries drag shares",
            text="The outlook was terrible and investors faced a bad recession."
        ),
    ]

    async def fake_gather_all_sources():
        return samples

    scheduler.fetcher.gather_all_sources = fake_gather_all_sources  # type: ignore
    await scheduler.run_once()


if __name__ == "__main__":
    asyncio.run(_main())

