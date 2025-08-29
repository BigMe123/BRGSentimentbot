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
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.live import Live
import logging
from datetime import datetime

from .skb_catalog import get_catalog
from .selection_planner import SelectionPlanner, SelectionQuotas
from .source_discovery import SourceDiscovery
from .relevance_filter import RelevanceFilter
from .health_monitor import get_monitor
from .smart_selector import SmartSelector
import feedparser
import aiohttp
import asyncio
from .analyzer import analyze
from dateutil import parser as date_parser
import hashlib

app = typer.Typer(
    name="bsgbot",
    help="BSG Bot - Massive SKB with intelligent source selection and analysis"
)
console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.command()
def run(
    region: Optional[str] = typer.Option(None, "--region", "-r", 
        help="Target region: asia, middle_east, europe, americas, africa"),
    topic: Optional[str] = typer.Option(None, "--topic", "-t",
        help="Standard topic: elections, security, economy, politics, energy, climate, tech"),
    other: Optional[str] = typer.Option(None, "--other", "-o",
        help="Free-text topic for obscure subjects (triggers fuzzy matching and discovery)"),
    strict: bool = typer.Option(False, "--strict", "-s",
        help="Strict mode - only exact matches"),
    expand: bool = typer.Option(False, "--expand", "-e",
        help="Expand to include cross-regional specialists"),
    budget: int = typer.Option(300, "--budget", "-b",
        help="Time budget in seconds (default: 5 minutes)"),
    min_sources: int = typer.Option(30, "--min-sources",
        help="Minimum number of sources to fetch"),
    target_words: int = typer.Option(10000, "--target-words",
        help="Target fresh words to collect"),
    discover: bool = typer.Option(False, "--discover", "-d",
        help="Enable active source discovery for obscure topics"),
    output: Optional[str] = typer.Option(None, "--output", "-f",
        help="Output file for results (JSON format)"),
    debug: bool = typer.Option(False, "--debug",
        help="Enable debug logging"),
    dry_run: bool = typer.Option(False, "--dry-run",
        help="Plan only, don't fetch articles"),
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
        console.print("[red]Error: Must specify at least one of --region, --topic, or --other[/red]")
        raise typer.Exit(1)
    
    if topic and other:
        console.print("[yellow]Warning: Both --topic and --other specified, using --topic[/yellow]")
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
    asyncio.run(_run_async(
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
        dry_run=dry_run
    ))


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
    dry_run: bool
):
    """Async main execution."""
    
    start_time = time.time()
    catalog = get_catalog()
    monitor = get_monitor()
    
    # Step 1: Selection Planning
    console.print("\n[bold]📚 Planning Source Selection...[/bold]")
    
    planner = SelectionPlanner(catalog)
    quotas = SelectionQuotas(
        min_sources=min_sources,
        time_budget_seconds=budget
    )
    
    # Handle topic resolution
    topics = [topic] if topic else None
    
    plan = planner.plan_selection(
        region=region,
        topics=topics,
        other_topic=other,
        strict=strict,
        expand=expand,
        quotas=quotas
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
            time_budget=plan.time_allocations.get('_discovery', 30)
        )
        
        # Add discovered sources to plan
        for disc_source in discovery_sources[:20]:  # Limit additions
            plan.sources.append(disc_source)
        
        console.print(f"[green]Added {len(discovery_sources)} discovered sources[/green]")
    
    if dry_run:
        console.print("\n[yellow]Dry run mode - skipping article fetching[/yellow]")
        return
    
    # Step 2: Fetch Articles
    console.print("\n[bold]📡 Fetching Articles...[/bold]")
    
    articles = await _fetch_articles(plan, monitor)
    
    # Step 2.5: Deduplication
    console.print(f"\n[bold]🔄 Deduplicating Articles...[/bold]")
    unique_articles = _deduplicate_articles(articles)
    console.print(f"[green]Kept {len(unique_articles)}/{len(articles)} unique articles[/green]")
    
    # Step 2.6: Freshness Filtering
    console.print(f"\n[bold]🕐 Applying Freshness Filter (max age: 24h)...[/bold]")
    fresh_articles, stale_count, freshness_rate = _filter_by_freshness(unique_articles, max_age_hours=24)
    console.print(f"[green]Fresh: {len(fresh_articles)}/{len(unique_articles)} articles (Freshness Rate: {freshness_rate:.1%})[/green]")
    
    # Calculate fresh words
    fresh_words = sum(len(article.get('content', article.get('description', '')).split()) for article in fresh_articles)
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
                strict=strict
            )
            
            if score.should_keep:
                article['_relevance_weight'] = score.weight
                filtered_articles.append(article)
                
                # Record relevance metrics
                monitor.record_relevance(
                    domain=article.get('domain', 'unknown'),
                    relevance_score=score.weight,
                    dropped=False
                )
            else:
                monitor.record_relevance(
                    domain=article.get('domain', 'unknown'),
                    relevance_score=score.weight,
                    dropped=True
                )
            
            progress.advance(task)
    
    console.print(f"[green]Kept {len(filtered_articles)}/{len(fresh_articles)} relevant articles[/green]")
    
    # Step 4: Analysis
    console.print("\n[bold]🧠 Analyzing Sentiment...[/bold]")
    
    results = await _analyze_articles(filtered_articles)
    
    # Add freshness metrics to results
    results['freshness_rate'] = freshness_rate
    results['fresh_words'] = fresh_words
    
    # Step 5: Auto-tune sources
    console.print("\n[bold]⚙️ Auto-tuning Sources...[/bold]")
    
    tune_actions = monitor.auto_tune_sources(dry_run=False)
    if any(tune_actions.values()):
        _display_tuning_actions(tune_actions)
    
    # Step 6: Display Results
    console.print("\n[bold]📊 Results Summary[/bold]")
    
    _display_results(results, monitor.get_run_metrics())
    
    # Step 7: Save output if requested
    if output:
        output_data = {
            'timestamp': datetime.now().isoformat(),
            'config': {
                'region': region,
                'topic': topic or other,
                'strict': strict,
                'expand': expand,
                'budget': budget
            },
            'plan': {
                'sources_selected': len(plan.sources),
                'diversity_score': plan.get_diversity_score(),
                'selection_time_ms': plan.selection_time_ms
            },
            'results': results,
            'metrics': monitor.export_metrics()
        }
        
        with open(output, 'w') as f:
            json.dump(output_data, f, indent=2, default=str)
        
        console.print(f"[green]Results saved to {output}[/green]")
    
    # Final timing
    total_time = time.time() - start_time
    console.print(f"\n[bold green]✓ Completed in {total_time:.1f} seconds[/bold green]")


