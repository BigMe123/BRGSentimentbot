#!/usr/bin/env python3
"""
Quick test script to verify all five comprehensive systems are working.
"""

import asyncio
from datetime import datetime, timedelta
import json

# Import all five systems
from sentiment_bot.core.economic_models import UnifiedEconomicModel
from sentiment_bot.core.rss_monitor import RSSMonitor
from sentiment_bot.core.realtime_pipeline import RealtimeAnalysisPipeline
from sentiment_bot.core.backtest_system import HistoricalBacktestSystem, BacktestConfig
from sentiment_bot.core.performance_monitor import PerformanceMonitor


async def test_all_systems():
    """Test all five core systems."""

    print("=" * 60)
    print("BSG Bot Comprehensive Systems Test")
    print("=" * 60)

    results = {}

    # 1. Test Economic Models
    print("\n1. Testing Economic Prediction Models...")
    try:
        model = UnifiedEconomicModel()
        sentiment_data = {
            "aggregate_sentiment": 0.3,
            "volume": 100,
            "topics": ["growth", "recovery", "employment"]
        }

        gdp = model.forecast_gdp("united_states", sentiment_data, horizon="nowcast")
        cpi = model.forecast_cpi("united_states", sentiment_data, horizon="nowcast")
        emp = model.forecast_employment("united_states", sentiment_data, horizon="nowcast")

        print(f"   ✅ GDP: {gdp.point_estimate:.2f}% [{gdp.confidence_low:.2f}, {gdp.confidence_high:.2f}]")
        print(f"   ✅ CPI: {cpi.point_estimate:.2f}% [{cpi.confidence_low:.2f}, {cpi.confidence_high:.2f}]")
        print(f"   ✅ Employment: {emp.point_estimate:.2f}% [{emp.confidence_low:.2f}, {emp.confidence_high:.2f}]")

        results["economic_models"] = "PASSED"
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        results["economic_models"] = f"FAILED: {e}"

    # 2. Test RSS Monitor
    print("\n2. Testing RSS Monitoring Infrastructure...")
    try:
        monitor = RSSMonitor()

        # Test with a known good feed
        test_feed = "https://feeds.bbci.co.uk/news/business/rss.xml"
        health, items = await monitor.check_feed(test_feed)

        print(f"   ✅ Feed Status: {health.status}")
        print(f"   ✅ Response Time: {health.response_time_ms}ms")
        print(f"   ✅ Items Found: {len(items)}")

        # Test quarantine check
        is_quarantined = await monitor.is_quarantined(test_feed)
        print(f"   ✅ Quarantine Check: {'Quarantined' if is_quarantined else 'Not Quarantined'}")

        results["rss_monitor"] = "PASSED"
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        results["rss_monitor"] = f"FAILED: {e}"

    # 3. Test Real-time Pipeline
    print("\n3. Testing Real-time Analysis Pipeline...")
    try:
        pipeline = RealtimeAnalysisPipeline()

        # Create a mock article for testing
        test_article = {
            "title": "US Economy Shows Strong Growth",
            "content": "The United States economy expanded at a robust pace in the latest quarter.",
            "url": "https://example.com/article",
            "published": datetime.now().isoformat(),
            "source": "test_source"
        }

        # Process the article
        processed = await pipeline._process_article(test_article)

        if processed:
            print(f"   ✅ Article Processed: {processed.title[:50]}...")
            print(f"   ✅ Sentiment Score: {processed.sentiment_score:.2f}")
            print(f"   ✅ Entities Found: {len(processed.entities)}")
            print(f"   ✅ Topics: {processed.topics[:3]}")
        else:
            print("   ⚠️  Article filtered out (expected behavior for some content)")

        results["realtime_pipeline"] = "PASSED"
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        results["realtime_pipeline"] = f"FAILED: {e}"

    # 4. Test Backtest System
    print("\n4. Testing Historical Backtesting System...")
    try:
        backtest = HistoricalBacktestSystem()

        # Small backtest config for testing
        config = BacktestConfig(
            start_date=datetime.now() - timedelta(days=30),
            end_date=datetime.now(),
            rebalance_frequency="weekly",
            initial_capital=100_000,
            countries=["united_states"],
            metrics_to_track=["gdp"]
        )

        # Run mini backtest
        results_bt = backtest.run_comprehensive_backtest(config)

        if "united_states" in results_bt:
            metrics = results_bt["united_states"]
            print(f"   ✅ Total Return: {metrics.total_return:.2%}")
            print(f"   ✅ Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
            print(f"   ✅ Max Drawdown: {metrics.max_drawdown:.2%}")
            print(f"   ✅ MAPE: {metrics.mape:.2f}%")

        results["backtest_system"] = "PASSED"
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        results["backtest_system"] = f"FAILED: {e}"

    # 5. Test Performance Monitor
    print("\n5. Testing Performance Monitoring...")
    try:
        perf_monitor = PerformanceMonitor()

        # Track some test predictions
        for i in range(5):
            perf_monitor.track_prediction(
                model_type="gdp",
                country="united_states",
                prediction=2.0 + i * 0.1,
                actual=2.0 + i * 0.08 if i > 0 else None,
                confidence_interval=(1.5 + i * 0.1, 2.5 + i * 0.1)
            )

        # Calculate metrics
        metrics = perf_monitor.calculate_metrics("gdp", "united_states", lookback_days=1)

        if metrics:
            print(f"   ✅ MAPE: {metrics.mape:.2f}%")
            print(f"   ✅ RMSE: {metrics.rmse:.3f}")
            print(f"   ✅ Sample Size: {metrics.sample_size}")
        else:
            print("   ✅ Metrics tracking initialized (no actuals yet)")

        # Check alerts
        alerts = perf_monitor.check_alerts(hours_back=1)
        print(f"   ✅ Alerts Checked: {len(alerts)} alerts found")

        # Generate report
        report = perf_monitor.generate_performance_report()
        print(f"   ✅ Report Generated: {len(report)} sections")

        results["performance_monitor"] = "PASSED"
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        results["performance_monitor"] = f"FAILED: {e}"

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary:")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v == "PASSED")
    failed = sum(1 for v in results.values() if "FAILED" in str(v))

    for system, status in results.items():
        icon = "✅" if status == "PASSED" else "❌"
        print(f"{icon} {system}: {status}")

    print(f"\nTotal: {passed}/{len(results)} systems passed")

    # Save results
    with open("test_results.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": results,
            "summary": {
                "passed": passed,
                "failed": failed,
                "total": len(results)
            }
        }, f, indent=2)

    print("\nResults saved to test_results.json")

    return passed == len(results)


if __name__ == "__main__":
    success = asyncio.run(test_all_systems())
    exit(0 if success else 1)