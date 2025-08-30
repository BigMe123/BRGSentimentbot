"""
Unified CLI - The SINGLE source of truth for all terminal commands.
Replaces cli_skb.py, cli_skb_optimized.py, and all other CLI variants.
"""

import asyncio
import typer
import time
import json
from pathlib import Path
from typing import Optional, List, Dict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)
from rich.live import Live
import logging
from datetime import datetime
from collections import Counter

from .skb_catalog import get_catalog
from .selection_planner import SelectionPlanner, SelectionQuotas
from .source_discovery import SourceDiscovery
from .relevance_filter import RelevanceFilter
from .health_monitor import get_monitor
from .smart_selector import SmartSelector
from .utils.run_id import make_run_id
from .utils.output_writer import OutputWriter
from .utils.output_models import (
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
from .utils.entity_extractor import EntityExtractor
import feedparser
import aiohttp
import asyncio
from .analyzer import analyze
from dateutil import parser as date_parser
import hashlib

app = typer.Typer(
    name="bsgbot",
    help="BSG Bot - Massive SKB with intelligent source selection and analysis",
)
console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@app.command()
def run(
    output_dir: str = typer.Option(
        "./output", "--output-dir", "-o", help="Directory for output files"
    ),
    run_id_seed: Optional[str] = typer.Option(
        None, "--run-id", help="Optional seed for run ID generation"
    ),
    export_csv: bool = typer.Option(
        False, "--export-csv", help="Also export results as CSV"
    ),
    region: Optional[str] = typer.Option(
        None,
        "--region",
        "-r",
        help="Target region: asia, middle_east, europe, americas, africa",
    ),
    topic: Optional[str] = typer.Option(
        None,
        "--topic",
        "-t",
        help="Standard topic: elections, security, economy, politics, energy, climate, tech",
    ),
    other: Optional[str] = typer.Option(
        None,
        "--other",
        "-o",
        help="Free-text topic for obscure subjects (triggers fuzzy matching and discovery)",
    ),
    strict: bool = typer.Option(
        False, "--strict", "-s", help="Strict mode - only exact matches"
    ),
    expand: bool = typer.Option(
        False, "--expand", "-e", help="Expand to include cross-regional specialists"
    ),
    budget: int = typer.Option(
        300, "--budget", "-b", help="Time budget in seconds (default: 5 minutes)"
    ),
    min_sources: int = typer.Option(
        30, "--min-sources", help="Minimum number of sources to fetch"
    ),
    target_words: int = typer.Option(
        10000, "--target-words", help="Target fresh words to collect"
    ),
    discover: bool = typer.Option(
        False,
        "--discover",
        "-d",
        help="Enable active source discovery for obscure topics",
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-f", help="Output file for results (JSON format)"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Plan only, don't fetch articles"
    ),
):
    """
    Main analysis command - the unified entry point for all operations.

    Examples:
        # Standard region/topic analysis
        bsgbot run --region asia --topic elections

        # Obscure topic with discovery
        bsgbot run --other "semiconductors in Maghreb" --discover

        # Strict mode with expanded sources
        bsgbot run --region europe --topic energy --strict --expand

        # Quick run with small budget
        bsgbot run --topic climate --budget 60 --min-sources 10
    """

    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate inputs
    if not any([region, topic, other]):
        console.print(
            "[red]Error: Must specify at least one of --region, --topic, or --other[/red]"
        )
        raise typer.Exit(1)

    if topic and other:
        console.print(
            "[yellow]Warning: Both --topic and --other specified, using --topic[/yellow]"
        )
        other = None

    # Display configuration
    config_text = f"""[bold cyan]Configuration[/bold cyan]
Region: {region or 'All'}
Topic: {topic or other or 'All'}
Mode: {'Strict' if strict else 'Flexible'} {'+ Expanded' if expand else ''}
Discovery: {'Enabled' if discover or other else 'Disabled'}
Budget: {budget}s
Min Sources: {min_sources}
Target Words: {target_words}"""

    console.print(Panel(config_text, title="BSG Bot Run"))

    # Run async main
    asyncio.run(
        _run_async(
            region=region,
            topic=topic,
            other=other,
            strict=strict,
            expand=expand,
            budget=budget,
            min_sources=min_sources,
            target_words=target_words,
            discover=discover,
            output=output,
            dry_run=dry_run,
            output_dir=output_dir,
            run_id_seed=run_id_seed,
            export_csv=export_csv,
        )
    )


async def _run_async(
    region: Optional[str],
    topic: Optional[str],
    other: Optional[str],
    strict: bool,
    expand: bool,
    budget: int,
    min_sources: int,
    target_words: int,
    discover: bool,
    output: Optional[str],
    dry_run: bool,
    output_dir: str,
    run_id_seed: Optional[str],
    export_csv: bool,
):
    """Async main execution."""

    start_time = time.time()
    started_at = datetime.now()
    catalog = get_catalog()
    monitor = get_monitor()

    # Generate run ID
    run_id = make_run_id(
        region=region, topic=topic or other, started_at=started_at, seed=run_id_seed
    )

    # Initialize output writer
    writer = OutputWriter(output_dir=output_dir, run_id=run_id)
    entity_extractor = EntityExtractor()

    console.print(f"[bold cyan]Run ID: {run_id}[/bold cyan]")

    # Step 1: Selection Planning
    console.print("\n[bold]📚 Planning Source Selection...[/bold]")

    planner = SelectionPlanner(catalog)
    quotas = SelectionQuotas(min_sources=min_sources, time_budget_seconds=budget)

    # Handle topic resolution
    topics = [topic] if topic else None

    plan = planner.plan_selection(
        region=region,
        topics=topics,
        other_topic=other,
        strict=strict,
        expand=expand,
        quotas=quotas,
    )

    # Display selection summary
    _display_selection_summary(plan)

    # Check if we need discovery
    needs_discovery = len(plan.sources) < min_sources and (discover or other)

    if needs_discovery:
        console.print("\n[bold]🔍 Running Source Discovery...[/bold]")
        discovery_sources = await _run_discovery(
            topic=other or topic,
            region=region,
            time_budget=plan.time_allocations.get("_discovery", 30),
        )

        # Add discovered sources to plan
        for disc_source in discovery_sources[:20]:  # Limit additions
            plan.sources.append(disc_source)

        console.print(
            f"[green]Added {len(discovery_sources)} discovered sources[/green]"
        )

    if dry_run:
        console.print("\n[yellow]Dry run mode - skipping article fetching[/yellow]")
        return

    # Step 2: Fetch Articles
    console.print("\n[bold]📡 Fetching Articles...[/bold]")

    articles = await _fetch_articles(plan, monitor)

    # Step 2.5: Deduplication
    console.print(f"\n[bold]🔄 Deduplicating Articles...[/bold]")
    unique_articles = _deduplicate_articles(articles)
    console.print(
        f"[green]Kept {len(unique_articles)}/{len(articles)} unique articles[/green]"
    )

    # Step 2.6: Freshness Filtering
    console.print(f"\n[bold]🕐 Applying Freshness Filter (max age: 24h)...[/bold]")
    fresh_articles, stale_count, freshness_rate = _filter_by_freshness(
        unique_articles, max_age_hours=24
    )
    console.print(
        f"[green]Fresh: {len(fresh_articles)}/{len(unique_articles)} articles (Freshness Rate: {freshness_rate:.1%})[/green]"
    )

    # Calculate fresh words
    fresh_words = sum(
        len(article.get("content", article.get("description", "")).split())
        for article in fresh_articles
    )
    console.print(f"[cyan]Fresh words collected: {fresh_words:,}[/cyan]")

    # Step 3: Relevance Verification
    console.print("\n[bold]✅ Verifying Relevance...[/bold]")

    relevance_filter = RelevanceFilter()
    filtered_articles = []

    with Progress() as progress:
        task = progress.add_task("[cyan]Filtering...", total=len(articles))

        for article in fresh_articles:  # Only process fresh articles
            score = relevance_filter.verify_relevance(
                article=article,
                target_region=region,
                target_topics=topics or [other] if other else None,
                strict=strict,
            )

            if score.should_keep:
                article["_relevance_weight"] = score.weight
                filtered_articles.append(article)

                # Record relevance metrics
                monitor.record_relevance(
                    domain=article.get("domain", "unknown"),
                    relevance_score=score.weight,
                    dropped=False,
                )
            else:
                monitor.record_relevance(
                    domain=article.get("domain", "unknown"),
                    relevance_score=score.weight,
                    dropped=True,
                )

            progress.advance(task)

    console.print(
        f"[green]Kept {len(filtered_articles)}/{len(fresh_articles)} relevant articles[/green]"
    )

    # Step 4: Analysis
    console.print("\n[bold]🧠 Analyzing Sentiment...[/bold]")

    results = await _analyze_articles(filtered_articles)

    # Add freshness metrics to results
    results["freshness_rate"] = freshness_rate
    results["fresh_words"] = fresh_words

    # Build article records for institutional output
    article_records = []
    for article in filtered_articles:
        # Get text content
        text = (
            article.get("content", "")
            or article.get("description", "")
            or article.get("title", "")
        )

        # Extract entities and signals
        entities = entity_extractor.extract_entities(text)
        tickers = entity_extractor.extract_tickers(text)
        volatility = entity_extractor.detect_volatility(text)

        # Get sentiment analysis
        analysis = analyze(text) if text else None
        sentiment_score = analysis.vader if analysis else 0
        sentiment_label = (
            "pos"
            if sentiment_score > 0.05
            else ("neg" if sentiment_score < -0.05 else "neu")
        )

        risk_level = entity_extractor.detect_risk_level(text, sentiment_score)
        themes = entity_extractor.extract_themes(text, topic or other)

        # Create article record
        record = ArticleRecord(
            run_id=run_id,
            id=entity_extractor.generate_article_id(
                source=article.get("domain", "unknown"),
                title=article.get("title", ""),
                published_at=article.get("published", ""),
            ),
            title=article.get("title", "Untitled"),
            url=article.get("link", ""),
            published_at=article.get("published", datetime.now().isoformat()),
            source=article.get("domain", "unknown"),
            region=region or "global",
            topic=topic or other or "general",
            language="en",
            authors=article.get("authors", []),
            tickers=tickers,
            entities=[{"text": e["text"], "type": e["type"]} for e in entities],
            summary=article.get("summary", "")[:500],
            text_chars=len(text),
            hash=entity_extractor.calculate_text_hash(text),
            relevance=article.get("_relevance_weight", 0.5),
            sentiment=Sentiment(
                label=sentiment_label, score=sentiment_score, confidence=0.8
            ),
            signals=SignalData(
                volatility=volatility, risk_level=risk_level, themes=themes
            ),
        )
        article_records.append(record)

    # Step 5: Auto-tune sources
    console.print("\n[bold]⚙️ Auto-tuning Sources...[/bold]")

    tune_actions = monitor.auto_tune_sources(dry_run=False)
    if any(tune_actions.values()):
        _display_tuning_actions(tune_actions)

    # Step 6: Display Results
    console.print("\n[bold]📊 Results Summary[/bold]")

    _display_results(results, monitor.get_run_metrics())

    # Step 7: Generate institutional outputs
    console.print("\n[bold]💾 Writing Institutional Outputs...[/bold]")

    # Build run summary
    sentiment_breakdown = results.get("sentiment", {})
    total_articles = sum(sentiment_breakdown.values())
    avg_sentiment = (
        sum(r.sentiment.score for r in article_records) / len(article_records)
        if article_records
        else 0
    )

    # Count entities
    entity_counter = Counter()
    for record in article_records:
        for entity in record.entities:
            entity_counter[(entity["text"], entity["type"])] += 1

    top_entities = [
        EntityCount(text=text, type=etype, count=count)
        for (text, etype), count in entity_counter.most_common(10)
    ]

    # Count sources
    source_counter = Counter(r.source for r in article_records)
    source_counts = [
        SourceCount(domain=domain, articles=count)
        for domain, count in source_counter.most_common()
    ]

    # Extract top triggers (volatility keywords)
    all_themes = []
    for record in article_records:
        if record.signals:
            all_themes.extend(record.signals.themes)
    theme_counter = Counter(all_themes)
    top_triggers = [theme for theme, _ in theme_counter.most_common(5)]

    # Calculate volatility index
    volatility_scores = [r.signals.volatility for r in article_records if r.signals]
    volatility_index = (
        sum(volatility_scores) / len(volatility_scores) if volatility_scores else 0
    )

    # Build summary object
    run_summary = RunSummary(
        run_id=run_id,
        started_at=started_at.isoformat(),
        finished_at=datetime.now().isoformat(),
        config=ConfigBlock(
            region=region,
            topic=topic or other,
            budget_sec=budget,
            min_sources=min_sources,
            discover=discover,
            max_age_hours=24,
        ),
        collection=CollectionBlock(
            attempted_feeds=len(plan.sources),
            articles_raw=len(articles),
            unique_after_dedupe=len(unique_articles),
            fresh_window_h=24,
            fresh_count=len(fresh_articles),
            relevant_count=len(filtered_articles),
        ),
        analysis=AnalysisBlock(
            sentiment_total=int(avg_sentiment * 100),
            breakdown=sentiment_breakdown,
            avg_sentiment=avg_sentiment,
            top_triggers=top_triggers,
            top_entities=top_entities,
            volatility_index=volatility_index,
        ),
        sources=source_counts,
        diversity=DiversityBlock(
            sources=len(source_counter),
            languages=(
                len(plan.language_distribution)
                if hasattr(plan, "language_distribution")
                else 1
            ),
            regions=(
                len(plan.region_distribution)
                if hasattr(plan, "region_distribution")
                else 1
            ),
            editorial_families=(
                len(plan.editorial_families)
                if hasattr(plan, "editorial_families")
                else 1
            ),
            score=(
                plan.get_diversity_score()
                if hasattr(plan, "get_diversity_score")
                else 0.5
            ),
        ),
        errors=[],
        schema_version="1.0.0",
    )

    # Write outputs
    jsonl_path = writer.write_articles_jsonl(article_records)
    console.print(f"[green]✓ Articles JSONL: {jsonl_path}[/green]")

    json_path = writer.write_run_summary_json(run_summary)
    console.print(f"[green]✓ Run Summary JSON: {json_path}[/green]")

    # Generate highlights for dashboard
    highlights = []
    for record in sorted(
        article_records, key=lambda r: abs(r.sentiment.score), reverse=True
    )[:5]:
        sentiment_emoji = (
            "🟢"
            if record.sentiment.label == "pos"
            else "🔴" if record.sentiment.label == "neg" else "⚪"
        )
        highlights.append(f"{sentiment_emoji} {record.title[:80]}")

    txt_path = writer.write_dashboard_txt(run_summary, highlights)
    console.print(f"[green]✓ Dashboard TXT: {txt_path}[/green]")

    if export_csv:
        csv_path = writer.write_csv(article_records)
        console.print(f"[green]✓ Articles CSV: {csv_path}[/green]")

    # Step 8: Save legacy output if requested
    if output:
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "config": {
                "region": region,
                "topic": topic or other,
                "strict": strict,
                "expand": expand,
                "budget": budget,
            },
            "plan": {
                "sources_selected": len(plan.sources),
                "diversity_score": plan.get_diversity_score(),
                "selection_time_ms": plan.selection_time_ms,
            },
            "results": results,
            "metrics": monitor.export_metrics(),
        }

        with open(output, "w") as f:
            json.dump(output_data, f, indent=2, default=str)

        console.print(f"[green]Results saved to {output}[/green]")

    # Final timing
    total_time = time.time() - start_time
    console.print(f"\n[bold green]✓ Completed in {total_time:.1f} seconds[/bold green]")


