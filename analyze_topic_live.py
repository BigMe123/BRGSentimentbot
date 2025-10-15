#!/usr/bin/env python3
"""
Live Topic Analysis - Fetch real news and analyze sentiment.

This combines:
1. News aggregation from Google News, GDELT, RSS feeds
2. Sentiment analysis on fetched content
3. Comprehensive reporting

Usage:
    python analyze_topic_live.py "Kenya AGOA trade"
    python analyze_topic_live.py "US China tariffs" --max-articles 100
"""

import asyncio
import sys
import json
import argparse
from datetime import datetime
from collections import Counter
from sentiment_bot.connectors.news_aggregator import NewsAggregatorConnector
import aiohttp
import logging

logger = logging.getLogger(__name__)


# Simple sentiment analysis (using the same logic as sentiment_analyzer.py)
def analyze_sentiment_simple(text: str) -> dict:
    """Quick sentiment analysis using VADER."""
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()
        scores = analyzer.polarity_scores(text)
        return scores
    except ImportError:
        return {"compound": 0.0, "pos": 0.0, "neg": 0.0, "neu": 1.0}


def detect_keywords(text: str, keyword_categories: dict) -> list:
    """Detect specific keywords in text."""
    text_lower = text.lower()
    detected = []

    for category, keywords in keyword_categories.items():
        for keyword in keywords:
            if keyword in text_lower:
                detected.append(keyword)

    return detected


def extract_numbers(text: str) -> dict:
    """Extract important numbers from text."""
    import re

    numbers_found = {
        'jobs': [],
        'money': [],
        'percentages': [],
        'years': []
    }

    # Jobs numbers (e.g., "66,000 jobs", "50000 workers")
    job_pattern = r'([\d,]+)\s*(jobs|workers|employees|employment)'
    for match in re.finditer(job_pattern, text, re.IGNORECASE):
        numbers_found['jobs'].append(match.group(0))

    # Money amounts (e.g., "$52 million", "KSh 60 billion")
    money_pattern = r'([$£€KSh]\s*[\d,]+\.?\d*\s*(million|billion|trillion|bn|m)?)'
    for match in re.finditer(money_pattern, text, re.IGNORECASE):
        numbers_found['money'].append(match.group(0))

    # Percentages (e.g., "28%", "10 percent")
    percent_pattern = r'(\d+\.?\d*)\s*(%|percent)'
    for match in re.finditer(percent_pattern, text, re.IGNORECASE):
        numbers_found['percentages'].append(match.group(0))

    # Years (e.g., "2025", "2024")
    year_pattern = r'\b(20\d{2})\b'
    for match in re.finditer(year_pattern, text):
        numbers_found['years'].append(match.group(0))

    return numbers_found


async def fetch_article_text(session: aiohttp.ClientSession, url: str, timeout: int = 10) -> str:
    """Fetch full article text from URL using newspaper3k."""
    try:
        from newspaper import Article

        # Download with timeout
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            if response.status != 200:
                return ""

            html = await response.text()

        # Parse with newspaper3k
        article = Article(url)
        article.set_html(html)
        article.parse()

        return article.text if article.text else ""

    except Exception as e:
        logger.debug(f"Failed to fetch article text from {url}: {e}")
        return ""


async def enrich_articles_with_text(articles: list, max_concurrent: int = 5) -> list:
    """Fetch full text for articles in parallel."""

    print(f"⏳ Fetching full article text (this may take 30-60 seconds)...\n")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        enriched = []

        # Process in batches for speed
        for i in range(0, len(articles), max_concurrent):
            batch = articles[i:i+max_concurrent]

            # Fetch texts in parallel
            tasks = [fetch_article_text(session, a.get("url", "")) for a in batch]
            texts = await asyncio.gather(*tasks)

            # Update articles with full text
            for article, full_text in zip(batch, texts):
                if full_text and len(full_text) > 100:
                    article["text"] = full_text
                    article["text_enriched"] = True
                    print(f"  ✓ Fetched {len(full_text):,} chars from {article.get('metadata', {}).get('source_name', 'unknown')[:30]}")
                else:
                    article["text_enriched"] = False

                enriched.append(article)

            # Small delay between batches
            await asyncio.sleep(0.5)

    enriched_count = sum(1 for a in enriched if a.get("text_enriched"))
    print(f"\n✅ Enriched {enriched_count}/{len(articles)} articles with full text\n")

    return enriched


