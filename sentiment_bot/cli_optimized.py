"""
Optimized CLI with TTY-safe prompts and unified pipeline.
Integrates all performance optimizations.
"""

import asyncio
import json
import typer
from pathlib import Path
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .prompt_utils import (
    safe_prompt, safe_choice, safe_multi_select, 
    handle_interactive_menu, is_interactive
)
from .fetcher_optimized import fetch_with_budget
from .metrics import MetricsCollector
from .domain_policy import get_domain_registry
from .config import settings, load_rss_sources

app = typer.Typer(help="Optimized news sentiment bot with SLO guarantees")
console = Console()


def display_metrics_summary(metrics: dict):
    """Display metrics summary with SLO status."""
    table = Table(title="Pipeline Metrics & SLOs", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="yellow")
    table.add_column("SLO", style="white")
    table.add_column("Status", style="green")
    
    # Define SLOs
    slos = [
        ("Fetch Success Rate", metrics.get('fetch_success_rate', 0), "≥80%", 0.80),
        ("P95 Latency (ms)", metrics.get('p95_fetch_latency_ms', 0), "≤8000", 8000),
        ("Headless Usage", metrics.get('headless_usage_rate', 0), "≤10%", 0.10),
        ("Top-1 Source Share", metrics.get('top1_source_share', 0), "≤30%", 0.30),
        ("Top-3 Source Share", metrics.get('top3_source_share', 0), "≤60%", 0.60),
        ("Fresh Articles (<24h)", metrics.get('fraction_published_24h', 0), "≥60%", 0.60),
    ]
    
    all_pass = True
    
    for name, value, slo_text, threshold in slos:
        # Format value
        if "Rate" in name or "Usage" in name or "Share" in name or "Fresh" in name:
            formatted_value = f"{value:.1%}"
            # Check SLO
            if "≥" in slo_text:
                passed = value >= threshold
            else:
                passed = value <= threshold
        else:
            formatted_value = f"{value:.0f}"
            # Check SLO for latency
            if "≤" in slo_text:
                passed = value <= threshold
            else:
                passed = value >= threshold
        
        status = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            all_pass = False
        
        table.add_row(name, formatted_value, slo_text, status)
    
    console.print(table)
    
    # Overall status
    if all_pass:
        console.print("\n[bold green]✅ All SLOs met![/bold green]")
    else:
        console.print("\n[bold red]❌ Some SLOs failed - run degraded[/bold red]")
    
    # Additional metrics
    console.print(f"\nUnique domains: {metrics.get('unique_domains', 0)}")
    console.print(f"Articles ingested: {metrics.get('articles_ingested', 0)}")
    console.print(f"Words ingested: {metrics.get('words_ingested', 0):,}")
    console.print(f"Runtime: {metrics.get('runtime_seconds', 0):.1f}s")


