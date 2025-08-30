#!/usr/bin/env python
"""Test the institutional output system directly."""

from datetime import datetime
from sentiment_bot.utils.run_id import make_run_id
from sentiment_bot.utils.output_writer import OutputWriter
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
from sentiment_bot.utils.entity_extractor import EntityExtractor

# Test data
region = "europe"
topic = "economy"
started_at = datetime.now()

# Generate run ID
run_id = make_run_id(region=region, topic=topic, started_at=started_at)
print(f"Run ID: {run_id}")

# Initialize components
writer = OutputWriter(output_dir="./test_output", run_id=run_id)
extractor = EntityExtractor()

# Create sample article records
sample_articles = [
    {
        "title": "ECB Signals Rate Cuts Amid Economic Slowdown",
        "text": "The European Central Bank indicated potential rate cuts as inflation pressures ease and economic growth slows across the eurozone.",
        "url": "https://example.com/ecb-rates",
        "source": "ft.com",
        "published": "2025-08-29T10:00:00Z",
    },
    {
        "title": "German Manufacturing Crisis Deepens",
        "text": "German industrial production fell sharply, raising concerns about recession risks in Europe's largest economy.",
        "url": "https://example.com/german-crisis",
        "source": "economist.com",
        "published": "2025-08-29T09:30:00Z",
    },
    {
        "title": "France Announces New Green Energy Investment Plan",
        "text": "The French government unveiled a €50 billion green energy investment plan to boost renewable energy and create jobs.",
        "url": "https://example.com/france-green",
        "source": "lemonde.fr",
        "published": "2025-08-29T08:45:00Z",
    },
]

# Build article records
article_records = []
for article in sample_articles:
    text = article["text"]

    # Extract entities and signals
    entities = extractor.extract_entities(text)
    tickers = extractor.extract_tickers(text)
    volatility = extractor.detect_volatility(text)

    # Mock sentiment (normally from analyzer)
    sentiment_score = -0.3 if "crisis" in text.lower() else 0.2
    sentiment_label = "neg" if sentiment_score < 0 else "pos"

    risk_level = extractor.detect_risk_level(text, sentiment_score)
    themes = extractor.extract_themes(text, topic)

    record = ArticleRecord(
        run_id=run_id,
        id=extractor.generate_article_id(
            source=article["source"],
            title=article["title"],
            published_at=article["published"],
        ),
        title=article["title"],
        url=article["url"],
        published_at=article["published"],
        source=article["source"],
        region=region,
        topic=topic,
        language="en",
        authors=[],
        tickers=tickers,
        entities=[{"text": e["text"], "type": e["type"]} for e in entities],
        summary=text[:200],
        text_chars=len(text),
        hash=extractor.calculate_text_hash(text),
        relevance=0.85,
        sentiment=Sentiment(
            label=sentiment_label, score=sentiment_score, confidence=0.9
        ),
        signals=SignalData(volatility=volatility, risk_level=risk_level, themes=themes),
    )
    article_records.append(record)

# Build run summary
run_summary = RunSummary(
    run_id=run_id,
    started_at=started_at.isoformat(),
    finished_at=datetime.now().isoformat(),
    config=ConfigBlock(
        region=region,
        topic=topic,
        budget_sec=30,
        min_sources=3,
        discover=False,
        max_age_hours=24,
    ),
    collection=CollectionBlock(
        attempted_feeds=10,
        articles_raw=50,
        unique_after_dedupe=45,
        fresh_window_h=24,
        fresh_count=40,
        relevant_count=len(article_records),
    ),
    analysis=AnalysisBlock(
        sentiment_total=-15,
        breakdown={"pos": 1, "neg": 2, "neu": 0},
        avg_sentiment=-0.13,
        top_triggers=["economic_growth", "monetary_policy", "green_transition"],
        top_entities=[
            EntityCount(text="ECB", type="ORG", count=2),
            EntityCount(text="Germany", type="GPE", count=2),
            EntityCount(text="France", type="GPE", count=1),
        ],
        volatility_index=0.35,
    ),
    sources=[
        SourceCount(domain="ft.com", articles=1),
        SourceCount(domain="economist.com", articles=1),
        SourceCount(domain="lemonde.fr", articles=1),
    ],
    diversity=DiversityBlock(
        sources=3, languages=2, regions=1, editorial_families=2, score=0.65
    ),
    errors=[],
    schema_version="1.0.0",
)

# Write outputs
print("\nWriting outputs...")

jsonl_path = writer.write_articles_jsonl(article_records)
print(f"✓ Articles JSONL: {jsonl_path}")

json_path = writer.write_run_summary_json(run_summary)
print(f"✓ Run Summary JSON: {json_path}")

# Generate highlights
highlights = [
    "🔴 ECB Signals Rate Cuts Amid Economic Slowdown",
    "🔴 German Manufacturing Crisis Deepens",
    "🟢 France Announces New Green Energy Investment Plan",
]

txt_path = writer.write_dashboard_txt(run_summary, highlights)
print(f"✓ Dashboard TXT: {txt_path}")

csv_path = writer.write_csv(article_records)
print(f"✓ Articles CSV: {csv_path}")

print("\n✅ Test completed successfully!")
