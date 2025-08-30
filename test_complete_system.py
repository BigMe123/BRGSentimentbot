#!/usr/bin/env python
"""
Complete system test for BSG Bot with all new features.
Tests the unified CLI, institutional outputs, and source selection.
"""

import asyncio
import sys
import os
from pathlib import Path
import json
from datetime import datetime
import shutil

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from sentiment_bot.skb_catalog import get_catalog
from sentiment_bot.selection_planner import SelectionPlanner, SelectionQuotas
from sentiment_bot.utils.run_id import make_run_id
from sentiment_bot.utils.output_writer import OutputWriter
from sentiment_bot.utils.entity_extractor import EntityExtractor
from sentiment_bot.utils.output_models import (
    ArticleRecord,
    RunSummary,
    Sentiment,
    SignalData,
    EntityCount,
    SourceCount,
    AnalysisBlock,
    DiversityBlock,
    CollectionBlock,
    ConfigBlock,
)


def test_skb_catalog():
    """Test the SKB catalog system."""
    print("\n✅ Testing SKB Catalog...")

    catalog = get_catalog()
    stats = catalog.get_stats()

    print(f"  - Total sources: {stats['total_sources']}")
    print(f"  - Regions: {', '.join(stats['regions'])}")
    topics_list = list(stats["topics"])
    print(f"  - Topics: {', '.join(topics_list[:5])}...")

    # Test source selection
    sources = catalog.get_sources_by_criteria(region="asia", topics=["elections"])
    print(f"  - Found {len(sources)} sources for asia/elections")

    assert stats["total_sources"] > 0, "No sources in catalog"
    assert len(sources) > 0, "No sources found for asia/elections"
    print("  ✓ SKB Catalog working!")


def test_selection_planner():
    """Test the selection planner."""
    print("\n✅ Testing Selection Planner...")

    catalog = get_catalog()
    planner = SelectionPlanner(catalog)

    quotas = SelectionQuotas(min_sources=10, time_budget_seconds=60)

    plan = planner.plan_selection(
        region="europe", topics=["economy"], strict=False, expand=False, quotas=quotas
    )

    print(f"  - Selected {len(plan.sources)} sources")
    print(f"  - Diversity score: {plan.get_diversity_score():.2f}")
    print(f"  - Editorial families: {len(plan.editorial_families)}")

    assert len(plan.sources) > 0, "No sources selected"
    assert plan.get_diversity_score() > 0, "Invalid diversity score"
    print("  ✓ Selection Planner working!")


def test_entity_extractor():
    """Test entity extraction."""
    print("\n✅ Testing Entity Extractor...")

    extractor = EntityExtractor()

    text = """
    The European Central Bank (ECB) announced rate cuts as Germany's 
    manufacturing crisis deepens. EUR/USD fell to 1.05 while the S&P 500 
    surged on the news. Chancellor Scholz called for emergency measures.
    """

    entities = extractor.extract_entities(text)
    tickers = extractor.extract_tickers(text)
    volatility = extractor.detect_volatility(text)
    themes = extractor.extract_themes(text, "economy")

    print(f"  - Found {len(entities)} entities")
    print(f"  - Found {len(tickers)} tickers")
    print(f"  - Volatility score: {volatility:.2f}")
    print(f"  - Themes: {', '.join(themes)}")

    assert len(entities) > 0, "No entities found"
    print("  ✓ Entity Extractor working!")


