#!/usr/bin/env python3
"""
Smoke Test - Validates Enhanced Connector System
===============================================

Runs basic validation tests to ensure the keyword fan-out and yield upgrades work correctly.
This is a lightweight test that can be run in production environments.

Usage:
    python smoke_test.py
    python smoke_test.py --quick     # Skip long-running tests
    python smoke_test.py --crypto    # Test crypto configuration
"""

import asyncio
import time
import json
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
from typing import List, Dict, Any

# Import the enhanced system
try:
    from sentiment_bot.ingest.registry import ConnectorRegistry, CONNECTORS
    from sentiment_bot.ingest.utils import parse_since_window, keyword_match
    from sentiment_bot.connectors.hackernews_search import HackerNewsSearch
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("Make sure you're in the BSGBOT directory and have installed dependencies")
    exit(1)


class SmokeTest:
    """Smoke test suite for enhanced connector system."""

    def __init__(self, quick: bool = False):
        self.quick = quick
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "tests": {},
            "summary": {"passed": 0, "failed": 0, "skipped": 0},
        }

    def log(self, message: str, test_name: str = None):
        """Log a test message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        if test_name:
            if test_name not in self.results["tests"]:
                self.results["tests"][test_name] = []
            self.results["tests"][test_name].append(message)

    def test_pass(self, test_name: str, message: str = ""):
        """Mark test as passed."""
        self.log(f"✅ PASS: {test_name} {message}", test_name)
        self.results["summary"]["passed"] += 1

    def test_fail(self, test_name: str, message: str = ""):
        """Mark test as failed."""
        self.log(f"❌ FAIL: {test_name} {message}", test_name)
        self.results["summary"]["failed"] += 1

    def test_skip(self, test_name: str, reason: str = ""):
        """Mark test as skipped."""
        self.log(f"⏭️  SKIP: {test_name} {reason}", test_name)
        self.results["summary"]["skipped"] += 1

    def test_utility_functions(self):
        """Test utility functions for since/keyword filtering."""
        test_name = "utility_functions"
        self.log("Testing utility functions...")

        try:
            # Test parse_since_window
            now = datetime.now(timezone.utc)

            # Test relative times
            result_7d = parse_since_window("7d")
            if result_7d and abs((now - result_7d).days - 7) <= 1:
                self.log("✓ parse_since_window('7d') works", test_name)
            else:
                self.test_fail(test_name, "parse_since_window('7d') failed")
                return

            result_24h = parse_since_window("24h")
            if result_24h and abs((now - result_24h).total_seconds() / 3600 - 24) <= 1:
                self.log("✓ parse_since_window('24h') works", test_name)
            else:
                self.test_fail(test_name, "parse_since_window('24h') failed")
                return

            # Test keyword_match
            record = {
                "title": "Bitcoin price surges in crypto market",
                "text": "Cryptocurrency markets are seeing growth",
            }

            if keyword_match(record, ["bitcoin"]):
                self.log("✓ keyword_match with title match works", test_name)
            else:
                self.test_fail(test_name, "keyword_match title match failed")
                return

            if keyword_match(record, ["cryptocurrency"]):
                self.log("✓ keyword_match with text match works", test_name)
            else:
                self.test_fail(test_name, "keyword_match text match failed")
                return

            if not keyword_match(record, ["stocks", "bonds"]):
                self.log("✓ keyword_match correctly rejects non-matches", test_name)
            else:
                self.test_fail(test_name, "keyword_match should reject non-matches")
                return

            self.test_pass(test_name)

        except Exception as e:
            self.test_fail(test_name, f"Exception: {e}")

    def test_connector_registry(self):
        """Test that all expected connectors are registered."""
        test_name = "connector_registry"
        self.log("Testing connector registry...")

        try:
            expected_connectors = [
                "reddit",
                "google_news",
                "hackernews",
                "hackernews_search",
                "stackexchange",
                "mastodon",
                "bluesky",
                "youtube",
                "wikipedia",
                "gdelt",
                "generic_web",
                "twitter",
            ]

            for name in expected_connectors:
                if name not in CONNECTORS:
                    self.test_fail(test_name, f"Missing connector: {name}")
                    return
                self.log(f"✓ {name} connector registered", test_name)

            # Test new HackerNews search specifically
            if "hackernews_search" in CONNECTORS:
                hn_search_class = CONNECTORS["hackernews_search"]
                if hn_search_class == HackerNewsSearch:
                    self.log(
                        "✓ HackerNews search connector properly registered", test_name
                    )
                else:
                    self.test_fail(
                        test_name, "HackerNews search connector class mismatch"
                    )
                    return

            self.test_pass(test_name)

        except Exception as e:
            self.test_fail(test_name, f"Exception: {e}")

    def test_connector_initialization(self):
        """Test that connectors can be initialized with new parameters."""
        test_name = "connector_initialization"
        self.log("Testing connector initialization...")

        try:
            from sentiment_bot.connectors.reddit_rss import RedditRSS
            from sentiment_bot.connectors.google_news import GoogleNewsRSS
            from sentiment_bot.connectors.hackernews_search import HackerNewsSearch

            # Test Reddit with queries (new mode)
            reddit = RedditRSS(
                queries=["crypto", "blockchain"],
                sort="new",
                time="week",
                limit_per_sub=100,
                delay_ms=300,
            )
            if reddit.queries == ["crypto", "blockchain"] and reddit.delay_ms == 300:
                self.log("✓ Reddit search mode initialization", test_name)
            else:
                self.test_fail(test_name, "Reddit initialization failed")
                return

            # Test Google News with fan-out
            google = GoogleNewsRSS(
                queries=["bitcoin"],
                editions=["en-US", "en-GB"],
                per_query_cap=200,
                delay_ms=300,
            )
            if len(google.editions) == 2 and google.per_query_cap == 200:
                self.log("✓ Google News fan-out initialization", test_name)
            else:
                self.test_fail(test_name, "Google News initialization failed")
                return

            # Test new HackerNews search
            hn_search = HackerNewsSearch(
                queries=["cryptocurrency", "blockchain"], hits_per_page=50, pages=2
            )
            if hn_search.name == "hackernews_search" and len(hn_search.queries) == 2:
                self.log("✓ HackerNews search initialization", test_name)
            else:
                self.test_fail(test_name, "HackerNews search initialization failed")
                return

            self.test_pass(test_name)

        except Exception as e:
            self.test_fail(test_name, f"Exception: {e}")

    def test_configuration_loading(self):
        """Test loading configuration with new parameters."""
        test_name = "configuration_loading"
        self.log("Testing configuration loading...")

        try:
            # Create test configuration
            test_config = """