async def analyze_topic_live(
    topic: str,
    max_articles: int = 50,
    days_back: int = 30,
    fetch_full_text: bool = False
):
    """Fetch live news and analyze sentiment for a topic."""

    print(f"\n{'='*80}")
    print(f"🔍 Live Topic Analysis: {topic}")
    print(f"{'='*80}\n")

    # Step 1: Fetch news
    print(f"⏳ Fetching news from multiple sources...\n")

    connector = NewsAggregatorConnector(
        topic=topic,
        max_results=max_articles,
        days_back=days_back,
    )

    articles = []
    async for article in connector.fetch():
        articles.append(article)
        source = article.get("source", "unknown")
        title = article.get("title", "No title")[:70]
        print(f"  ✓ [{source:15s}] {title}")

        if len(articles) >= max_articles:
            break

    if not articles:
        print("\n❌ No articles found for this topic.")
        return None

    print(f"\n✅ Fetched {len(articles)} articles\n")

    # Step 1.5: Optionally enrich with full article text
    if fetch_full_text:
        articles = await enrich_articles_with_text(articles, max_concurrent=10)

    # Step 2: Analyze sentiment
    print(f"⏳ Analyzing sentiment...\n")

    keyword_categories = {
        'economic': [
            'trade', 'economy', 'tariff', 'tariffs', 'export', 'exports', 'import', 'imports',
            'gdp', 'investment', 'market', 'markets', 'growth', 'recession', 'inflation',
            'economic', 'fiscal', 'financial', 'revenue', 'deficit'
        ],
        'political': [
            'government', 'president', 'policy', 'policies', 'legislation', 'congress',
            'agreement', 'bilateral', 'diplomatic', 'sanctions', 'ruto', 'trump',
            'administration', 'negotiation', 'negotiations'
        ],
        'crisis': [
            'crisis', 'collapse', 'threat', 'threats', 'risk', 'risks', 'concern', 'concerns',
            'fear', 'fears', 'uncertainty', 'expire', 'expiry', 'expiration', 'deadline',
            'vulnerable', 'vulnerability', 'challenge', 'challenges'
        ],
        'positive': [
            'growth', 'opportunity', 'opportunities', 'benefit', 'benefits', 'success',
            'successful', 'increase', 'strengthen', 'improve', 'improvement', 'secure',
            'extension', 'renewal', 'optimize', 'enhance', 'win', 'gain'
        ],
        'jobs': [
            'jobs', 'job', 'employment', 'workers', 'worker', 'layoff', 'layoffs',
            'hiring', 'unemployment', 'workforce', 'employee', 'employees',
            'labor', 'labour'
        ],
        'agoa_specific': [
            'agoa', 'african growth', 'opportunity act', 'preferential',
            'duty-free', 'duty free', 'trade pact', 'trade deal'
        ],
        'kenya_specific': [
            'kenya', 'kenyan', 'nairobi', 'mombasa', 'epz', 'export processing',
            'textile', 'textiles', 'apparel', 'garment', 'garments', 'manufacturing',
            'macadamia', 'nuts'
        ],
        'us_africa': [
            'us-kenya', 'united states', 'america', 'american', 'washington',
            'stip', 'strategic trade', 'bilateral', 'fta', 'free trade'
        ]
    }

    analyzed_articles = []
    total_sentiment = 0.0
    all_keywords = []
    all_numbers = {'jobs': [], 'money': [], 'percentages': [], 'years': []}

    for article in articles:
        title = article.get("title", "")
        text = article.get("text", "")
        combined_text = f"{title} {text}"

        # Sentiment analysis
        sentiment = analyze_sentiment_simple(combined_text)

        # Keyword detection
        keywords = detect_keywords(combined_text, keyword_categories)
        all_keywords.extend(keywords)

        # Number extraction
        numbers = extract_numbers(combined_text)
        for key in all_numbers:
            all_numbers[key].extend(numbers[key])

        analyzed_articles.append({
            **article,
            "sentiment": sentiment,
            "keywords": keywords,
            "numbers": numbers
        })

        total_sentiment += sentiment.get("compound", 0.0)

    # Step 3: Generate insights
    print(f"{'='*80}")
    print(f"📊 Analysis Results")
    print(f"{'='*80}\n")

    avg_sentiment = total_sentiment / len(articles) if articles else 0.0

    print(f"Topic: {topic}")
    print(f"Articles Analyzed: {len(articles)}")
    print(f"Average Sentiment: {avg_sentiment:.3f} ", end="")

    if avg_sentiment > 0.1:
        print("(Positive 😊)")
    elif avg_sentiment < -0.1:
        print("(Negative 😟)")
    else:
        print("(Neutral 😐)")

    # Sources breakdown
    sources = Counter(a.get("source", "unknown") for a in articles)
    print(f"\n📰 Sources:")
    for source, count in sources.most_common(5):
        print(f"  • {source:20s}: {count:3d} articles")

    # Top keywords
    keyword_counts = Counter(all_keywords)
    print(f"\n🔑 Top Keywords:")
    for keyword, count in keyword_counts.most_common(10):
        print(f"  • {keyword:20s}: {count:3d} mentions")

    # Sentiment distribution
    positive_count = sum(1 for a in analyzed_articles if a["sentiment"]["compound"] > 0.1)
    negative_count = sum(1 for a in analyzed_articles if a["sentiment"]["compound"] < -0.1)
    neutral_count = len(articles) - positive_count - negative_count

    print(f"\n📈 Sentiment Distribution:")
    print(f"  • Positive: {positive_count:3d} ({positive_count/len(articles)*100:.1f}%)")
    print(f"  • Neutral:  {neutral_count:3d} ({neutral_count/len(articles)*100:.1f}%)")
    print(f"  • Negative: {negative_count:3d} ({negative_count/len(articles)*100:.1f}%)")

    # Most positive/negative articles
    sorted_by_sentiment = sorted(analyzed_articles, key=lambda x: x["sentiment"]["compound"])

    print(f"\n😟 Most Negative Headlines:")
    for article in sorted_by_sentiment[:3]:
        score = article["sentiment"]["compound"]
        title = article.get("title", "No title")[:70]
        source_name = article.get("metadata", {}).get("source_name", "Unknown")
        print(f"  [{score:+.2f}] {title} - {source_name}")

    print(f"\n😊 Most Positive Headlines:")
    for article in sorted_by_sentiment[-3:]:
        score = article["sentiment"]["compound"]
        title = article.get("title", "No title")[:70]
        source_name = article.get("metadata", {}).get("source_name", "Unknown")
        print(f"  [{score:+.2f}] {title} - {source_name}")

    # Key numbers found
    if any(all_numbers.values()):
        print(f"\n🔢 Key Numbers Detected:")
        if all_numbers['jobs']:
            unique_jobs = list(set(all_numbers['jobs']))[:5]
            print(f"  Jobs/Workers: {', '.join(unique_jobs)}")
        if all_numbers['money']:
            unique_money = list(set(all_numbers['money']))[:5]
            print(f"  Financial:    {', '.join(unique_money)}")
        if all_numbers['percentages']:
            unique_pct = list(set(all_numbers['percentages']))[:5]
            print(f"  Percentages:  {', '.join(unique_pct)}")
        if all_numbers['years']:
            unique_years = sorted(list(set(all_numbers['years'])), reverse=True)[:5]
            print(f"  Years:        {', '.join(unique_years)}")

    # Save results
    output_file = f"live_analysis_{topic.replace(' ', '_')[:30]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    def serialize_article(article):
        """Convert article dict to JSON-serializable format."""
        serialized = dict(article)
        for key, value in serialized.items():
            if isinstance(value, datetime):
                serialized[key] = value.isoformat()
            elif isinstance(value, dict):
                serialized[key] = {k: v.isoformat() if isinstance(v, datetime) else v for k, v in value.items()}
        return serialized

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "topic": topic,
            "analyzed_at": datetime.now().isoformat(),
            "total_articles": len(articles),
            "average_sentiment": avg_sentiment,
            "sentiment_distribution": {
                "positive": positive_count,
                "neutral": neutral_count,
                "negative": negative_count
            },
            "top_keywords": [{"keyword": k, "count": c} for k, c in keyword_counts.most_common(20)],
            "sources": dict(sources),
            "articles": [serialize_article(a) for a in analyzed_articles]
        }, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Full analysis saved to: {output_file}")
    print(f"\n{'='*80}\n")

    return analyzed_articles


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Live Topic Analysis with Sentiment")
    parser.add_argument("topic", nargs="+", help="Topic to analyze")
    parser.add_argument("--max-articles", type=int, default=50, help="Maximum articles to fetch")
    parser.add_argument("--days-back", type=int, default=30, help="Days back to search")
    parser.add_argument("--full-text", action="store_true", help="Fetch full article text (slower but more accurate)")

    args = parser.parse_args()
    topic = " ".join(args.topic)

    # Run async analysis
    asyncio.run(analyze_topic_live(
        topic=topic,
        max_articles=args.max_articles,
        days_back=args.days_back,
        fetch_full_text=args.full_text
    ))


if __name__ == "__main__":
    main()