async def _run_discovery(topic: str, region: Optional[str], time_budget: float) -> List:
    """Run source discovery for obscure topics."""

    discovery = SourceDiscovery(
        max_concurrent=5, timeout=10, max_domains=20, max_pages=50
    )

    results = await discovery.discover_sources(
        topic=topic, region=region, time_budget=time_budget
    )

    # Convert discovery results to source records
    sources = []
    for result in results:
        if result.confidence > 0.4:  # Only decent matches
            from .skb_catalog import SourceRecord

            source = SourceRecord(
                domain=result.domain,
                name=result.domain,
                region=region or "global",
                topics=result.topics or [],
                rss_endpoints=[result.url],
                priority=0.3,
                policy="allow",
            )
            sources.append(source)

    return sources


async def _fetch_single_rss(session, url):
    """Fetch single RSS feed."""
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            if response.status == 200:
                content = await response.text()
                feed = feedparser.parse(content)
                return (feed, url, True)  # Return status for progress tracking
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
    return (None, url, False)  # Return status even on failure


async def _fetch_articles(plan, monitor) -> List[Dict]:
    """Fetch articles from selected sources."""

    articles = []

    # Build RSS URLs from sources
    rss_urls = []
    for source in plan.sources:
        if source.rss_endpoints:  # Only process sources with RSS feeds
            for endpoint in source.rss_endpoints[
                :1
            ]:  # Limit to 1 endpoint per source to avoid overload
                rss_urls.append(endpoint)
                logger.info(f"Added RSS endpoint: {endpoint}")

    if not rss_urls:
        console.print(
            "[yellow]Warning: No RSS feeds found for selected sources[/yellow]"
        )
        return articles

    with Progress() as progress:
        task = progress.add_task("[cyan]Fetching RSS feeds...", total=len(rss_urls))

        # Fetch feeds with timeout
        async with aiohttp.ClientSession() as session:
            # Create tasks but don't gather immediately
            tasks = [_fetch_single_rss(session, url) for url in rss_urls]

            # Process results as they complete for live progress updates
            for coro in asyncio.as_completed(tasks):
                result = await coro
                feed, url, success = result
                progress.advance(task)  # Update progress for each completed feed

                if feed and feed.entries:
                    domain = (
                        feed.feed.get("title", "Unknown")
                        if hasattr(feed, "feed")
                        else "Unknown"
                    )

                    # Smart fetch limit based on source quality
                    fetch_limit = 25  # Default increased from 10
                    for entry in feed.entries[:fetch_limit]:
                        # Extract article data
                        # Parse published date for freshness
                        published_str = entry.get("published", entry.get("updated", ""))
                        published_date = None
                        if published_str:
                            try:
                                published_date = date_parser.parse(published_str)
                            except:
                                pass

                        article = {
                            "title": entry.get("title", ""),
                            "link": entry.get("link", ""),
                            "description": entry.get(
                                "summary", entry.get("description", "")
                            ),
                            "domain": domain,
                            "published": published_str,
                            "published_date": published_date,
                            "content": (
                                entry.get("content", [{}])[0].get("value", "")
                                if "content" in entry
                                else ""
                            ),
                            "url_hash": hashlib.md5(
                                entry.get("link", "").encode()
                            ).hexdigest(),  # For dedup
                        }

                        # Record fetch metrics
                        monitor.record_fetch_result(
                            domain=domain, success=True, latency_ms=100  # Placeholder
                        )

                        articles.append(article)
                else:
                    # Record failure metrics
                    monitor.record_fetch_result(
                        domain=url.split("/")[2] if "/" in url else "unknown",
                        success=False,
                        latency_ms=100,
                    )

    return articles


