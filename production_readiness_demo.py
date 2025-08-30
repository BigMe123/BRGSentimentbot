#!/usr/bin/env python3
"""
Demo version of Production Readiness Suite with reduced budgets for quick testing.
"""

import asyncio
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from production_readiness_suite import ProductionReadinessSuite


class DemoProductionSuite(ProductionReadinessSuite):
    """Demo version with shorter timeouts."""

    def _load_config(self, config_path):
        """Override with demo timings."""
        config = super()._load_config(config_path)

        # Reduce all budgets for demo
        config["budgets"] = {
            "canary": 30,  # 30s instead of 60 min
            "functional": 30,  # 30s instead of 5 min
            "incrementality": 20,  # 20s
            "chaos": 30,  # 30s instead of 15 min
            "load_150": 30,  # 30s instead of 5 min
            "load_500": 60,  # 60s instead of 15 min
            "soak": 60,  # 60s simulated (was 24h)
        }

        # Use smaller corpus for demo
        self.demo_mode = True

        return config

    def _build_production_corpus(self):
        """Build smaller corpus for demo."""
        corpus = super()._build_production_corpus()

        # Limit to 10 feeds for demo
        corpus["feeds"] = corpus["feeds"][:10]

        # Reduce fixtures
        corpus["controlled_fixtures"]["duplicates"] = corpus["controlled_fixtures"][
            "duplicates"
        ][:3]
        corpus["controlled_fixtures"]["stale_items"] = corpus["controlled_fixtures"][
            "stale_items"
        ][:3]

        return corpus

    async def phase6_soak(self):
        """Override soak test for demo - just 3 iterations."""
        import statistics
        from datetime import datetime, timezone
        from sentiment_bot.fetcher_optimized import fetch_with_budget

        logger.info("\n" + "=" * 80)
        logger.info("📍 PHASE 6: SOAK TEST (Demo - 3 iterations)")
        logger.info("=" * 80)

        phase_start = datetime.now(timezone.utc)

        # Demo: Just 3 quick iterations
        iterations = 3
        iteration_budget = 10  # 10 seconds per iteration
        memory_samples = []
        success_rates = []

        for i in range(iterations):
            logger.info(f"Soak iteration {i+1}/{iterations}")

            snapshot_before = self.resource_monitor.capture()

            result = await fetch_with_budget(
                feed_urls=self.corpus["feeds"][:5],  # Just 5 feeds
                budget_seconds=iteration_budget,
            )

            snapshot_after = self.resource_monitor.capture()

            memory_samples.append(snapshot_after.memory_mb)
            success_rates.append(result.metrics.get("fetch_success_rate", 0))

            await asyncio.sleep(1)  # Brief pause

        memory_trend = (
            self._analyze_trend(memory_samples) if len(memory_samples) > 1 else 0
        )
        success_stability = (
            statistics.stdev(success_rates) if len(success_rates) > 1 else 0
        )

        acceptance = {
            "memory_stable": memory_trend < 0.10,  # Relaxed for demo
            "success_rate_stable": success_stability < 0.20,  # Relaxed
            "no_crashes": True,
            "avg_success_ge_50": statistics.mean(success_rates) >= 0.50,  # Relaxed
            "no_resource_exhaustion": max(memory_samples) < 2000,
        }

        soak_report = {
            "iterations": iterations,
            "memory_samples_mb": memory_samples,
            "memory_trend": memory_trend,
            "success_rates": success_rates,
            "success_stability": success_stability,
            "avg_success_rate": statistics.mean(success_rates) if success_rates else 0,
            "demo_mode": True,
        }

        self._save_artifact("phase6_soak_report.json", soak_report)

        phase_end = datetime.now(timezone.utc)

        return {
            "phase": "soak",
            "status": "pass" if all(acceptance.values()) else "fail",
            "duration_seconds": (phase_end - phase_start).total_seconds(),
            "metrics": soak_report,
            "acceptance": acceptance,
        }


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S UTC",
)
logging.Formatter.converter = time.gmtime
logger = logging.getLogger(__name__)


async def main():
    """Run demo suite."""
    print("=" * 80)
    print("PRODUCTION READINESS SUITE - DEMO MODE")
    print("Running with reduced budgets for quick demonstration")
    print("=" * 80)

    suite = DemoProductionSuite()

    # Run just first 3 phases for demo
    results = []

    try:
        print("\n▶️ Running Phase 1: Canary (30s budget)...")
        phase1 = await suite.phase1_canary()
        results.append(phase1)
        print(f"   Status: {phase1['status'].upper()}")

        print("\n▶️ Running Phase 2: Functional (30s budget)...")
        phase2 = await suite.phase2_functional()
        results.append(phase2)
        print(f"   Status: {phase2['status'].upper()}")

        print("\n▶️ Running Phase 3: Incrementality (20s budget)...")
        phase3 = await suite.phase3_incrementality()
        results.append(phase3)
        print(f"   Status: {phase3['status'].upper()}")

        # Summary
        passed = sum(1 for r in results if r["status"] == "pass")
        failed = sum(1 for r in results if r["status"] == "fail")

        print("\n" + "=" * 80)
        print("DEMO RESULTS")
        print("=" * 80)
        print(f"Phases Run: {len(results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")

        for result in results:
            emoji = "✅" if result["status"] == "pass" else "❌"
            print(f"\n{emoji} Phase {result['phase'].upper()}")
            if "acceptance" in result:
                for key, value in result["acceptance"].items():
                    status = "✓" if value else "✗"
                    print(f"    {status} {key}")

        # Save demo report
        output_dir = Path("prod_test_artifacts")
        output_dir.mkdir(exist_ok=True)

        demo_report = {
            "mode": "DEMO",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phases_run": len(results),
            "phases_passed": passed,
            "phases_failed": failed,
            "results": results,
        }

        with open(output_dir / "demo_report.json", "w") as f:
            json.dump(demo_report, f, indent=2, default=str)

        print(f"\n📁 Demo report saved to {output_dir / 'demo_report.json'}")

        if failed == 0:
            print("\n✅ DEMO PASSED - All phases successful!")
            return 0
        else:
            print(f"\n⚠️ DEMO COMPLETED - {failed} phases failed")
            return 1

    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()
        return 2


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