async def _run_discovery(topic: str, region: Optional[str], time_budget: float) -> List:
    """Run source discovery for obscure topics."""
    
    discovery = SourceDiscovery(
        max_concurrent=5,
        timeout=10,
        max_domains=20,
        max_pages=50
    )
    
    results = await discovery.discover_sources(
        topic=topic,
        region=region,
        time_budget=time_budget
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
                policy="allow"
            )
            sources.append(source)
    
    return sources


async def _fetch_single_rss(session, url):
    """Fetch single RSS feed."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
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
            for endpoint in source.rss_endpoints[:1]:  # Limit to 1 endpoint per source to avoid overload
                rss_urls.append(endpoint)
                logger.info(f"Added RSS endpoint: {endpoint}")
    
    if not rss_urls:
        console.print("[yellow]Warning: No RSS feeds found for selected sources[/yellow]")
        return articles
    
    with Progress() as progress:
        task = progress.add_task(
            "[cyan]Fetching RSS feeds...", 
            total=len(rss_urls)
        )
        
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
                    domain = feed.feed.get('title', 'Unknown') if hasattr(feed, 'feed') else 'Unknown'
                    
                    # Smart fetch limit based on source quality
                    fetch_limit = 25  # Default increased from 10
                    for entry in feed.entries[:fetch_limit]:
                        # Extract article data
                        # Parse published date for freshness
                        published_str = entry.get('published', entry.get('updated', ''))
                        published_date = None
                        if published_str:
                            try:
                                published_date = date_parser.parse(published_str)
                            except:
                                pass
                        
                        article = {
                            'title': entry.get('title', ''),
                            'link': entry.get('link', ''),
                            'description': entry.get('summary', entry.get('description', '')),
                            'domain': domain,
                            'published': published_str,
                            'published_date': published_date,
                            'content': entry.get('content', [{}])[0].get('value', '') if 'content' in entry else '',
                            'url_hash': hashlib.md5(entry.get('link', '').encode()).hexdigest()  # For dedup
                        }
                        
                        # Record fetch metrics
                        monitor.record_fetch_result(
                            domain=domain,
                            success=True,
                            latency_ms=100  # Placeholder
                        )
                        
                        articles.append(article)
                else:
                    # Record failure metrics
                    monitor.record_fetch_result(
                        domain=url.split('/')[2] if '/' in url else 'unknown',
                        success=False,
                        latency_ms=100
                    )
    
    return articles


async def _analyze_articles(articles: List[Dict]) -> Dict:
    """Analyze article sentiment."""
    
    if not articles:
        return {
            'total_articles': 0,
            'sentiment': {'positive': 0, 'negative': 0, 'neutral': 0},
            'top_topics': [],
            'key_insights': []
        }
    
    # Analyze each article individually
    analysis_results = []
    for article in articles:
        # Get the text content from the article
        text = article.get('content', '') or article.get('description', '') or article.get('title', '')
        
        if text:
            # Analyze the text content
            analysis = analyze(text)
            
            # Create result dict with the analysis
            result = {
                'title': article.get('title', 'Untitled'),
                'sentiment_label': 'POSITIVE' if analysis.vader > 0.05 else ('NEGATIVE' if analysis.vader < -0.05 else 'NEUTRAL'),
                'sentiment_score': analysis.vader
            }
            analysis_results.append(result)
    
    # Calculate aggregate sentiment score (-100 to +100)
    if analysis_results:
        avg_sentiment = sum(a['sentiment_score'] for a in analysis_results) / len(analysis_results)
        # Convert from -1 to 1 scale to -100 to +100 scale
        aggregate_score = round(avg_sentiment * 100)
    else:
        aggregate_score = 0
    
    # Format results for display
    results = {
        'total_articles': len(articles),
        'sentiment_score': aggregate_score,  # Single aggregate score
        'sentiment': {
            'positive': sum(1 for a in analysis_results if a['sentiment_label'] == 'POSITIVE'),
            'negative': sum(1 for a in analysis_results if a['sentiment_label'] == 'NEGATIVE'),
            'neutral': sum(1 for a in analysis_results if a['sentiment_label'] == 'NEUTRAL')
        },
        'top_topics': [],
        'key_insights': []
    }
    
    # Extract key insights from highly positive/negative articles
    for article in analysis_results:
        if article['sentiment_score'] > 0.8 or article['sentiment_score'] < -0.8:
            results['key_insights'].append({
                'title': article['title'],
                'sentiment': article['sentiment_label'],
                'score': article['sentiment_score']
            })
    
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
            source.domain[:30],
            f"{source.priority:.2f}",
            topics_str[:30],
            source.policy
        )
    
    if len(plan.sources) > 15:
        table.add_row(
            f"... + {len(plan.sources) - 15} more",
            "",
            "",
            ""
        )
    
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
    
    if actions['promoted']:
        console.print(f"[green]↑ Promoted: {', '.join(actions['promoted'][:5])}[/green]")
    
    if actions['demoted']:
        console.print(f"[yellow]↓ Demoted: {', '.join(actions['demoted'][:5])}[/yellow]")
    
    if actions['parked']:
        console.print(f"[red]✗ Parked: {', '.join(actions['parked'][:5])}[/red]")


def _display_results(results: Dict, metrics: Dict):
    """Display analysis results."""
    
    # Results table
    table = Table(title="Analysis Results", show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="yellow")
    
    table.add_row("Total Articles", str(results['total_articles']))
    
    # Display sentiment score with color based on value
    score = results.get('sentiment_score', 0)
    if score > 20:
        score_style = "[green]"
    elif score < -20:
        score_style = "[red]"
    else:
        score_style = "[yellow]"
    
    table.add_row("Sentiment Score", f"{score_style}{score:+d}[/]")
    table.add_row("Breakdown", f"Pos: {results['sentiment']['positive']}, "
                               f"Neg: {results['sentiment']['negative']}, "
                               f"Neu: {results['sentiment']['neutral']}")
    
    console.print(table)
    
    # Metrics table
    if metrics:
        metrics_table = Table(title="Run Metrics", show_header=False)
        metrics_table.add_column("Metric", style="cyan")
        metrics_table.add_column("Value", style="green")
        
        metrics_table.add_row("Fetch Success Rate", f"{metrics.get('fetch_success_rate', 0):.1%}")
        metrics_table.add_row("Freshness Rate", f"{metrics.get('freshness_rate', 0):.1%}")
        metrics_table.add_row("Fresh Words", f"{metrics.get('fresh_words', 0):,}")
        metrics_table.add_row("Avg Latency", f"{metrics.get('avg_latency_ms', 0):.0f}ms")
        
        console.print(metrics_table)


def _deduplicate_articles(articles: List[Dict]) -> List[Dict]:
    """Remove duplicate articles based on URL hash."""
    seen_hashes = set()
    unique_articles = []
    
    for article in articles:
        url_hash = article.get('url_hash') or hashlib.md5(article.get('link', '').encode()).hexdigest()
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
        pub_date = article.get('published_date')
        
        if pub_date:
            # Make timezone naive for comparison if needed
            if hasattr(pub_date, 'tzinfo') and pub_date.tzinfo:
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
    force: bool = typer.Option(False, "--force", "-f", help="Force reimport")
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
        
        console.print(f"[green]✓ Successfully imported {stats['total_sources']} sources[/green]")
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
    
    table.add_row("Total Sources", str(stats['total_sources']))
    table.add_row("Active Sources", str(stats['active_sources']))
    table.add_row("Staging Sources", str(stats['staging_sources']))
    table.add_row("Parked Sources", str(stats['parked_sources']))
    table.add_row("Avg Reliability", f"{stats['avg_reliability']:.2f}")
    table.add_row("Avg Yield", f"{stats['avg_yield']:.0f} words")
    
    console.print(table)
    
    # Region distribution
    if stats['regions']:
        region_table = Table(title="Sources by Region", show_header=True)
        region_table.add_column("Region", style="cyan")
        region_table.add_column("Count", style="yellow")
        
        for region, count in sorted(stats['regions'].items(), key=lambda x: x[1], reverse=True):
            region_table.add_row(region, str(count))
        
        console.print(region_table)
    
    # Top topics
    if stats['topics']:
        topic_table = Table(title="Top Topics", show_header=True)
        topic_table.add_column("Topic", style="green")
        topic_table.add_column("Sources", style="yellow")
        
        for topic, count in list(stats['topics'].items())[:10]:
            topic_table.add_row(topic, str(count))
        
        console.print(topic_table)


@app.command()
def health(
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Specific domain to check"),
    export: Optional[str] = typer.Option(None, "--export", "-e", help="Export metrics to JSON file")
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
            console.print("[yellow]No health metrics available yet. Run an analysis first.[/yellow]")
            return
        
        table = Table(title="Overall Health Metrics", show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="yellow")
        
        table.add_row("Total Sources", str(metrics.get('total_sources', 0)))
        table.add_row("Fetch Success Rate", f"{metrics.get('fetch_success_rate', 0):.1%}")
        table.add_row("Freshness Rate", f"{metrics.get('freshness_rate', 0):.1%}")
        table.add_row("Avg Latency", f"{metrics.get('avg_latency_ms', 0):.0f}ms")
        
        console.print(table)
        
        # Health distribution
        if 'sources_by_health' in metrics:
            health_table = Table(title="Sources by Health", show_header=True)
            health_table.add_column("Category", style="cyan")
            health_table.add_column("Count", style="yellow")
            
            for category, count in metrics['sources_by_health'].items():
                health_table.add_row(category.capitalize(), str(count))
            
            console.print(health_table)
    
    if export:
        all_metrics = monitor.export_metrics()
        with open(export, 'w') as f:
            json.dump(all_metrics, f, indent=2, default=str)
        console.print(f"[green]Metrics exported to {export}[/green]")


if __name__ == "__main__":
    app()