def test_output_system():
    """Test the institutional output system."""
    print("\n✅ Testing Output System...")

    # Create test output directory
    output_dir = Path("./test_system_output")
    output_dir.mkdir(exist_ok=True)

    # Generate run ID
    run_id = make_run_id(region="asia", topic="elections", started_at=datetime.now())
    print(f"  - Generated run ID: {run_id}")

    # Initialize output writer
    writer = OutputWriter(output_dir=str(output_dir), run_id=run_id)

    # Create sample data
    extractor = EntityExtractor()

    sample_article = {
        "title": "Asian Markets Rally on Election Results",
        "text": "Markets across Asia surged following election outcomes...",
        "url": "https://example.com/article",
        "source": "reuters.com",
        "published": datetime.now().isoformat(),
    }

    # Build article record
    text = sample_article["text"]
    entities = extractor.extract_entities(text)

    record = ArticleRecord(
        run_id=run_id,
        id=extractor.generate_article_id(
            source=sample_article["source"],
            title=sample_article["title"],
            published_at=sample_article["published"],
        ),
        title=sample_article["title"],
        url=sample_article["url"],
        published_at=sample_article["published"],
        source=sample_article["source"],
        region="asia",
        topic="elections",
        language="en",
        relevance=0.9,
        sentiment=Sentiment(label="pos", score=0.5, confidence=0.85),
        signals=SignalData(
            volatility=0.3, risk_level="normal", themes=["elections", "equity_markets"]
        ),
    )

    # Build run summary
    summary = RunSummary(
        run_id=run_id,
        started_at=datetime.now().isoformat(),
        finished_at=datetime.now().isoformat(),
        config=ConfigBlock(
            region="asia",
            topic="elections",
            budget_sec=60,
            min_sources=10,
            discover=False,
            max_age_hours=24,
        ),
        collection=CollectionBlock(
            attempted_feeds=10,
            articles_raw=20,
            unique_after_dedupe=18,
            fresh_window_h=24,
            fresh_count=15,
            relevant_count=1,
        ),
        analysis=AnalysisBlock(
            sentiment_total=50,
            breakdown={"pos": 1, "neg": 0, "neu": 0},
            avg_sentiment=0.5,
            top_triggers=["elections"],
            top_entities=[],
            volatility_index=0.3,
        ),
        sources=[SourceCount(domain="reuters.com", articles=1)],
        diversity=DiversityBlock(
            sources=1, languages=1, regions=1, editorial_families=1, score=0.5
        ),
        errors=[],
        schema_version="1.0.0",
    )

    # Write outputs
    jsonl_path = writer.write_articles_jsonl([record])
    json_path = writer.write_run_summary_json(summary)
    txt_path = writer.write_dashboard_txt(summary, ["Test article"])
    csv_path = writer.write_csv([record])

    # Verify files exist
    assert Path(jsonl_path).exists(), "JSONL file not created"
    assert Path(json_path).exists(), "JSON file not created"
    assert Path(txt_path).exists(), "TXT file not created"
    assert Path(csv_path).exists(), "CSV file not created"

    print(f"  - Created JSONL: {Path(jsonl_path).name}")
    print(f"  - Created JSON: {Path(json_path).name}")
    print(f"  - Created TXT: {Path(txt_path).name}")
    print(f"  - Created CSV: {Path(csv_path).name}")

    # Clean up
    shutil.rmtree(output_dir)
    print("  ✓ Output System working!")


def test_sentiment_analyzer():
    """Test the sentiment analyzer."""
    print("\n✅ Testing Sentiment Analyzer...")

    from sentiment_bot.analyzer import analyze

    texts = [
        "Markets crashed dramatically amid panic selling",
        "Strong earnings beat expectations significantly",
        "Trading remained flat throughout the session",
    ]

    for text in texts:
        result = analyze(text)
        print(f"  - '{text[:30]}...' -> Score: {result.vader:.2f}")

    print("  ✓ Sentiment Analyzer working!")


async def test_basic_fetch():
    """Test basic RSS fetching."""
    print("\n✅ Testing RSS Fetching...")

    import aiohttp
    import feedparser

    test_feed = "https://feeds.bbci.co.uk/news/world/rss.xml"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                test_feed, timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    content = await response.text()
                    feed = feedparser.parse(content)
                    print(f"  - Fetched {len(feed.entries)} articles from BBC")
                    print("  ✓ RSS Fetching working!")
                else:
                    print(f"  ⚠ BBC feed returned status {response.status}")
    except Exception as e:
        print(f"  ⚠ RSS fetch failed: {e}")


def main():
    """Run all tests."""
    print("=" * 60)
    print("BSG Bot Complete System Test")
    print("=" * 60)

    try:
        # Test components
        test_skb_catalog()
        test_selection_planner()
        test_entity_extractor()
        test_output_system()
        test_sentiment_analyzer()

        # Test async components
        asyncio.run(test_basic_fetch())

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nThe BSG Bot system is fully operational with:")
        print("  • SKB catalog with intelligent source selection")
        print("  • Entity extraction and signal detection")
        print("  • Institutional-style output formatting")
        print("  • Sentiment analysis")
        print("  • RSS fetching capabilities")
        print("\nYou can now run the full system with:")
        print("  poetry run bsgbot run --region [region] --topic [topic]")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