async def _analyze_articles(articles: List[Dict]) -> Dict:
    """Analyze article sentiment."""

    if not articles:
        return {
            "total_articles": 0,
            "sentiment": {"positive": 0, "negative": 0, "neutral": 0},
            "top_topics": [],
            "key_insights": [],
        }

    # Analyze each article individually with progress
    console.print(f"Analyzing {len(articles)} articles...")
    analysis_results = []

    for i, article in enumerate(articles):
        if i % 10 == 0:
            console.print(f"  Progress: {i}/{len(articles)} articles analyzed...")

        # Get the text content from the article
        text = (
            article.get("content", "")
            or article.get("description", "")
            or article.get("title", "")
        )

        if text:
            try:
                # Analyze the text content with a reasonable limit
                text_sample = text[:1000]  # Limit text to first 1000 chars for speed
                analysis = analyze(text_sample)

                # Create result dict with the analysis
                result = {
                    "title": article.get("title", "Untitled"),
                    "sentiment_label": (
                        "POSITIVE"
                        if analysis.vader > 0.05
                        else ("NEGATIVE" if analysis.vader < -0.05 else "NEUTRAL")
                    ),
                    "sentiment_score": analysis.vader,
                }
                analysis_results.append(result)
            except Exception as e:
                logger.warning(f"Failed to analyze article: {e}")
                continue

    # Calculate aggregate sentiment score (-100 to +100)
    if analysis_results:
        avg_sentiment = sum(a["sentiment_score"] for a in analysis_results) / len(
            analysis_results
        )
        # Convert from -1 to 1 scale to -100 to +100 scale
        aggregate_score = round(avg_sentiment * 100)
    else:
        aggregate_score = 0

    # Format results for display
    results = {
        "total_articles": len(articles),
        "sentiment_score": aggregate_score,  # Single aggregate score
        "sentiment": {
            "positive": sum(
                1 for a in analysis_results if a["sentiment_label"] == "POSITIVE"
            ),
            "negative": sum(
                1 for a in analysis_results if a["sentiment_label"] == "NEGATIVE"
            ),
            "neutral": sum(
                1 for a in analysis_results if a["sentiment_label"] == "NEUTRAL"
            ),
        },
        "top_topics": [],
        "key_insights": [],
    }

    # Extract key insights from highly positive/negative articles
    for article in analysis_results:
        if article["sentiment_score"] > 0.8 or article["sentiment_score"] < -0.8:
            results["key_insights"].append(
                {
                    "title": article["title"],
                    "sentiment": article["sentiment_label"],
                    "score": article["sentiment_score"],
                }
            )

    return results


