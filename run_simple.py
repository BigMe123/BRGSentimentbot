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