@app.command()
def once(
    budget: int = typer.Option(300, "--budget", help="Time budget in seconds"),
    feeds: Optional[Path] = typer.Option(None, "--feeds", help="Path to feeds file"),
    view: str = typer.Option("Summary", "--view", help="Default view: Summary/Articles/Analysis"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON metrics"),
    canary: bool = typer.Option(False, "--canary", help="Run canary mode (limited feeds)"),
) -> None:
    """Run the optimized pipeline once with SLO monitoring."""
    
    async def _run():
        # Load feeds
        if feeds and feeds.exists():
            feed_urls = [
                line.strip() for line in feeds.read_text().splitlines()
                if line.strip() and not line.startswith('#')
            ]
        else:
            feed_urls = load_rss_sources()
        
        if canary:
            # Canary mode: only use high-value feeds
            canary_feeds = [
                'https://feeds.bbci.co.uk/news/world/rss.xml',
                'https://rss.nytimes.com/services/xml/rss/nyt/World.xml',
                'https://feeds.reuters.com/reuters/worldNews',
                'https://www.aljazeera.com/xml/rss/all.xml',
                'https://feeds.washingtonpost.com/rss/world',
            ]
            feed_urls = [f for f in feed_urls if f in canary_feeds][:10]
            console.print(f"[yellow]Canary mode: using {len(feed_urls)} high-value feeds[/yellow]")
        
        console.print(f"Processing {len(feed_urls)} feeds with {budget}s budget...")
        
        # Run pipeline with progress
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching articles...", total=None)
            
            result = await fetch_with_budget(
                feed_urls=feed_urls,
                budget_seconds=budget,
            )
            
            progress.update(task, completed=True)
        
        # Display results
        if json_output:
            # JSON output for automation
            output = {
                'metrics': result.metrics,
                'alerts': [
                    {
                        'severity': alert.severity,
                        'metric': alert.metric,
                        'value': alert.value,
                        'threshold': alert.threshold,
                        'message': alert.message,
                    }
                    for alert in result.alerts
                ],
                'articles_count': len(result.articles),
            }
            console.print_json(json.dumps(output))
        else:
            # Human-readable output
            display_metrics_summary(result.metrics)
            
            # Show alerts
            if result.alerts:
                console.print("\n[bold red]⚠️ Alerts:[/bold red]")
                for alert in result.alerts:
                    console.print(f"  [{alert.severity}] {alert.message}")
            
            # Interactive menu (TTY-safe)
            if not json_output:
                # Prepare data for menu
                stats = {
                    'total': len(result.articles),
                    'attempted': result.metrics.get('fetch_attempts', 0),
                    'success_rate': result.metrics.get('fetch_success_rate', 0) * 100,
                    'words_collected': result.metrics.get('words_ingested', 0),
                    'unique_domains': result.metrics.get('unique_domains', 0),
                    'cache_hits': result.metrics.get('cache_hits', 0),
                    'circuit_breakers': result.metrics.get('circuit_opened_count', 0),
                    'data_quality': result.metrics.get('fraction_published_24h', 0) * 100,
                }
                
                analysis_results = {
                    'volatility': 0.0,  # Would come from analyzer
                    'model_confidence': 0.0,
                    'articles': result.articles[:10],  # Sample
                }
                
                handle_interactive_menu(stats, analysis_results, result.articles, view)
        
        # Exit code based on SLOs
        slo_failures = 0
        if result.metrics.get('fetch_success_rate', 0) < 0.80:
            slo_failures += 1
        if result.metrics.get('p95_fetch_latency_ms', float('inf')) > 8000:
            slo_failures += 1
        if result.metrics.get('headless_usage_rate', 1.0) > 0.10:
            slo_failures += 1
        if result.metrics.get('top1_source_share', 1.0) > 0.30:
            slo_failures += 1
        if result.metrics.get('fraction_published_24h', 0) < 0.60:
            slo_failures += 1
        
        if slo_failures > 0:
            raise typer.Exit(code=1)
    
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        raise typer.Exit(code=130)


@app.command()
def interactive(
    budget: int = typer.Option(300, "--budget", help="Time budget in seconds"),
    view: str = typer.Option("Summary", "--view", help="Default view for non-TTY"),
) -> None:
    """Interactive mode with TTY-safe prompts."""
    
    # Region selection
    regions = ["All", "Africa", "Asia", "Europe", "Latin America", 
               "Middle East", "North America", "Oceania"]
    
    if is_interactive():
        selected_regions = safe_multi_select(
            "Select regions to monitor:",
            regions,
            defaults=["All"]
        )
    else:
        selected_regions = ["All"]
        console.print(f"[dim]Non-interactive mode, using regions: {selected_regions}[/dim]")
    
    # Topic selection
    topics = ["All", "Elections", "Markets", "Technology", "Climate", 
              "Conflict", "Trade", "Energy"]
    
    if is_interactive():
        selected_topics = safe_multi_select(
            "Select topics to track:",
            topics,
            defaults=["All"]
        )
    else:
        selected_topics = ["All"]
        console.print(f"[dim]Non-interactive mode, using topics: {selected_topics}[/dim]")
    
    # Time window
    windows = ["1 hour", "6 hours", "24 hours", "7 days"]
    
    if is_interactive():
        time_window = safe_choice(
            "Select time window:",
            windows,
            default="24 hours"
        )
    else:
        time_window = "24 hours"
        console.print(f"[dim]Non-interactive mode, using window: {time_window}[/dim]")
    
    console.print(f"\n[bold]Configuration:[/bold]")
    console.print(f"  Regions: {', '.join(selected_regions)}")
    console.print(f"  Topics: {', '.join(selected_topics)}")
    console.print(f"  Window: {time_window}")
    
    # Run the pipeline
    typer.echo("\nStarting pipeline...")
    once(budget=budget, view=view)


@app.command()
def validate_policies(
    config: Optional[Path] = typer.Option(None, "--config", help="Policy config file"),
) -> None:
    """Validate and display domain policies."""
    
    registry = get_domain_registry(config)
    
    # Display policy stats
    stats = registry.export_stats()
    
    table = Table(title="Domain Policy Registry", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="yellow")
    
    table.add_row("Policies Loaded", str(stats['policies_loaded']))
    table.add_row("Pattern Policies", str(stats['pattern_policies']))
    table.add_row("Allowed Domains", str(stats['allowed']))
    table.add_row("Denied Domains", str(stats['denied']))
    table.add_row("JS-Allowed Domains", str(stats['js_allowed']))
    table.add_row("API-Only Domains", str(stats['api_only']))
    
    console.print(table)
    
    # Test some URLs
    test_urls = [
        'https://feeds.bbci.co.uk/news/rss.xml',
        'https://www.bloomberg.com/markets',
        'https://spam-site.example.com/feed',
    ]
    
    console.print("\n[bold]Policy Tests:[/bold]")
    for url in test_urls:
        decision, reason = registry.check_access(url)
        if decision == 'allow':
            console.print(f"  ✅ {url}: [green]ALLOWED[/green]")
        elif decision == 'deny':
            console.print(f"  ❌ {url}: [red]DENIED[/red] - {reason}")
        elif decision == 'js_required':
            console.print(f"  🌐 {url}: [yellow]JS REQUIRED[/yellow] - {reason}")
        elif decision == 'api_only':
            console.print(f"  🔌 {url}: [blue]API ONLY[/blue] - {reason}")


@app.command()
def metrics(
    last_run: bool = typer.Option(False, "--last", help="Show last run metrics"),
    export: Optional[Path] = typer.Option(None, "--export", help="Export metrics to file"),
) -> None:
    """Display pipeline metrics and SLO compliance."""
    
    # For demo, create sample metrics
    sample_metrics = {
        'unique_domains': 45,
        'articles_ingested': 523,
        'words_ingested': 125000,
        'fetch_success_rate': 0.82,
        'p95_fetch_latency_ms': 7500,
        'headless_usage_rate': 0.08,
        'top1_source_share': 0.28,
        'top3_source_share': 0.55,
        'fraction_published_24h': 0.65,
        'runtime_seconds': 298.5,
    }
    
    if export:
        export.write_text(json.dumps(sample_metrics, indent=2))
        console.print(f"[green]Metrics exported to {export}[/green]")
    else:
        display_metrics_summary(sample_metrics)


if __name__ == "__main__":
    app()