def _display_selection_summary(plan):
    """Display selected sources summary."""

    table = Table(title="Selected Sources", show_header=True)
    table.add_column("Domain", style="cyan", width=30)
    table.add_column("Priority", style="yellow", width=10)
    table.add_column("Topics", style="green", width=30)
    table.add_column("Policy", style="magenta", width=15)

    # Show top sources
    for source in plan.sources[:15]:
        topics_str = ", ".join(source.topics[:3]) if source.topics else "general"
        table.add_row(
            source.domain[:30], f"{source.priority:.2f}", topics_str[:30], source.policy
        )

    if len(plan.sources) > 15:
        table.add_row(f"... + {len(plan.sources) - 15} more", "", "", "")

    console.print(table)

    # Diversity metrics
    diversity_text = f"""Sources: {len(plan.sources)}
Editorial Families: {len(plan.editorial_families)}
Languages: {len(plan.language_distribution)}
Regions: {len(plan.region_distribution)}
Diversity Score: {plan.get_diversity_score():.2f}"""

    console.print(Panel(diversity_text, title="Diversity Metrics"))


def _display_tuning_actions(actions: Dict):
    """Display auto-tuning actions."""

    if actions["promoted"]:
        console.print(
            f"[green]↑ Promoted: {', '.join(actions['promoted'][:5])}[/green]"
        )

    if actions["demoted"]:
        console.print(
            f"[yellow]↓ Demoted: {', '.join(actions['demoted'][:5])}[/yellow]"
        )

    if actions["parked"]:
        console.print(f"[red]✗ Parked: {', '.join(actions['parked'][:5])}[/red]")


