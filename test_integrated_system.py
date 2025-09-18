#!/usr/bin/env python3
"""
Integrated System Testing Framework
===================================

Comprehensive testing of the entire BSG sentiment analysis system.
This tests all components working together in production-like scenarios.

Author: BSG Team
Created: 2025-01-15
"""

import asyncio
import logging
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path
import numpy as np
import pandas as pd

# Import all major components
from sentiment_bot.unified_source_selector import UnifiedSourceSelector
from sentiment_bot.enhanced_stable_scraper import EnhancedStableScraper
from sentiment_bot.realtime_market_processor import RealTimeMarketProcessor, MarketTick, TickType
from sentiment_bot.consumer_confidence_analyzer import ConsumerConfidenceAnalyzer
from sentiment_bot.bridge_dfm_models import IntegratedNowcastingSystem
from sentiment_bot.analyzers.sentiment_ensemble import SentimentEnsemble
from sentiment_bot.production_economic_predictor import ProductionEconomicPredictor
from sentiment_bot.connectors.twitter_improved import TwitterImproved

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IntegratedSystemTest:
    """Main integrated system test framework."""

    def __init__(self):
        self.components = {}
        self.results = {}
        self.start_time = datetime.now()
        self.test_data = {}

    async def initialize_components(self) -> bool:
        """Initialize all system components."""
        print("🏭 Initializing System Components")
        print("=" * 50)

        try:
            # Source selector
            print("   ✓ Source Selector...", end="")
            self.components['source_selector'] = UnifiedSourceSelector()
            print(" OK")

            # Scraper
            print("   ✓ Enhanced Scraper...", end="")
            self.components['scraper'] = EnhancedStableScraper(
                rate_limit=10.0,  # 10 requests per second
                max_retries=3
            )
            print(" OK")

            # Market processor
            print("   ✓ Market Processor...", end="")
            self.components['market_processor'] = RealTimeMarketProcessor()
            await self.components['market_processor'].start()
            print(" OK")

            # Confidence analyzer
            print("   ✓ Confidence Analyzer...", end="")
            self.components['confidence_analyzer'] = ConsumerConfidenceAnalyzer()
            print(" OK")

            # Nowcasting system
            print("   ✓ Nowcasting System...", end="")
            self.components['nowcasting'] = IntegratedNowcastingSystem()
            print(" OK")

            # Sentiment analyzer
            print("   ✓ Sentiment Analyzer...", end="")
            self.components['sentiment'] = SentimentEnsemble()
            print(" OK")

            # Economic predictor
            print("   ✓ Economic Predictor...", end="")
            self.components['predictor'] = ProductionEconomicPredictor()
            print(" OK")

            # Twitter connector (mock)
            print("   ✓ Social Media Connector...", end="")
            self.components['twitter'] = TwitterImproved(use_mock=True)
            print(" OK")

            print("\n✅ All components initialized successfully")
            return True

        except Exception as e:
            print(f"\n❌ Initialization failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def test_data_pipeline(self) -> bool:
        """Test end-to-end data pipeline."""
        print("\n🔗 Testing Data Pipeline")
        print("=" * 50)

        try:
            # 1. Select sources
            print("\n1. Source Selection:")
            sources = self.components['source_selector'].select_for_mode(
                mode="ECONOMIC",
                region="Europe",
                max_sources=5
            )
            print(f"   Selected {len(sources)} sources")
            if sources:
                print(f"   Sample: {sources[0].get('name', 'Unknown')}")

            # 2. Fetch articles
            print("\n2. Article Fetching:")
            articles = []
            async for article in self.components['scraper'].fetch_batch(
                sources[:2],  # Just 2 for speed
                max_per_source=3
            ):
                articles.append(article)

            print(f"   Fetched {len(articles)} articles")

            # 3. Analyze sentiment
            print("\n3. Sentiment Analysis:")
            sentiments = []
            for article in articles[:5]:  # Analyze first 5
                text = article.get('text', article.get('title', ''))
                if text:
                    sentiment_result = self.components['sentiment'].score_article(text)
                    sentiment = {
                        'compound': sentiment_result.score,
                        'label': sentiment_result.label
                    }
                    sentiments.append(sentiment)

            if sentiments:
                avg_sentiment = np.mean([s.get('compound', 0) for s in sentiments])
                print(f"   Analyzed {len(sentiments)} articles")
                print(f"   Average sentiment: {avg_sentiment:.3f}")

            # 4. Submit to market processor
            print("\n4. Market Processing:")
            for i, sentiment in enumerate(sentiments):
                tick = MarketTick(
                    timestamp=datetime.now(),
                    tick_type=TickType.SENTIMENT,
                    symbol="TEST",
                    data={'sentiment': sentiment.get('compound', 0)},
                    source="pipeline_test"
                )
                await self.components['market_processor'].submit_tick(tick)

            await asyncio.sleep(1)  # Let processor work
            stats = self.components['market_processor'].get_stats()
            print(f"   Processed {stats['ticks_processed']} ticks")

            self.test_data['pipeline'] = {
                'sources': len(sources),
                'articles': len(articles),
                'sentiments': len(sentiments),
                'ticks': stats['ticks_processed']
            }

            return len(articles) > 0 and len(sentiments) > 0

        except Exception as e:
            print(f"   ❌ Pipeline test failed: {e}")
            return False

    async def test_economic_analysis(self) -> bool:
        """Test economic analysis components."""
        print("\n📊 Testing Economic Analysis")
        print("=" * 50)

        try:
            # Generate test data
            sentiment_data = {
                'overall': 0.3,
                'economic': 0.4,
                'employment': 0.2,
                'inflation': -0.1
            }

            economic_data = {
                'gdp_growth': 2.5,
                'unemployment': 4.0,
                'inflation': 2.2
            }

            # 1. Consumer confidence
            print("\n1. Consumer Confidence:")
            confidence = self.components['confidence_analyzer'].analyze(
                sentiment_data,
                economic_data
            )
            print(f"   Overall Index: {confidence.overall_index:.1f}")
            print(f"   Trend: {confidence.trend}")

            # 2. Economic prediction
            print("\n2. Economic Prediction:")
            articles = [
                {
                    'text': 'Economic growth remains strong',
                    'sentiment': {'compound': 0.5},
                    'country': 'USA'
                }
            ]

            # Extract sentiment for prediction
            sentiment_score = 0.5  # Default
            if articles:
                sent_result = self.components['sentiment'].score_article(articles[0]['text'])
                sentiment_score = sent_result.score

            prediction = self.components['predictor'].predict_with_transparency(
                sentiment_score=sentiment_score,
                topic_factors={'economy': 0.5},
                context_text=articles[0]['text'] if articles else ""
            )

            if prediction:
                print(f"   GDP Forecast: {prediction.get('gdp_forecast', 'N/A')}")
                print(f"   Confidence: {prediction.get('confidence', 'N/A')}")

            # 3. Nowcasting
            print("\n3. Nowcasting:")
            # Generate synthetic data for nowcasting
            dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
            sentiment_df = pd.DataFrame({
                'sentiment': np.random.normal(0.2, 0.1, 30)
            }, index=dates)

            nowcast = self.components['nowcasting'].nowcast_all(
                sentiment_df,
                pd.DataFrame(),  # Empty monthly data
                pd.DataFrame()   # Empty financial data
            )

            print(f"   Nowcasts generated: {len(nowcast.get('forecasts', {}))}")

            self.test_data['economic'] = {
                'confidence': confidence.overall_index,
                'prediction': prediction is not None,
                'nowcasts': len(nowcast.get('forecasts', {}))
            }

            return confidence.overall_index > 0

        except Exception as e:
            print(f"   ❌ Economic analysis test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def test_social_media_integration(self) -> bool:
        """Test social media integration."""
        print("\n🐦 Testing Social Media Integration")
        print("=" * 50)

        try:
            tweets = []
            print("   Fetching mock tweets...")

            async for tweet in self.components['twitter'].fetch():
                tweets.append(tweet)
                if len(tweets) >= 5:
                    break

            print(f"   Fetched {len(tweets)} tweets")

            # Analyze sentiment
            sentiments = []
            for tweet in tweets:
                text = tweet.get('text', '')
                if text:
                    sentiment_result = self.components['sentiment'].score_article(text)
                    sentiment = {
                        'compound': sentiment_result.score,
                        'label': sentiment_result.label
                    }
                    sentiments.append(sentiment.get('compound', 0))

            if sentiments:
                avg_sentiment = np.mean(sentiments)
                print(f"   Average sentiment: {avg_sentiment:.3f}")

            self.test_data['social'] = {
                'tweets': len(tweets),
                'sentiments': len(sentiments)
            }

            return len(tweets) > 0

        except Exception as e:
            print(f"   ❌ Social media test failed: {e}")
            return False

    async def test_performance(self) -> bool:
        """Test system performance."""
        print("\n⏱️ Testing System Performance")
        print("=" * 50)

        try:
            # Test sentiment analysis speed
            print("\n1. Sentiment Analysis Speed:")
            texts = ["This is a test sentence." * 10 for _ in range(100)]
            start = time.time()

            for text in texts:
                _ = self.components['sentiment'].score_article(text)

            elapsed = time.time() - start
            rate = len(texts) / elapsed
            print(f"   Processed {len(texts)} texts in {elapsed:.2f}s")
            print(f"   Rate: {rate:.1f} texts/second")

            # Test market processor throughput
            print("\n2. Market Processor Throughput:")
            start = time.time()
            submitted = 0

            for i in range(500):
                tick = MarketTick(
                    timestamp=datetime.now(),
                    tick_type=TickType.SENTIMENT,
                    symbol="PERF",
                    data={'value': i},
                    source="perf_test"
                )
                if await self.components['market_processor'].submit_tick(tick):
                    submitted += 1

            elapsed = time.time() - start
            rate = submitted / elapsed
            print(f"   Submitted {submitted} ticks in {elapsed:.2f}s")
            print(f"   Rate: {rate:.1f} ticks/second")

            self.test_data['performance'] = {
                'sentiment_rate': rate,
                'market_rate': rate
            }

            return rate > 10  # At least 10 ticks/second

        except Exception as e:
            print(f"   ❌ Performance test failed: {e}")
            return False

    async def test_error_handling(self) -> bool:
        """Test error handling and resilience."""
        print("\n🛡️ Testing Error Handling")
        print("=" * 50)

        try:
            # Test with invalid data
            print("\n1. Invalid Data Handling:")

            # Empty text
            sentiment_result = self.components['sentiment'].score_article("")
            sentiment = {'label': sentiment_result.label}
            print(f"   Empty text: {sentiment.get('label', 'handled')}")

            # Invalid source
            invalid_source = {'url': 'http://invalid.test'}
            error_count = 0
            async for _ in self.components['scraper'].fetch_batch(
                [invalid_source],
                max_per_source=1
            ):
                pass
            print(f"   Invalid source: handled gracefully")

            # Null economic data
            confidence = self.components['confidence_analyzer'].analyze(
                {},  # Empty sentiment
                None  # No economic data
            )
            print(f"   Null data: confidence={confidence.overall_index:.1f}")

            print("\n✅ All error cases handled gracefully")
            return True

        except Exception as e:
            print(f"   ❌ Error handling test failed: {e}")
            return False

    async def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report."""
        elapsed = (datetime.now() - self.start_time).seconds

        report = {
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': elapsed,
            'components_tested': len(self.components),
            'tests_passed': sum(self.results.values()),
            'tests_total': len(self.results),
            'test_results': self.results,
            'test_data': self.test_data,
            'component_status': {
                name: 'initialized' for name in self.components.keys()
            }
        }

        # Calculate overall health
        pass_rate = report['tests_passed'] / max(report['tests_total'], 1)
        if pass_rate >= 0.9:
            report['overall_status'] = 'HEALTHY'
        elif pass_rate >= 0.7:
            report['overall_status'] = 'DEGRADED'
        else:
            report['overall_status'] = 'CRITICAL'

        return report

    async def cleanup(self):
        """Clean up resources."""
        print("\n🧹 Cleaning up...")

        if 'market_processor' in self.components:
            await self.components['market_processor'].stop()

        print("   Cleanup complete")

    async def run_all_tests(self) -> bool:
        """Run complete integration test suite."""
        print("🧪 BSG Integrated System Test Suite")
        print("=" * 60)
        print(f"Started at: {self.start_time.isoformat()}")
        print()

        # Initialize
        if not await self.initialize_components():
            return False

        # Run tests
        tests = [
            ("Data Pipeline", self.test_data_pipeline),
            ("Economic Analysis", self.test_economic_analysis),
            ("Social Media", self.test_social_media_integration),
            ("Performance", self.test_performance),
            ("Error Handling", self.test_error_handling)
        ]

        for test_name, test_func in tests:
            try:
                print(f"\n🔍 Running: {test_name}")
                success = await test_func()
                self.results[test_name] = success
                print(f"\nResult: {'✅ PASS' if success else '❌ FAIL'}")
            except Exception as e:
                print(f"❌ Critical error in {test_name}: {e}")
                self.results[test_name] = False

        # Generate report
        report = await self.generate_report()

        # Summary
        print("\n" + "=" * 60)
        print("📋 INTEGRATION TEST SUMMARY")
        print("=" * 60)

        for test_name, success in self.results.items():
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"   {test_name}: {status}")

        print(f"\nOverall: {report['tests_passed']}/{report['tests_total']} tests passed")
        print(f"System Status: {report['overall_status']}")

        # Save report
        report_path = Path("integration_test_report.json")
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to: {report_path}")

        # Cleanup
        await self.cleanup()

        if report['overall_status'] == 'HEALTHY':
            print("\n🎉 System is HEALTHY and ready for production!")
            return True
        elif report['overall_status'] == 'DEGRADED':
            print("\n⚠️ System is DEGRADED but functional.")
            return True
        else:
            print("\n❌ System is CRITICAL - needs attention.")
            return False


async def main():
    """Main entry point."""
    tester = IntegratedSystemTest()
    success = await tester.run_all_tests()
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)