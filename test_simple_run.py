#!/usr/bin/env python3
"""
Simple test to verify pipeline components work.
"""

import asyncio
from sentiment_bot.fetcher_optimized import fetch_with_budget


async def test():
    """Test basic pipeline functionality."""
    print("Testing pipeline with 2 feeds, 30 second budget...")

    test_feeds = [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    ]

    try:
        result = await fetch_with_budget(
            feed_urls=test_feeds,
            budget_seconds=30,
        )

        print(f"✅ Success!")
        print(f"   Articles collected: {len(result.articles)}")
        print(
            f"   Fetch success rate: {result.metrics.get('fetch_success_rate', 0):.1%}"
        )
        print(f"   Runtime: {result.metrics.get('runtime_seconds', 0):.1f}s")

        if result.alerts:
            print(f"   Alerts: {len(result.alerts)}")
            for alert in result.alerts[:3]:
                print(f"     - {alert.message}")

        return True

    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test())
    exit(0 if success else 1)
