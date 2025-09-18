#!/usr/bin/env python3
"""
Fixed Integrated System Testing Framework
========================================

Comprehensive testing using standardized interfaces to avoid API mismatches.
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

# Import standardized interfaces
from sentiment_bot.interfaces import (
    create_sentiment_analyzer,
    create_source_selector,
    create_article_scraper,
    create_economic_predictor,
    AnalysisMode,
    Article,
    SentimentResult,
    Source
)

# Import remaining components
from sentiment_bot.realtime_market_processor import RealTimeMarketProcessor, MarketTick, TickType
from sentiment_bot.consumer_confidence_analyzer import ConsumerConfidenceAnalyzer
from sentiment_bot.bridge_dfm_models import IntegratedNowcastingSystem
from sentiment_bot.connectors.twitter_improved import TwitterImproved

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FixedIntegratedSystemTest:
    """Fixed integrated system test using standardized interfaces."""

    def __init__(self):
        self.components = {}
        self.results = {}
        self.start_time = datetime.now()
        self.test_data = {}

    async def initialize_components(self) -> bool:
        """Initialize all system components with standardized interfaces."""
        print("🏭 Initializing System Components (Fixed)")
        print("=" * 50)

        try:
            # Standardized components
            print("   ✓ Sentiment Analyzer...", end="")
            self.components['sentiment'] = create_sentiment_analyzer()
            print(" OK")

            print("   ✓ Source Selector...", end="")
            self.components['source_selector'] = create_source_selector()
            print(" OK")

            print("   ✓ Article Scraper...", end="")
            self.components['scraper'] = create_article_scraper()
            print(" OK")

            print("   ✓ Economic Predictor...", end="")
            self.components['predictor'] = create_economic_predictor()
            print(" OK")

            # Direct components (already working)
            print("   ✓ Market Processor...", end="")
            self.components['market_processor'] = RealTimeMarketProcessor()
            await self.components['market_processor'].start()
            print(" OK")

            print("   ✓ Confidence Analyzer...", end="")
            self.components['confidence_analyzer'] = ConsumerConfidenceAnalyzer()
            print(" OK")

            print("   ✓ Nowcasting System...", end="")
            self.components['nowcasting'] = IntegratedNowcastingSystem()
            print(" OK")

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

    async def test_standardized_sentiment(self) -> bool:
        """Test standardized sentiment analysis interface."""
        print("\n🧠 Testing Standardized Sentiment Analysis")
        print("=" * 50)

        try:
            test_texts = [
                "The economy is performing very well with strong growth.",
                "Economic outlook appears negative with declining indicators.",
                "Neutral economic conditions continue.",
                ""  # Empty text test
            ]

            sentiments = []
            for i, text in enumerate(test_texts):
                print(f"   Analyzing text {i+1}...")
                result = self.components['sentiment'].analyze(text)
                
                print(f"     Score: {result.score:.3f}")
                print(f"     Label: {result.label}")
                print(f"     Confidence: {result.confidence:.3f}")
                
                sentiments.append(result)

            # Test legacy compatibility
            legacy_result = self.components['sentiment'].analyze_sentiment(test_texts[0])
            print(f"\n   Legacy compatibility: {legacy_result}")

            self.test_data['sentiment'] = {
                'texts_analyzed': len(test_texts),
                'avg_confidence': np.mean([s.confidence for s in sentiments]),
                'legacy_working': 'compound' in legacy_result
            }

            return True

        except Exception as e:
            print(f"   ❌ Sentiment test failed: {e}")
            return False

    async def test_standardized_source_selection(self) -> bool:
        """Test standardized source selection interface."""
        print("\n📋 Testing Standardized Source Selection")
        print("=" * 50)

        try:
            # Test different selection modes
            modes = [AnalysisMode.ECONOMIC, AnalysisMode.SMART, AnalysisMode.MARKET]
            
            for mode in modes:
                print(f"\n   Testing {mode.value} mode...")
                sources = self.components['source_selector'].select_sources(
                    mode=mode,
                    region="americas",
                    max_sources=5
                )
                
                print(f"     Selected {len(sources)} sources")
                if sources:
                    sample = sources[0]
                    print(f"     Sample: {sample.name} ({sample.country})")
                    print(f"     URLs: {len(sample.rss_endpoints)}")

            self.test_data['source_selection'] = {
                'modes_tested': len(modes),
                'total_sources': sum(len(self.components['source_selector'].select_sources(
                    mode=mode, max_sources=10)) for mode in modes)
            }

            return True

        except Exception as e:
            print(f"   ❌ Source selection test failed: {e}")
            return False

    async def test_standardized_scraping(self) -> bool:
        """Test standardized scraping interface."""
        print("\n🔍 Testing Standardized Article Scraping")
        print("=" * 50)

        try:
            # Get sources
            sources = self.components['source_selector'].select_sources(
                mode=AnalysisMode.ECONOMIC,
                region="americas",
                max_sources=2
            )
            
            if not sources:
                print("   No sources available for testing")
                return True

            print(f"   Scraping from {len(sources)} sources...")
            
            articles = []
            async for article in self.components['scraper'].fetch_articles(
                sources, max_per_source=2
            ):
                articles.append(article)
                if len(articles) >= 3:  # Limit for testing
                    break

            print(f"   Fetched {len(articles)} articles")
            
            if articles:
                sample = articles[0]
                print(f"   Sample: {sample.title[:50]}...")
                print(f"   Source: {sample.source}")
                print(f"   Length: {len(sample.text)} chars")

            self.test_data['scraping'] = {
                'sources_used': len(sources),
                'articles_fetched': len(articles),
                'avg_length': np.mean([len(a.text) for a in articles]) if articles else 0
            }

            return True

        except Exception as e:
            print(f"   ❌ Scraping test failed: {e}")
            return False

    async def test_standardized_prediction(self) -> bool:
        """Test standardized economic prediction interface."""
        print("\n📈 Testing Standardized Economic Prediction")
        print("=" * 50)

        try:
            # Create test articles
            test_articles = [
                Article(
                    title="Strong Economic Growth Expected",
                    text="The economy shows robust growth with positive indicators across sectors.",
                    url="https://example.com/1",
                    sentiment_score=0.7,
                    country="USA"
                ),
                Article(
                    title="Market Concerns Grow",
                    text="Economic indicators suggest potential slowdown in coming quarters.",
                    url="https://example.com/2",
                    sentiment_score=-0.3,
                    country="USA"
                )
            ]

            print(f"   Predicting from {len(test_articles)} articles...")
            
            prediction = self.components['predictor'].predict(
                articles=test_articles,
                target="gdp",
                horizon="1_quarter"
            )

            print(f"   GDP Forecast: {prediction.value:.2f}%")
            print(f"   Confidence: {prediction.confidence:.2f}")
            print(f"   CI: [{prediction.confidence_interval[0]:.2f}, {prediction.confidence_interval[1]:.2f}]")
            print(f"   Methodology: {prediction.methodology}")
            
            if prediction.drivers:
                print(f"   Drivers: {prediction.drivers[:3]}")

            # Test legacy compatibility
            legacy_result = self.components['predictor'].predict_with_transparency(
                sentiment_score=0.5,
                topic_factors={'economy': 0.6},
                context_text="Test economic context"
            )
            print(f"\n   Legacy compatibility: {legacy_result.get('gdp_forecast', 'N/A')}")

            self.test_data['prediction'] = {
                'forecast_value': prediction.value,
                'confidence': prediction.confidence,
                'legacy_working': 'gdp_forecast' in legacy_result
            }

            return True

        except Exception as e:
            print(f"   ❌ Prediction test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def test_end_to_end_pipeline(self) -> bool:
        """Test complete end-to-end pipeline with standardized interfaces."""
        print("\n🔗 Testing End-to-End Pipeline (Standardized)")
        print("=" * 50)

        try:
            # 1. Select sources
            print("\n1. Source Selection:")
            sources = self.components['source_selector'].select_sources(
                mode=AnalysisMode.ECONOMIC,
                region="americas",
                max_sources=3
            )
            print(f"   Selected {len(sources)} sources")

            # 2. Fetch articles (simulated with test data)
            print("\n2. Article Processing:")
            test_articles = [
                Article(
                    title="Economic Growth Accelerates",
                    text="The latest economic data shows accelerating growth with strong consumer spending and business investment.",
                    url="https://test.com/1",
                    source="TestSource",
                    country="USA"
                ),
                Article(
                    title="Market Volatility Increases",
                    text="Recent market volatility reflects uncertainty about future economic conditions and policy changes.",
                    url="https://test.com/2",
                    source="TestSource",
                    country="USA"
                )
            ]
            print(f"   Processing {len(test_articles)} articles")

            # 3. Analyze sentiment
            print("\n3. Sentiment Analysis:")
            for article in test_articles:
                sentiment = self.components['sentiment'].analyze(article.text)
                article.sentiment_score = sentiment.score
                print(f"   {article.title[:30]}... -> {sentiment.score:.2f} ({sentiment.label})")

            # 4. Generate prediction
            print("\n4. Economic Prediction:")
            prediction = self.components['predictor'].predict(
                articles=test_articles,
                target="gdp",
                horizon="1_quarter"
            )
            print(f"   GDP Forecast: {prediction.value:.2f}%")
            print(f"   Confidence: {prediction.confidence:.2f}")

            # 5. Process through market processor
            print("\n5. Market Processing:")
            for article in test_articles:
                tick = MarketTick(
                    timestamp=datetime.now(),
                    tick_type=TickType.SENTIMENT,
                    symbol="USA",
                    data={'sentiment': article.sentiment_score},
                    source="pipeline_test"
                )
                await self.components['market_processor'].submit_tick(tick)

            # Wait for processing
            await asyncio.sleep(1)
            stats = self.components['market_processor'].get_stats()
            print(f"   Processed {stats['ticks_processed']} ticks")

            # 6. Consumer confidence analysis
            print("\n6. Consumer Confidence:")
            sentiment_data = {
                'overall': np.mean([a.sentiment_score for a in test_articles]),
                'economic': prediction.value / 100  # Normalize
            }
            
            confidence = self.components['confidence_analyzer'].analyze(
                sentiment_data
            )
            print(f"   Confidence Index: {confidence.overall_index:.1f}")
            print(f"   Trend: {confidence.trend}")

            self.test_data['pipeline'] = {
                'sources': len(sources),
                'articles': len(test_articles),
                'prediction_value': prediction.value,
                'confidence_index': confidence.overall_index,
                'ticks_processed': stats['ticks_processed']
            }

            return True

        except Exception as e:
            print(f"   ❌ Pipeline test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def test_performance(self) -> bool:
        """Test system performance with standardized interfaces."""
        print("\n⏱️ Testing Performance (Standardized)")
        print("=" * 50)

        try:
            # Test sentiment analysis speed
            print("\n1. Sentiment Analysis Performance:")
            test_texts = ["Economic growth continues to accelerate." * 10] * 100
            
            start_time = time.time()
            for text in test_texts:
                _ = self.components['sentiment'].analyze(text)
            elapsed = time.time() - start_time
            
            rate = len(test_texts) / elapsed
            print(f"   Processed {len(test_texts)} texts in {elapsed:.2f}s")
            print(f"   Rate: {rate:.1f} texts/second")

            # Test prediction performance
            print("\n2. Prediction Performance:")
            test_article = Article(
                title="Test Article",
                text="Economic indicators show positive trends.",
                url="test",
                sentiment_score=0.5
            )
            
            start_time = time.time()
            for _ in range(10):
                _ = self.components['predictor'].predict([test_article])
            elapsed = time.time() - start_time
            
            pred_rate = 10 / elapsed
            print(f"   Processed 10 predictions in {elapsed:.2f}s")
            print(f"   Rate: {pred_rate:.1f} predictions/second")

            self.test_data['performance'] = {
                'sentiment_rate': rate,
                'prediction_rate': pred_rate
            }

            return rate > 10 and pred_rate > 1  # Reasonable thresholds

        except Exception as e:
            print(f"   ❌ Performance test failed: {e}")
            return False

    async def cleanup(self):
        """Clean up resources."""
        print("\n🧹 Cleaning up...")
        if 'market_processor' in self.components:
            await self.components['market_processor'].stop()
        print("   Cleanup complete")

    async def run_all_tests(self) -> bool:
        """Run all standardized tests."""
        print("🧪 Fixed BSG Integrated System Test Suite")
        print("=" * 60)
        print(f"Started at: {self.start_time.isoformat()}")
        print()

        # Initialize
        if not await self.initialize_components():
            return False

        # Run tests
        tests = [
            ("Standardized Sentiment", self.test_standardized_sentiment),
            ("Standardized Source Selection", self.test_standardized_source_selection),
            ("Standardized Scraping", self.test_standardized_scraping),
            ("Standardized Prediction", self.test_standardized_prediction),
            ("End-to-End Pipeline", self.test_end_to_end_pipeline),
            ("Performance", self.test_performance)
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
        elapsed = (datetime.now() - self.start_time).seconds
        passed = sum(self.results.values())
        total = len(self.results)

        report = {
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': elapsed,
            'tests_passed': passed,
            'tests_total': total,
            'test_results': self.results,
            'test_data': self.test_data,
            'overall_status': 'HEALTHY' if passed == total else 'DEGRADED' if passed >= total * 0.7 else 'CRITICAL'
        }

        # Summary
        print("\n" + "=" * 60)
        print("📋 FIXED INTEGRATION TEST SUMMARY")
        print("=" * 60)

        for test_name, success in self.results.items():
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"   {test_name}: {status}")

        print(f"\nOverall: {passed}/{total} tests passed")
        print(f"System Status: {report['overall_status']}")

        # Save report
        report_path = Path("integration_test_report_fixed.json")
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to: {report_path}")

        # Cleanup
        await self.cleanup()

        if report['overall_status'] == 'HEALTHY':
            print("\n🎉 System is HEALTHY with standardized interfaces!")
            return True
        elif report['overall_status'] == 'DEGRADED':
            print("\n⚠️ System is DEGRADED but functional.")
            return True
        else:
            print("\n❌ System needs attention.")
            return False


async def main():
    """Main entry point."""
    tester = FixedIntegratedSystemTest()
    success = await tester.run_all_tests()
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)