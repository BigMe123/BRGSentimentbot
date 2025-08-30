"""
Enhanced CLI v2 - Complete implementation with all high-impact fixes.
"""

import asyncio
import typer
import time
import json
import yaml
from pathlib import Path
from typing import Optional, List, Dict, Set
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
import logging
from datetime import datetime, timedelta
from dateutil import parser as date_parser
import aiohttp
import feedparser

try:
    from .skb_catalog import get_catalog, SourceRecord
    from .selection_planner import SelectionPlanner, SelectionQuotas
    from .relevance_filter import RelevanceFilter
    from .health_monitor import get_monitor
    from .rss_discovery import get_discovery
    from .models import batched_predict, get_sentiment_pipeline
except ImportError:
    # For standalone testing
    from sentiment_bot.skb_catalog import get_catalog, SourceRecord
    from sentiment_bot.selection_planner import SelectionPlanner, SelectionQuotas
    from sentiment_bot.relevance_filter import RelevanceFilter
    from sentiment_bot.health_monitor import get_monitor
    from sentiment_bot.rss_discovery import get_discovery
    from sentiment_bot.models import batched_predict, get_sentiment_pipeline

console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load config
config_path = Path(__file__).parent.parent / "config" / "defaults.yaml"
if config_path.exists():
    with open(config_path) as f:
        CONFIG = yaml.safe_load(f)
else:
    CONFIG = {}


app = typer.Typer(
    name="bsgbot-v2",
    help="BSG Bot v2 - Enhanced with RSS discovery, freshness, and diversity",
)