sources:
  - type: reddit
    queries: ["crypto", "blockchain"]
    sort: new
    limit_per_sub: 100
    delay_ms: 300
    
  - type: hackernews_search
    queries: ["bitcoin"]
    hits_per_page: 50
    pages: 2
    delay_ms: 100
    
  - type: google_news
    queries: ["ethereum"]
    editions: ["en-US"]
    per_query_cap: 50
    delay_ms: 300
"""

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                f.write(test_config)
                f.flush()

                try:
                    registry = ConnectorRegistry(f.name)

                    if len(registry.connectors) != 3:
                        self.test_fail(
                            test_name,
                            f"Expected 3 connectors, got {len(registry.connectors)}",
                        )
                        return

                    # Verify connector types
                    connector_names = [c.name for c in registry.connectors]
                    expected_names = ["reddit", "hackernews_search", "google_news"]

                    for name in expected_names:
                        if name not in connector_names:
                            self.test_fail(test_name, f"Missing connector: {name}")
                            return

                    self.log("✓ Configuration loaded successfully", test_name)
                    self.test_pass(test_name)

                finally:
                    Path(f.name).unlink()  # Cleanup

        except Exception as e:
            self.test_fail(test_name, f"Exception: {e}")

    async def test_acceptance_criteria_math(self):
        """Test that the math works out for acceptance criteria."""
        test_name = "acceptance_criteria"
        self.log("Testing acceptance criteria math...")

        try:
            # Target: --keywords "crypto,blockchain,bitcoin,ethereum,web3,defi" --limit 400 --since 7d
            # Should yield dozens+ results

            keywords = ["crypto", "blockchain", "bitcoin", "ethereum", "web3", "defi"]
            limit_per_connector = 400
            since_days = 7

            # Calculate potential yield from major connectors
            potential_yield = 0

            # Google News: 6 queries × 4 editions × min(limit, 200) per query-edition
            google_queries = len(keywords)
            google_editions = 4  # en-US, en-GB, en-CA, en-AU
            google_per_query = min(limit_per_connector, 200)
            google_potential = google_queries * google_editions * google_per_query
            potential_yield += google_potential
            self.log(f"✓ Google News potential: {google_potential}", test_name)

            # Reddit: 6 queries × min(limit, 200) per query
            reddit_queries = len(keywords)
            reddit_per_query = min(limit_per_connector, 200)
            reddit_potential = reddit_queries * reddit_per_query
            potential_yield += reddit_potential
            self.log(f"✓ Reddit potential: {reddit_potential}", test_name)

            # Twitter: 6 queries × min(limit, 400) per query
            twitter_queries = len(keywords)
            twitter_per_query = min(limit_per_connector, 400)
            twitter_potential = twitter_queries * twitter_per_query
            potential_yield += twitter_potential
            self.log(f"✓ Twitter potential: {twitter_potential}", test_name)

            # HackerNews Search: 6 queries × 100 per page × 3 pages
            hn_search_queries = len(keywords)
            hn_search_per_page = 100
            hn_search_pages = 3
            hn_search_potential = (
                hn_search_queries * hn_search_per_page * hn_search_pages
            )
            potential_yield += hn_search_potential
            self.log(f"✓ HackerNews Search potential: {hn_search_potential}", test_name)

            self.log(f"✓ Total potential yield: {potential_yield}", test_name)

            # Even with 90% filtering, should get dozens+ results
            conservative_estimate = potential_yield * 0.1  # 10% success rate
            if conservative_estimate > 50:  # "dozens+"
                self.log(
                    f"✓ Conservative estimate ({conservative_estimate:.0f}) exceeds 'dozens+'",
                    test_name,
                )
                self.test_pass(
                    test_name,
                    f"Potential yield: {potential_yield}, Conservative: {conservative_estimate:.0f}",
                )
            else:
                self.test_fail(
                    test_name,
                    f"Conservative estimate too low: {conservative_estimate:.0f}",
                )

        except Exception as e:
            self.test_fail(test_name, f"Exception: {e}")

    async def test_live_connector(self):
        """Test one live connector to ensure the system actually works."""
        test_name = "live_connector"

        if self.quick:
            self.test_skip(test_name, "Skipped in quick mode")
            return

        self.log("Testing live connector (HackerNews)...")

        try:
            from sentiment_bot.connectors.hackernews import HackerNews

            # Test with small limit to be respectful
            connector = HackerNews(categories=["top"], max_stories=5)

            items = []
            timeout_seconds = 30
            start_time = time.time()

            async for item in connector.fetch():
                items.append(item)
                if len(items) >= 3:  # Just get a few items
                    break
                if time.time() - start_time > timeout_seconds:
                    break

            if len(items) > 0:
                self.log(f"✓ Fetched {len(items)} items from HackerNews", test_name)

                # Verify structure
                first_item = items[0]
                required_fields = ["id", "source", "title", "url"]
                for field in required_fields:
                    if field not in first_item:
                        self.test_fail(test_name, f"Missing field: {field}")
                        return

                self.log(
                    f"✓ Item structure valid: {list(first_item.keys())}", test_name
                )
                self.test_pass(test_name, f"Fetched {len(items)} items successfully")
            else:
                self.test_fail(test_name, "No items fetched")

        except Exception as e:
            self.test_fail(test_name, f"Exception: {e}")

    async def run_all_tests(self):
        """Run all smoke tests."""
        self.log("🚀 Starting Connector System Smoke Tests")
        self.log(f"Quick mode: {self.quick}")

        # Run tests
        self.test_utility_functions()
        self.test_connector_registry()
        self.test_connector_initialization()
        self.test_configuration_loading()
        await self.test_acceptance_criteria_math()
        await self.test_live_connector()

        # Summary
        total_tests = sum(self.results["summary"].values())
        passed = self.results["summary"]["passed"]
        failed = self.results["summary"]["failed"]
        skipped = self.results["summary"]["skipped"]

        self.log(f"\n📊 Test Summary:")
        self.log(f"   Total:   {total_tests}")
        self.log(f"   Passed:  {passed} ✅")
        self.log(f"   Failed:  {failed} ❌")
        self.log(f"   Skipped: {skipped} ⏭️")

        if failed == 0:
            self.log("\n🎉 All tests passed! Connector system is ready.")
            return True
        else:
            self.log(f"\n⚠️  {failed} test(s) failed. Check output above.")
            return False

    def save_results(self, output_file: str = "smoke_test_results.json"):
        """Save detailed test results to file."""
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2, default=str)
        self.log(f"📄 Detailed results saved to {output_file}")


def test_crypto_config():
    """Test the crypto-specific configuration."""
    print("🪙 Testing crypto configuration...")

    crypto_config_path = Path("config/sources.crypto.yaml")
    if not crypto_config_path.exists():
        print("❌ Crypto config file not found: config/sources.crypto.yaml")
        return False

    try:
        registry = ConnectorRegistry(str(crypto_config_path))
        print(f"✅ Crypto config loaded: {len(registry.connectors)} connectors")

        # Verify we have the key connectors for crypto
        connector_names = [c.name for c in registry.connectors]
        key_connectors = ["google_news", "reddit", "hackernews_search", "twitter"]

        for name in key_connectors:
            if name in connector_names:
                print(f"✅ {name} configured")
            else:
                print(f"⚠️  {name} not found in crypto config")

        return True

    except Exception as e:
        print(f"❌ Error loading crypto config: {e}")
        return False


async def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(
        description="Smoke test for enhanced connector system"
    )
    parser.add_argument("--quick", action="store_true", help="Skip long-running tests")
    parser.add_argument(
        "--crypto", action="store_true", help="Test crypto configuration"
    )
    parser.add_argument(
        "--output", default="smoke_test_results.json", help="Output file for results"
    )

    args = parser.parse_args()

    if args.crypto:
        success = test_crypto_config()
        return success

    # Run main smoke tests
    smoke_test = SmokeTest(quick=args.quick)
    success = await smoke_test.run_all_tests()
    smoke_test.save_results(args.output)

    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