def _display_results(results: Dict, metrics: Dict):
    """Display analysis results."""

    # Results table
    table = Table(title="Analysis Results", show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="yellow")

    table.add_row("Total Articles", str(results["total_articles"]))

    # Display sentiment score with color based on value
    score = results.get("sentiment_score", 0)
    if score > 20:
        score_style = "[green]"
    elif score < -20:
        score_style = "[red]"
    else:
        score_style = "[yellow]"

    table.add_row("Sentiment Score", f"{score_style}{score:+d}[/]")
    table.add_row(
        "Breakdown",
        f"Pos: {results['sentiment']['positive']}, "
        f"Neg: {results['sentiment']['negative']}, "
        f"Neu: {results['sentiment']['neutral']}",
    )

    console.print(table)

    # Metrics table
    if metrics:
        metrics_table = Table(title="Run Metrics", show_header=False)
        metrics_table.add_column("Metric", style="cyan")
        metrics_table.add_column("Value", style="green")

        metrics_table.add_row(
            "Fetch Success Rate", f"{metrics.get('fetch_success_rate', 0):.1%}"
        )
        metrics_table.add_row(
            "Freshness Rate", f"{metrics.get('freshness_rate', 0):.1%}"
        )
        metrics_table.add_row("Fresh Words", f"{metrics.get('fresh_words', 0):,}")
        metrics_table.add_row(
            "Avg Latency", f"{metrics.get('avg_latency_ms', 0):.0f}ms"
        )

        console.print(metrics_table)


def _deduplicate_articles(articles: List[Dict]) -> List[Dict]:
    """Remove duplicate articles based on URL hash."""
    seen_hashes = set()
    unique_articles = []

    for article in articles:
        url_hash = (
            article.get("url_hash")
            or hashlib.md5(article.get("link", "").encode()).hexdigest()
        )
        if url_hash not in seen_hashes:
            seen_hashes.add(url_hash)
            unique_articles.append(article)

    return unique_articles


def _filter_by_freshness(articles: List[Dict], max_age_hours: int = 24) -> tuple:
    """Filter articles by freshness."""
    from datetime import datetime, timedelta

    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    fresh_articles = []
    stale_count = 0

    for article in articles:
        pub_date = article.get("published_date")

        if pub_date:
            # Make timezone naive for comparison if needed
            if hasattr(pub_date, "tzinfo") and pub_date.tzinfo:
                pub_date = pub_date.replace(tzinfo=None)
                cutoff_naive = cutoff
            else:
                cutoff_naive = cutoff

            if pub_date >= cutoff_naive:
                fresh_articles.append(article)
            else:
                stale_count += 1
        else:
            # If no date, be conservative and exclude it
            stale_count += 1

    freshness_rate = len(fresh_articles) / len(articles) if articles else 0

    return fresh_articles, stale_count, freshness_rate