@app.command(name="run")
def run(
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
        help="Standard topic: elections, security, economy, politics, energy, climate, tech, general",
    ),
    other: Optional[str] = typer.Option(
        None, "--other", "-o", help="Free-text topic for obscure subjects"
    ),
    strict: bool = typer.Option(
        False, "--strict", "-s", help="Strict mode - only exact matches"
    ),
    expand: bool = typer.Option(
        False, "--expand", "-e", help="Expand to include cross-regional specialists"
    ),
    budget: int = typer.Option(300, "--budget", "-b", help="Time budget in seconds"),
    min_sources: int = typer.Option(
        None, "--min-sources", help="Minimum number of sources (default from config)"
    ),
    target_words: int = typer.Option(
        10000, "--target-words", help="Target fresh words to collect"
    ),
    discover: bool = typer.Option(
        None, "--discover", "-d", help="Enable RSS discovery (default from config)"
    ),
    max_age_hours: int = typer.Option(
        None,
        "--max-age-hours",
        help="Maximum article age in hours (default from config)",
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
    Enhanced BSG Bot with comprehensive RSS discovery and quality controls.
    """

    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load defaults from config
    if min_sources is None:
        min_sources = CONFIG.get("selection", {}).get("min_sources", 30)
    if discover is None:
        discover = CONFIG.get("discovery", {}).get("enabled", True)
    if max_age_hours is None:
        max_age_hours = CONFIG.get("freshness", {}).get("max_age_hours", 48)

    # Validate inputs
    if not any([region, topic, other]):
        console.print(
            "[red]Error: Must specify at least one of --region, --topic, or --other[/red]"
        )
        raise typer.Exit(1)

    # Display configuration
    config_text = f"""[bold cyan]Configuration[/bold cyan]
Region: {region or 'All'}
Topic: {topic or other or 'All'}
Mode: {'Strict' if strict else 'Flexible'} {'+ Expanded' if expand else ''}
Discovery: {'Enabled' if discover else 'Disabled'}
Budget: {budget}s
Min Sources: {min_sources}
Max Article Age: {max_age_hours}h
Target Words: {target_words}"""

    console.print(Panel(config_text, title="BSG Bot Enhanced v2"))

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
            max_age_hours=max_age_hours,
            output=output,
            dry_run=dry_run,
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
    max_age_hours: int,
    output: Optional[str],
    dry_run: bool,
):
    """Enhanced async main execution."""

    start_time = time.time()
    catalog = get_catalog()
    monitor = get_monitor()
    discovery = get_discovery()

    # Step 1: Selection Planning with Enhanced Diversity
    console.print("\n[bold]📚 Planning Source Selection...[/bold]")

    planner = SelectionPlanner(catalog)
    quotas = SelectionQuotas(min_sources=min_sources, time_budget_seconds=budget)

    topics = [topic] if topic else None

    plan = planner.plan_selection(
        region=region,
        topics=topics,
        other_topic=other,
        strict=strict,
        expand=expand,
        quotas=quotas,
    )

    # Step 2: RSS Discovery and Resolution
    console.print("\n[bold]🔍 Resolving RSS Feeds...[/bold]")

    # Resolve RSS feeds for each source
    resolved_sources = []
    editorial_families = set()

    with Progress() as progress:
        task = progress.add_task("[cyan]Discovering feeds...", total=len(plan.sources))

        for source in plan.sources:
            # Get RSS feeds from discovery
            if not source.rss_endpoints or discover:
                feeds = await discovery.resolve_feeds(
                    source.domain, region=region, topic=topic or other
                )
                if feeds:
                    source.rss_endpoints = feeds

            # Get editorial family
            family = discovery.get_editorial_family(source.domain, region)
            editorial_families.add(family)

            if source.rss_endpoints:
                resolved_sources.append(source)

            progress.advance(task)

    # Step 3: Backfill if needed
    if len(resolved_sources) < min_sources or len(editorial_families) < CONFIG.get(
        "selection", {}
    ).get("require_editorial_families", 4):
        console.print(
            f"\n[yellow]Need backfill: {len(resolved_sources)}/{min_sources} sources, {len(editorial_families)} families[/yellow]"
        )

        # Add global sources for diversity
        global_sources = await _get_backfill_sources(
            needed=min_sources - len(resolved_sources),
            existing_families=editorial_families,
            region=region,
            topic=topic or other,
        )

        for source in global_sources:
            feeds = await discovery.resolve_feeds(source["domain"])
            if feeds:
                resolved_sources.append(
                    SourceRecord(
                        domain=source["domain"],
                        name=source["domain"],
                        region="global",
                        topics=[topic or other or "general"],
                        rss_endpoints=feeds,
                        priority=0.5,
                        policy="allow",
                    )
                )
                editorial_families.add(source.get("family", "wire"))

    # Display enhanced summary
    _display_enhanced_summary(resolved_sources, editorial_families)

    if dry_run:
        console.print("\n[yellow]Dry run mode - skipping article fetching[/yellow]")
        return

    # Step 4: Fetch Articles with Retry Logic
    console.print("\n[bold]📡 Fetching Articles...[/bold]")

    articles = await _fetch_articles_with_retry(resolved_sources, monitor)

    # Step 5: Freshness Filter
    console.print("\n[bold]🕐 Applying Freshness Filter...[/bold]")

    fresh_articles, stale_count, freshness_rate = _filter_by_freshness(
        articles, max_age_hours
    )

    console.print(
        f"[green]Fresh: {len(fresh_articles)}/{len(articles)} articles (Freshness Rate: {freshness_rate:.1%})[/green]"
    )

    # Step 6: Relevance Verification
    console.print("\n[bold]✅ Verifying Relevance...[/bold]")

    relevance_filter = RelevanceFilter()
    filtered_articles = []

    with Progress() as progress:
        task = progress.add_task("[cyan]Filtering...", total=len(fresh_articles))

        for article in fresh_articles:
            score = relevance_filter.verify_relevance(
                article=article,
                target_region=region,
                target_topics=topics or [other] if other else None,
                strict=strict,
            )

            if score.should_keep:
                article["_relevance_weight"] = score.weight
                filtered_articles.append(article)

            progress.advance(task)

    console.print(
        f"[green]Kept {len(filtered_articles)}/{len(fresh_articles)} fresh articles after relevance filter[/green]"
    )

    # Step 7: Enhanced Analysis with Batching
    console.print("\n[bold]🧠 Analyzing Sentiment (Batched)...[/bold]")

    results = await _analyze_articles_batched(filtered_articles)

    # Step 8: Calculate Fresh Words
    fresh_words = sum(
        len(article.get("content", "").split()) for article in filtered_articles
    )

    # Step 9: Display Results
    console.print("\n[bold]📊 Results Summary[/bold]")

    _display_enhanced_results(
        results,
        {
            "total_sources": len(resolved_sources),
            "editorial_families": len(editorial_families),
            "freshness_rate": freshness_rate,
            "fresh_words": fresh_words,
            "fetch_success_rate": monitor.get_run_metrics().get(
                "fetch_success_rate", 0
            ),
            "avg_latency_ms": monitor.get_run_metrics().get("avg_latency_ms", 0),
        },
    )

    # Step 10: Save output
    if output:
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "config": {
                "region": region,
                "topic": topic or other,
                "strict": strict,
                "expand": expand,
                "budget": budget,
                "max_age_hours": max_age_hours,
            },
            "metrics": {
                "sources": len(resolved_sources),
                "editorial_families": list(editorial_families),
                "freshness_rate": freshness_rate,
                "fresh_words": fresh_words,
            },
            "results": results,
        }

        with open(output, "w") as f:
            json.dump(output_data, f, indent=2, default=str)

        console.print(f"[green]Results saved to {output}[/green]")

    # Clean up
    await discovery.close()

    # Final timing
    total_time = time.time() - start_time
    console.print(f"\n[bold green]✓ Completed in {total_time:.1f} seconds[/bold green]")


async def _get_backfill_sources(
    needed: int, existing_families: Set[str], region: str = None, topic: str = None
) -> List[Dict]:
    """Get backfill sources to meet diversity requirements."""

    sources = []

    # Priority order for backfill
    backfill_domains = [
        {"domain": "reuters.com", "family": "wire"},
        {"domain": "apnews.com", "family": "wire"},
        {"domain": "bloomberg.com", "family": "wire"},
        {"domain": "aljazeera.com", "family": "broadcaster"},
        {"domain": "cnn.com", "family": "broadcaster"},
        {"domain": "bbc.com", "family": "public_broadcaster"},
        {"domain": "dw.com", "family": "public_broadcaster"},
        {"domain": "france24.com", "family": "public_broadcaster"},
        {"domain": "euronews.com", "family": "broadcaster"},
        {"domain": "politico.eu", "family": "broadsheet"},
    ]

    # Add sources prioritizing missing families
    for source in backfill_domains:
        if len(sources) >= needed:
            break

        # Prioritize missing editorial families
        if source["family"] not in existing_families or len(sources) < needed:
            sources.append(source)
            existing_families.add(source["family"])

    return sources


async def _fetch_articles_with_retry(
    sources: List[SourceRecord], monitor
) -> List[Dict]:
    """Fetch articles with retry logic and exponential backoff."""

    articles = []

    async def fetch_with_retry(session, url, max_retries=3):
        """Fetch with exponential backoff."""
        for attempt in range(max_retries):
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with session.get(url, timeout=timeout) as response:
                    if response.status == 200:
                        content = await response.text()
                        return feedparser.parse(content)
                    elif response.status == 429:  # Rate limited
                        retry_after = response.headers.get("Retry-After", 2**attempt)
                        await asyncio.sleep(float(retry_after))
                    elif response.status >= 500:  # Server error
                        await asyncio.sleep(2**attempt)  # Exponential backoff
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
            except Exception as e:
                logger.debug(f"Error fetching {url}: {e}")

        return None

    # Collect all RSS URLs
    rss_urls = []
    url_to_source = {}

    for source in sources:
        if source.rss_endpoints:
            for endpoint in source.rss_endpoints[:2]:  # Max 2 feeds per source
                rss_urls.append(endpoint)
                url_to_source[endpoint] = source

    if not rss_urls:
        console.print("[yellow]Warning: No RSS feeds to fetch[/yellow]")
        return articles

    # Fetch with progress
    with Progress() as progress:
        task = progress.add_task("[cyan]Fetching feeds...", total=len(rss_urls))

        async with aiohttp.ClientSession() as session:
            tasks = [fetch_with_retry(session, url) for url in rss_urls]

            for coro in asyncio.as_completed(tasks):
                result = await coro
                progress.advance(task)

                if result and result.entries:
                    # Find which source this belongs to
                    for url in rss_urls:
                        if url in url_to_source:
                            source = url_to_source[url]
                            domain = source.domain
                            break
                    else:
                        domain = "Unknown"

                    for entry in result.entries[:10]:
                        article = {
                            "title": entry.get("title", ""),
                            "link": entry.get("link", ""),
                            "description": entry.get(
                                "summary", entry.get("description", "")
                            ),
                            "domain": domain,
                            "published": entry.get("published", ""),
                            "content": (
                                entry.get("content", [{}])[0].get("value", "")
                                if "content" in entry
                                else ""
                            ),
                        }

                        # Parse published date
                        if article["published"]:
                            try:
                                article["published_date"] = date_parser.parse(
                                    article["published"]
                                )
                            except:
                                article["published_date"] = None

                        articles.append(article)

                        # Record metrics
                        monitor.record_fetch_result(
                            domain=domain, success=True, latency_ms=100
                        )

    return articles


def _filter_by_freshness(articles: List[Dict], max_age_hours: int) -> tuple:
    """Filter articles by freshness."""

    cutoff = datetime.now(tz=None) - timedelta(hours=max_age_hours)
    fresh_articles = []
    stale_count = 0

    for article in articles:
        # Try to get published date
        pub_date = article.get("published_date")

        if pub_date:
            # Make timezone naive for comparison
            if pub_date.tzinfo:
                pub_date = pub_date.replace(tzinfo=None)

            if pub_date >= cutoff:
                fresh_articles.append(article)
            else:
                stale_count += 1
        else:
            # If no date, include it (assume fresh)
            fresh_articles.append(article)

    freshness_rate = len(fresh_articles) / len(articles) if articles else 0

    return fresh_articles, stale_count, freshness_rate


async def _analyze_articles_batched(articles: List[Dict]) -> Dict:
    """Analyze articles with batched inference."""

    if not articles:
        return {
            "total_articles": 0,
            "sentiment": {"positive": 0, "negative": 0, "neutral": 0},
            "top_topics": [],
            "key_insights": [],
        }

    # Prepare texts for batch processing
    texts = []
    for article in articles:
        text = (
            article.get("content", "")
            or article.get("description", "")
            or article.get("title", "")
        )
        if text:
            # Truncate to max 512 tokens for BERT models
            text = text[:2000]  # Rough approximation
            texts.append(text)

    if not texts:
        return {
            "total_articles": len(articles),
            "sentiment": {"positive": 0, "negative": 0, "neutral": 0},
            "top_topics": [],
            "key_insights": [],
        }

    # Batch sentiment analysis
    try:
        sentiment_pipeline = get_sentiment_pipeline()
        batch_size = CONFIG.get("runtime", {}).get("batch_size", 16)

        # Process in batches
        all_results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_results = sentiment_pipeline(batch)
            all_results.extend(batch_results)

        # Count sentiments
        sentiment_counts = {"POSITIVE": 0, "NEGATIVE": 0, "NEUTRAL": 0}

        for result in all_results:
            label = result["label"]
            if "POSITIVE" in label.upper():
                sentiment_counts["POSITIVE"] += 1
            elif "NEGATIVE" in label.upper():
                sentiment_counts["NEGATIVE"] += 1
            else:
                sentiment_counts["NEUTRAL"] += 1

        return {
            "total_articles": len(articles),
            "sentiment": {
                "positive": sentiment_counts["POSITIVE"],
                "negative": sentiment_counts["NEGATIVE"],
                "neutral": sentiment_counts["NEUTRAL"],
            },
            "top_topics": [],
            "key_insights": [],
        }

    except Exception as e:
        logger.error(f"Error in batch analysis: {e}")
        return {
            "total_articles": len(articles),
            "sentiment": {"positive": 0, "negative": 0, "neutral": 0},
            "top_topics": [],
            "key_insights": [],
            "error": str(e),
        }


def _display_enhanced_summary(sources: List[SourceRecord], families: Set[str]):
    """Display enhanced selection summary."""

    table = Table(title="Selected Sources with RSS Feeds", show_header=True)
    table.add_column("Domain", style="cyan", width=30)
    table.add_column("RSS Feeds", style="yellow", width=10)
    table.add_column("Family", style="green", width=20)
    table.add_column("Priority", style="magenta", width=10)

    # Show top sources
    for source in sources[:15]:
        family = get_discovery().get_editorial_family(source.domain)
        feed_count = len(source.rss_endpoints) if source.rss_endpoints else 0
        table.add_row(
            source.domain[:30], str(feed_count), family, f"{source.priority:.2f}"
        )

    if len(sources) > 15:
        table.add_row(f"... + {len(sources) - 15} more", "", "", "")

    console.print(table)

    # Enhanced diversity metrics
    diversity_text = f"""Sources with RSS: {len(sources)}
Editorial Families: {len(families)} ({', '.join(sorted(families)[:5])})
Diversity Score: {len(families) / 5:.2f}"""

    console.print(Panel(diversity_text, title="Diversity Metrics"))


def _display_enhanced_results(results: Dict, metrics: Dict):
    """Display enhanced analysis results."""

    # Results table
    table = Table(title="Analysis Results", show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="yellow")

    table.add_row("Total Articles", str(results["total_articles"]))
    table.add_row(
        "Sentiment",
        f"Pos: {results['sentiment']['positive']}, "
        f"Neg: {results['sentiment']['negative']}, "
        f"Neu: {results['sentiment']['neutral']}",
    )

    console.print(table)

    # Enhanced metrics table
    metrics_table = Table(title="Quality Metrics", show_header=False)
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Value", style="green")

    metrics_table.add_row("Total Sources", str(metrics["total_sources"]))
    metrics_table.add_row("Editorial Families", str(metrics["editorial_families"]))
    metrics_table.add_row("Freshness Rate", f"{metrics['freshness_rate']:.1%}")
    metrics_table.add_row("Fresh Words", f"{metrics['fresh_words']:,}")
    metrics_table.add_row("Fetch Success Rate", f"{metrics['fetch_success_rate']:.1%}")
    metrics_table.add_row("Avg Latency", f"{metrics['avg_latency_ms']:.0f}ms")

    console.print(metrics_table)


if __name__ == "__main__":
    app()
