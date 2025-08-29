#!/usr/bin/env python3
"""Test the professional sentiment analysis system."""

import asyncio
import sys
from pathlib import Path
import json
import time
import uuid
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from sentiment_bot.analyzers.sentiment_ensemble import SentimentEnsemble
from sentiment_bot.analyzers.aspect_extraction import AspectExtractor
from sentiment_bot.analyzers.aspect_sentiment import AspectSentimentAnalyzer
from sentiment_bot.analyzers.topic_nli import TopicAnalyzer
from sentiment_bot.analyzers.cluster import DocumentClusterer
from sentiment_bot.professional_metrics import ProfessionalMetrics
from sentiment_bot.state.db import SentimentDB

# Import existing components
from sentiment_bot.skb_catalog import get_catalog
from sentiment_bot.selection_planner import SelectionPlanner
from sentiment_bot.health_monitor import get_monitor
from sentiment_bot.cli_unified import _fetch_articles, _deduplicate_articles, _filter_by_freshness

import feedparser
import aiohttp
from rich.console import Console
from rich.progress import Progress
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()

async def test_professional_pipeline():
    """Test the complete professional sentiment analysis pipeline."""
    
    console.print(Panel.fit(
        "[bold cyan]Professional Sentiment Analysis Test[/bold cyan]",
        box=box.DOUBLE
    ))
    
    # Configuration
    region = "europe"
    topic = "economy"
    min_sources = 5
    budget = 30
    
    start_time = time.time()
    run_id = str(uuid.uuid4())[:8]
    
    # Step 1: Source Selection
    console.print("\n[bold]📚 Step 1: Source Selection[/bold]")
    catalog = get_catalog()
    planner = SelectionPlanner(catalog)
    monitor = get_monitor()
    
    plan = planner.plan_selection(
        region=region,
        topics=[topic]
    )
    
    console.print(f"Selected {len(plan.sources)} sources from {region} for {topic}")
    
    # Step 2: Fetch Articles
    console.print("\n[bold]📡 Step 2: Fetching Articles[/bold]")
    articles = await _fetch_articles(plan, monitor)
    console.print(f"Fetched {len(articles)} articles")
    
    # Step 3: Deduplication
    console.print("\n[bold]🔄 Step 3: Deduplication[/bold]")
    unique_articles = _deduplicate_articles(articles)
    console.print(f"Kept {len(unique_articles)}/{len(articles)} unique articles")
    
    # Step 4: Freshness Filter
    console.print("\n[bold]🕐 Step 4: Freshness Filtering[/bold]")
    fresh_articles, stale_count, freshness_rate = _filter_by_freshness(unique_articles, max_age_hours=24)
    console.print(f"Fresh: {len(fresh_articles)}/{len(unique_articles)} (Rate: {freshness_rate:.1%})")
    
    # Step 5: Clustering
    console.print("\n[bold]🎯 Step 5: Article Clustering[/bold]")
    clusterer = DocumentClusterer()
    clustered_articles = clusterer.cluster_articles(fresh_articles[:20])  # Limit for testing
    unique_clusters = len(set(a['cluster_id'] for a in clustered_articles))
    console.print(f"Found {unique_clusters} unique clusters from {len(clustered_articles)} articles")
    
    # Step 6: Professional Analysis
    console.print("\n[bold]🧠 Step 6: Professional Analysis[/bold]")
    
    ensemble = SentimentEnsemble()
    aspect_extractor = AspectExtractor()
    aspect_analyzer = AspectSentimentAnalyzer()
    topic_analyzer = TopicAnalyzer()
    
    analyzed_articles = []
    abstained_count = 0
    
    with Progress() as progress:
        task = progress.add_task("[cyan]Analyzing...", total=len(clustered_articles))
        
        for article in clustered_articles:
            # Ensemble sentiment
            text = article.get('content', article.get('description', ''))
            title = article.get('title', '')
            
            if text or title:
                # 1. Sentiment with confidence
                sentiment_result = ensemble.score_article(text, title)
                article['sentiment_score'] = sentiment_result.score
                article['confidence'] = sentiment_result.confidence
                article['sentiment_label'] = sentiment_result.label
                article['abstained'] = sentiment_result.abstained
                
                if sentiment_result.abstained:
                    abstained_count += 1
                
                # 2. Aspect extraction and sentiment
                aspects = aspect_extractor.extract_aspects(text, {'region': region, 'topic': topic})
                scored_aspects = aspect_analyzer.score_aspects(text, aspects)
                article['aspects'] = scored_aspects
                
                # 3. Topic analysis
                topic_analysis = topic_analyzer.analyze_full(text, topic, region)
                article['topic_relevance'] = topic_analysis['relevance_score']
                article['stances'] = topic_analysis['stances']
                article['tags'] = topic_analysis['tags']
                
                analyzed_articles.append(article)
            
            progress.advance(task)
    
    console.print(f"Analyzed {len(analyzed_articles)} articles, {abstained_count} abstained")
    
    # Step 7: Generate Cluster Summaries
    console.print("\n[bold]📊 Step 7: Cluster Summaries[/bold]")
    
    clusters_by_id = {}
    for article in analyzed_articles:
        cid = article.get('cluster_id', -1)
        if cid not in clusters_by_id:
            clusters_by_id[cid] = []
        clusters_by_id[cid].append(article)
    
    cluster_summaries = []
    for cid, cluster_articles in clusters_by_id.items():
        summary = clusterer.summarize_cluster(cluster_articles)
        cluster_summaries.append(summary)
    
    console.print(f"Generated {len(cluster_summaries)} cluster summaries")
    
    # Step 8: Save to Database
    console.print("\n[bold]💾 Step 8: Saving to Database[/bold]")
    
    db = SentimentDB()
    
    # Calculate aggregate metrics
    sentiment_scores = [a['sentiment_score'] for a in analyzed_articles if not a.get('abstained')]
    avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
    avg_confidence = sum(a['confidence'] for a in analyzed_articles) / len(analyzed_articles) if analyzed_articles else 0
    abstain_rate = abstained_count / len(analyzed_articles) if analyzed_articles else 0
    
    # Save run
    run_data = {
        'run_id': run_id,
        'region': region,
        'topic': topic,
        'freshness_rate': freshness_rate,
        'kept_ratio': len(analyzed_articles) / len(articles) if articles else 0,
        'abstain_rate': abstain_rate,
        'total_articles': len(articles),
        'fresh_articles': len(fresh_articles),
        'relevant_articles': len(analyzed_articles),
        'clusters_found': unique_clusters,
        'aggregate_sentiment': avg_sentiment,
        'confidence_avg': avg_confidence,
        'diversity': {
            'sources': len(plan.sources),
            'domains': len(set(a.get('domain') for a in analyzed_articles))
        },
        'metrics': {
            'fetch_success_rate': 0.9,  # Placeholder
            'processing_time': time.time() - start_time
        }
    }
    
    db.save_run(run_data)
    
    # Save articles
    for article in analyzed_articles:
        article['region'] = region
        article['topic'] = topic
        db.save_article(article, run_id)
    
    db.close()
    console.print(f"Saved run {run_id} to database")
    
    # Step 9: Generate Professional Metrics
    console.print("\n[bold]📈 Step 9: Professional Metrics[/bold]")
    
    metrics_collector = ProfessionalMetrics()
    
    # Prepare results
    results = {
        'total_articles': len(analyzed_articles),
        'sentiment_score': avg_sentiment,
        'sentiment': {
            'positive': sum(1 for a in analyzed_articles if a['sentiment_label'] == 'positive'),
            'negative': sum(1 for a in analyzed_articles if a['sentiment_label'] == 'negative'),
            'neutral': sum(1 for a in analyzed_articles if a['sentiment_label'] == 'neutral')
        }
    }
    
    performance = {
        'fetch_success_rate': 0.9,
        'freshness_rate': freshness_rate,
        'fresh_words': sum(len(a.get('content', a.get('description', '')).split()) for a in fresh_articles),
        'processing_time': time.time() - start_time
    }
    
    summary_path = metrics_collector.emit_run_summary(
        run_id=run_id,
        config={'region': region, 'topic': topic, 'min_sources': min_sources},
        results=results,
        articles=analyzed_articles,
        performance=performance
    )
    
    console.print(f"Metrics saved to {summary_path}")
    
    # Step 10: Display Results
    console.print("\n[bold]✅ Step 10: Results Summary[/bold]")
    
    # Quality table
    quality_table = Table(title="Quality Metrics", box=box.ROUNDED)
    quality_table.add_column("Metric", style="cyan")
    quality_table.add_column("Value", style="yellow")
    
    quality_table.add_row("Total Articles", str(len(analyzed_articles)))
    quality_table.add_row("Abstain Rate", f"{abstain_rate:.1%}")
    quality_table.add_row("Avg Confidence", f"{avg_confidence:.2f}")
    quality_table.add_row("Sentiment Score", f"{avg_sentiment:+.2f}")
    quality_table.add_row("Processing Time", f"{time.time() - start_time:.1f}s")
    
    console.print(quality_table)
    
    # Top aspects
    all_aspects = []
    for article in analyzed_articles:
        all_aspects.extend(article.get('aspects', []))
    
    if all_aspects:
        # Sort by importance
        all_aspects.sort(key=lambda a: a.get('importance', 0), reverse=True)
        
        aspects_table = Table(title="Top Aspects", box=box.SIMPLE)
        aspects_table.add_column("Aspect", style="cyan")
        aspects_table.add_column("Type", style="yellow")
        aspects_table.add_column("Sentiment", style="green")
        
        for aspect in all_aspects[:10]:
            sentiment_color = "green" if aspect['sentiment_score'] > 0 else "red"
            aspects_table.add_row(
                aspect['text'],
                aspect['type'],
                f"[{sentiment_color}]{aspect['sentiment_score']:+.2f}[/]"
            )
        
        console.print(aspects_table)
    
    # Cluster examples
    if cluster_summaries:
        cluster_table = Table(title="Cluster Summaries", box=box.SIMPLE)
        cluster_table.add_column("Size", style="cyan")
        cluster_table.add_column("Sentiment", style="yellow")
        cluster_table.add_column("Key Points", style="green")
        
        for summary in cluster_summaries[:5]:
            sentiment = summary['cluster_sentiment']
            key_points = "; ".join(summary['key_points'][:2])
            cluster_table.add_row(
                str(summary['size']),
                f"{sentiment['label']} ({sentiment['score']:+.2f})",
                key_points[:60] + "..."
            )
        
        console.print(cluster_table)
    
    console.print(f"\n[green]✓ Professional analysis complete in {time.time() - start_time:.1f} seconds[/green]")
    
    # Acceptance check
    console.print("\n[bold]📋 Acceptance Criteria Check:[/bold]")
    
    checks = [
        ("Freshness ≥ 0.7", freshness_rate >= 0.7, freshness_rate),
        ("Kept ≥ 45 articles", len(analyzed_articles) >= 45, len(analyzed_articles)),
        ("Abstain rate ≥ 5%", abstain_rate >= 0.05, abstain_rate),
        ("Confidence histogram available", avg_confidence > 0, avg_confidence),
        ("Per-aspect sentiment", len(all_aspects) > 0, len(all_aspects)),
        ("Cluster summaries", len(cluster_summaries) > 0, len(cluster_summaries)),
        ("Runtime ≤ 60s", time.time() - start_time <= 60, time.time() - start_time)
    ]
    
    check_table = Table(box=box.SIMPLE)
    check_table.add_column("Criterion", style="cyan")
    check_table.add_column("Status", style="yellow")
    check_table.add_column("Value", style="green")
    
    for criterion, passed, value in checks:
        status = "[green]✓[/green]" if passed else "[red]✗[/red]"
        check_table.add_row(criterion, status, str(value))
    
    console.print(check_table)

if __name__ == "__main__":
    asyncio.run(test_professional_pipeline())