@app.command()
def import_skb(
    yaml_path: str = typer.Argument(..., help="Path to SKB YAML file"),
    force: bool = typer.Option(False, "--force", "-f", help="Force reimport"),
):
    """Import SKB from YAML file into SQLite catalog."""

    yaml_file = Path(yaml_path)
    if not yaml_file.exists():
        console.print(f"[red]Error: File {yaml_path} not found[/red]")
        raise typer.Exit(1)

    catalog = get_catalog()

    console.print(f"[cyan]Importing SKB from {yaml_path}...[/cyan]")

    try:
        catalog.import_from_yaml(str(yaml_file))
        stats = catalog.get_stats()

        console.print(
            f"[green]✓ Successfully imported {stats['total_sources']} sources[/green]"
        )
        console.print(f"  Active: {stats['active_sources']}")
        console.print(f"  Regions: {', '.join(stats['regions'].keys())}")

    except Exception as e:
        console.print(f"[red]Error importing SKB: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def stats():
    """Display SKB catalog statistics."""

    catalog = get_catalog()
    stats = catalog.get_stats()

    # Main stats
    table = Table(title="SKB Statistics", show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="yellow")

    table.add_row("Total Sources", str(stats["total_sources"]))
    table.add_row("Active Sources", str(stats["active_sources"]))
    table.add_row("Staging Sources", str(stats["staging_sources"]))
    table.add_row("Parked Sources", str(stats["parked_sources"]))
    table.add_row("Avg Reliability", f"{stats['avg_reliability']:.2f}")
    table.add_row("Avg Yield", f"{stats['avg_yield']:.0f} words")

    console.print(table)

    # Region distribution
    if stats["regions"]:
        region_table = Table(title="Sources by Region", show_header=True)
        region_table.add_column("Region", style="cyan")
        region_table.add_column("Count", style="yellow")

        for region, count in sorted(
            stats["regions"].items(), key=lambda x: x[1], reverse=True
        ):
            region_table.add_row(region, str(count))

        console.print(region_table)

    # Top topics
    if stats["topics"]:
        topic_table = Table(title="Top Topics", show_header=True)
        topic_table.add_column("Topic", style="green")
        topic_table.add_column("Sources", style="yellow")

        for topic, count in list(stats["topics"].items())[:10]:
            topic_table.add_row(topic, str(count))

        console.print(topic_table)


@app.command()
def health(
    domain: Optional[str] = typer.Option(
        None, "--domain", "-d", help="Specific domain to check"
    ),
    export: Optional[str] = typer.Option(
        None, "--export", "-e", help="Export metrics to JSON file"
    ),
):
    """Display source health metrics."""

    monitor = get_monitor()

    if domain:
        # Specific source report
        report = monitor.get_source_report(domain)
        if not report:
            console.print(f"[yellow]No metrics available for {domain}[/yellow]")
            return

        table = Table(title=f"Health Report: {domain}", show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="yellow")

        table.add_row("Health Score", f"{report['health_score']:.2f}")
        table.add_row("Success Rate", f"{report['success_rate']:.1%}")
        table.add_row("Avg Latency", f"{report['avg_latency_ms']:.0f}ms")
        table.add_row("Freshness Rate", f"{report['freshness_rate']:.1%}")
        table.add_row("Avg Yield", f"{report['avg_yield_words']:.0f} words")

        console.print(table)

    else:
        # Overall health summary
        metrics = monitor.get_run_metrics()

        if not metrics:
            console.print(
                "[yellow]No health metrics available yet. Run an analysis first.[/yellow]"
            )
            return

        table = Table(title="Overall Health Metrics", show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="yellow")

        table.add_row("Total Sources", str(metrics.get("total_sources", 0)))
        table.add_row(
            "Fetch Success Rate", f"{metrics.get('fetch_success_rate', 0):.1%}"
        )
        table.add_row("Freshness Rate", f"{metrics.get('freshness_rate', 0):.1%}")
        table.add_row("Avg Latency", f"{metrics.get('avg_latency_ms', 0):.0f}ms")

        console.print(table)

        # Health distribution
        if "sources_by_health" in metrics:
            health_table = Table(title="Sources by Health", show_header=True)
            health_table.add_column("Category", style="cyan")
            health_table.add_column("Count", style="yellow")

            for category, count in metrics["sources_by_health"].items():
                health_table.add_row(category.capitalize(), str(count))

            console.print(health_table)

    if export:
        all_metrics = monitor.export_metrics()
        with open(export, "w") as f:
            json.dump(all_metrics, f, indent=2, default=str)
        console.print(f"[green]Metrics exported to {export}[/green]")


@app.command()
def connectors(
    config: str = typer.Option(
        "config/sources.yaml",
        "--config",
        "-c",
        help="Path to connector configuration YAML",
    ),
    connector_type: Optional[str] = typer.Option(
        None, "--type", "-t", help="Run only specific connector type"
    ),
    output_dir: str = typer.Option(
        "./output", "--output-dir", "-o", help="Directory for output files"
    ),
    limit: int = typer.Option(400, "--limit", "-l", help="Maximum items per connector"),
    analyze: bool = typer.Option(
        False, "--analyze", help="Run sentiment analysis on fetched content"
    ),
    keywords: Optional[str] = typer.Option(
        None,
        "--keywords",
        "-k",
        help="Keywords for relevance filtering (comma-separated)",
    ),
    since: Optional[str] = typer.Option(
        None,
        "--since",
        "-s",
        help="Date window filter (e.g., '24h', '7d', '2025-01-01')",
    ),
):
    """Fetch data using modern connectors (Reddit, Twitter, YouTube, etc.)

    Examples:
        # Fetch crypto data with keyword fan-out
        bsgbot connectors --keywords "crypto,blockchain,bitcoin,ethereum" --limit 400 --since 7d

        # Test specific connector
        bsgbot connectors --type google_news --keywords "bitcoin" --limit 50

        # Full analysis with metrics
        bsgbot connectors --keywords "web3,defi" --analyze --since 24h
    """

    from .ingest.registry import ConnectorRegistry
    from .ingest.utils import parse_since_window, keyword_match
    from datetime import datetime
    import time

    async def run_connectors():
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Initialize registry
        registry = ConnectorRegistry(config)

        if not registry.connectors:
            console.print(
                "[red]No connectors configured. Check your config file.[/red]"
            )
            console.print(
                f"[yellow]Copy config/sources.example.yaml to {config} to get started[/yellow]"
            )
            return

        # Filter connectors if type specified
        connectors = registry.connectors
        if connector_type:
            connectors = [c for c in connectors if c.name == connector_type]
            if not connectors:
                console.print(f"[red]Connector type '{connector_type}' not found[/red]")
                return

        # Show configured connectors
        table = Table(title="Active Connectors")
        table.add_column("Type", style="cyan")
        table.add_column("Class", style="green")

        for conn in connectors:
            table.add_row(conn.name, conn.__class__.__name__)

        console.print(table)
        console.print()

        # Initialize components
        analyzer_func = None
        if analyze:
            from .analyzer import analyze as analyze_sentiment

            analyzer_func = analyze_sentiment

        keyword_list = None
        if keywords:
            keyword_list = [k.strip() for k in keywords.split(",")]

        # Parse since window
        since_cutoff = None
        if since:
            since_cutoff = parse_since_window(since)
            if since_cutoff:
                console.print(
                    f"[cyan]Filtering articles since: {since_cutoff.strftime('%Y-%m-%d %H:%M:%S UTC')}[/cyan]"
                )
            else:
                console.print(
                    f"[yellow]Warning: Could not parse --since '{since}', ignoring filter[/yellow]"
                )

        # Wire keywords into connectors that support them
        if keyword_list:
            for conn in connectors:
                if conn.name == "google_news":
                    conn.queries = keyword_list
                elif conn.name == "wikipedia":
                    conn.queries = keyword_list
                elif conn.name == "reddit":
                    # Switch to search mode
                    conn.queries = keyword_list
                    conn.subreddits = []
                elif conn.name == "youtube":
                    conn.search_queries = keyword_list
                elif conn.name == "twitter":
                    # Build search queries
                    conn.queries = [f'"{kw}"' for kw in keyword_list]
                elif conn.name == "gdelt":
                    conn.query = " OR ".join(keyword_list)
                elif conn.name == "mastodon":
                    conn.hashtags = [kw.replace(" ", "") for kw in keyword_list]
                elif conn.name == "stackexchange":
                    conn.queries = keyword_list  # Use search mode instead of tags
                elif conn.name == "bluesky":
                    conn.queries = keyword_list
                elif conn.name == "hackernews_search":
                    conn.queries = keyword_list

        # Collect all articles with metrics
        all_articles = []
        connector_stats = {}
        start_time = time.time()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:

            for conn in connectors:
                task = progress.add_task(f"[cyan]{conn.name}[/cyan]", total=limit)
                conn_start = time.time()

                # Initialize stats for this connector
                stats = {
                    "fetched": 0,
                    "after_keywords": 0,
                    "after_since": 0,
                    "saved": 0,
                    "time_ms": 0,
                    "errors": 0,
                }

                try:
                    async for item in conn.fetch():
                        stats["fetched"] += 1

                        # Apply keyword filter (post-fetch defensive filtering)
                        if keyword_list:
                            if not keyword_match(item, keyword_list):
                                continue
                        stats["after_keywords"] += 1

                        # Apply since filter
                        if since_cutoff and item.get("published_at"):
                            pub_date = item["published_at"]
                            if isinstance(pub_date, str):
                                try:
                                    from dateutil import parser as date_parser

                                    pub_date = date_parser.parse(pub_date)
                                except:
                                    pub_date = None

                            if pub_date and hasattr(pub_date, "replace"):
                                # Make timezone-naive for comparison
                                if hasattr(pub_date, "tzinfo") and pub_date.tzinfo:
                                    pub_date = pub_date.replace(tzinfo=None)

                                if pub_date < since_cutoff.replace(tzinfo=None):
                                    continue
                        stats["after_since"] += 1

                        # Analyze sentiment if requested
                        if analyzer_func and item.get("text"):
                            try:
                                sentiment = analyzer_func(item["text"])
                                item["sentiment"] = sentiment
                            except Exception as e:
                                logger.warning(f"Sentiment analysis failed: {e}")

                        all_articles.append(item)
                        stats["saved"] += 1
                        progress.update(task, advance=1)

                        if stats["saved"] >= limit:
                            break

                    stats["time_ms"] = int((time.time() - conn_start) * 1000)
                    connector_stats[conn.name] = stats

                    progress.update(
                        task,
                        description=f"[green]✓[/green] {conn.name}: {stats['saved']} saved",
                    )

                except Exception as e:
                    stats["errors"] += 1
                    stats["time_ms"] = int((time.time() - conn_start) * 1000)
                    connector_stats[conn.name] = stats
                    console.print(f"[red]Error in {conn.name}: {e}[/red]")
                    progress.update(
                        task, description=f"[red]✗[/red] {conn.name}: failed"
                    )

        total_time = time.time() - start_time

        # Generate comprehensive metrics summary
        console.print(f"\n[bold]📊 Connector Metrics Summary[/bold]")

        # Overall stats
        total_fetched = sum(stats["fetched"] for stats in connector_stats.values())
        total_after_keywords = sum(
            stats["after_keywords"] for stats in connector_stats.values()
        )
        total_after_since = sum(
            stats["after_since"] for stats in connector_stats.values()
        )
        total_saved = sum(stats["saved"] for stats in connector_stats.values())
        total_errors = sum(stats["errors"] for stats in connector_stats.values())

        summary_table = Table(title="Overall Metrics")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Count", style="yellow")
        summary_table.add_column("Rate", style="green")

        summary_table.add_row("Raw Fetched", str(total_fetched), "100.0%")
        if keyword_list:
            keyword_rate = (
                (total_after_keywords / total_fetched * 100) if total_fetched > 0 else 0
            )
            summary_table.add_row(
                "After Keywords", str(total_after_keywords), f"{keyword_rate:.1f}%"
            )
        if since:
            since_rate = (
                (total_after_since / total_after_keywords * 100)
                if total_after_keywords > 0
                else 0
            )
            summary_table.add_row(
                "After Since Filter", str(total_after_since), f"{since_rate:.1f}%"
            )
        summary_table.add_row("Final Saved", str(total_saved), "")
        if total_errors > 0:
            summary_table.add_row("Errors", str(total_errors), "")
        summary_table.add_row("Total Time", f"{total_time:.1f}s", "")

        console.print(summary_table)

        # Per-connector breakdown
        if len(connectors) > 1:
            conn_table = Table(title="Per-Connector Breakdown")
            conn_table.add_column("Connector", style="cyan")
            conn_table.add_column("Fetched", style="yellow")
            if keyword_list:
                conn_table.add_column("Keywords", style="yellow")
            if since:
                conn_table.add_column("Since", style="yellow")
            conn_table.add_column("Saved", style="green")
            conn_table.add_column("Time", style="magenta")

            for name, stats in connector_stats.items():
                row = [name, str(stats["fetched"])]
                if keyword_list:
                    row.append(str(stats["after_keywords"]))
                if since:
                    row.append(str(stats["after_since"]))
                row.extend([str(stats["saved"]), f"{stats['time_ms']}ms"])
                conn_table.add_row(*row)

            console.print(conn_table)

        console.print(
            f"\n[green]✓ Collected {len(all_articles)} articles meeting all criteria[/green]"
        )

        if all_articles:
            # Save results
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = output_path / f"connector_results_{timestamp}.json"

            # Add run metadata and convert datetime objects for JSON serialization
            run_metadata = {
                "run_timestamp": datetime.now().isoformat(),
                "config": {
                    "keywords": keyword_list,
                    "since": since,
                    "limit": limit,
                    "analyze": analyze,
                    "connector_type": connector_type,
                },
                "metrics": {
                    "total_time_sec": total_time,
                    "connectors_used": len(connectors),
                    "total_fetched": total_fetched,
                    "after_keywords": total_after_keywords,
                    "after_since": total_after_since,
                    "final_saved": total_saved,
                    "errors": total_errors,
                    "connector_stats": connector_stats,
                },
                "articles": all_articles,
            }

            for article in all_articles:
                if "published_at" in article and hasattr(
                    article["published_at"], "isoformat"
                ):
                    article["published_at"] = article["published_at"].isoformat()

            with open(output_file, "w") as f:
                json.dump(run_metadata, f, indent=2, default=str)

            console.print(f"[green]Results saved to {output_file}[/green]")

            # Show final source distribution
            if all_articles:
                source_counts = Counter(a["source"] for a in all_articles)

                source_table = Table(title="Final Results by Source")
                source_table.add_column("Source", style="cyan")
                source_table.add_column("Articles", style="green")
                source_table.add_column("Percentage", style="yellow")

                for source, count in source_counts.most_common():
                    percentage = (count / len(all_articles)) * 100
                    source_table.add_row(source, str(count), f"{percentage:.1f}%")

                console.print(source_table)

    # Run async function
    asyncio.run(run_connectors())


@app.command()
def list_connectors():
    """List all available connector types."""

    from .ingest.registry import CONNECTORS

    table = Table(title="Available Connector Types")
    table.add_column("Type", style="cyan")
    table.add_column("Class", style="green")
    table.add_column("Description", style="white")

    for name, cls in sorted(CONNECTORS.items()):
        doc = cls.__doc__ or "No description"
        doc = doc.strip().split("\n")[0]  # First line only
        table.add_row(name, cls.__name__, doc)

    console.print(table)
    console.print(
        "\n[yellow]To use connectors, create config/sources.yaml based on config/sources.example.yaml[/yellow]"
    )


if __name__ == "__main__":
    app()
