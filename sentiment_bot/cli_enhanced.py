"""Enhanced CLI commands with HTML crawling and threshold-based gathering."""

import asyncio
import typer
from rich.console import Console
from typing import Optional

from .fetcher_enhanced import enhanced_gather_all_sources
from .analyzer import analyze, aggregate, display_analysis_results

app = typer.Typer(help="Enhanced bot with HTML crawling and anti-bot features")
console = Console()


@app.command()
def enhanced(
    topic: Optional[str] = typer.Option(
        None,
        "--topic",
        "-t",
        help="Topic filter (e.g., 'elections', 'energy')",
    ),
    region: Optional[str] = typer.Option(
        None,
        "--region",
        "-r",
        help="Region filter (e.g., 'asia', 'europe')",
    ),
    use_thresholds: bool = typer.Option(
        True,
        "--thresholds/--no-thresholds",
        help="Use volatility/certainty thresholds",
    ),
    sources_file: str = typer.Option(
        "sources.txt",
        "--sources",
        "-s",
        help="Path to mixed sources file",
    ),
) -> None:
    """
    Run enhanced fetcher with HTML crawling and threshold enforcement.
    
    Features:
    - Mixed RSS/HTML sources from sources.txt
    - HTML crawling with pagination
    - Topic/region filtering
    - Threshold-based infinite scaling
    - Advanced anti-bot with detailed logging
    - Deduplication and quality checks
    """
    
    async def _main():
        console.print("\n[bold cyan]🚀 Enhanced Bot with HTML Crawling[/bold cyan]\n")
        
        # Load and gather articles
        articles, stats = await enhanced_gather_all_sources(
            topic_filter=topic,
            region_filter=region,
            use_thresholds=use_thresholds
        )
        
        if not articles:
            console.print("[red]No articles found matching criteria[/red]")
            return
        
        # Analyze articles
        console.print(f"\n[cyan]Analyzing {len(articles)} articles...[/cyan]")
        analyses = [analyze(art.text) for art in articles]
        snapshot = aggregate(analyses)
        
        # Display results
        console.print("\n[bold green]Analysis Results:[/bold green]")
        console.print(f"Volatility: {snapshot.volatility:.3f}")
        console.print(f"Confidence: {snapshot.confidence:.3f}")
        
        if stats.get("iterations"):
            console.print(f"Iterations to meet thresholds: {stats['iterations']}")
        
        console.print(f"\nTotal articles: {stats.get('total_articles', len(articles))}")
        console.print(f"Unique domains: {stats.get('unique_domains', 0)}")
        console.print(f"Average word count: {stats.get('avg_word_count', 0):.0f}")
        
        # Show top volatile articles
        if articles:
            console.print("\n[cyan]Top Volatile Articles:[/cyan]")
            article_volatilities = []
            for art, res in zip(articles[:10], analyses[:10]):
                vol = (abs(res.vader) + abs(res.bert)) / 2
                article_volatilities.append((vol, art))
            
            for vol, art in sorted(article_volatilities, key=lambda x: x[0], reverse=True)[:5]:
                status_icon = "✅" if art.word_count > 100 else "⚠️"
                console.print(
                    f"[{status_icon}] {art.source_domain} ({art.source_type}) - "
                    f"{art.word_count} words - Volatility: {vol:.3f}"
                )
                if art.title:
                    console.print(f"    Title: {art.title[:80]}...")
        
        # Show fetch method distribution
        if articles:
            methods = {}
            for art in articles:
                methods[art.fetch_method] = methods.get(art.fetch_method, 0) + 1
            
            console.print("\n[cyan]Fetch Methods Used:[/cyan]")
            for method, count in methods.items():
                console.print(f"  {method}: {count} articles")
    
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()


@app.command()
def test() -> None:
    """Test enhanced features with detailed output."""
    
    async def _test():
        from .fetcher_enhanced import (
            enhanced_fetch_url,
            crawl_html,
            CrawlConfig,
            load_mixed_sources
        )
        
        console.print("[bold cyan]Testing Enhanced Features[/bold cyan]\n")
        
        # Test 1: Enhanced fetch
        console.print("[yellow]1. Testing enhanced fetch with anti-bot[/yellow]")
        result = await enhanced_fetch_url("https://www.reuters.com")
        if result.success:
            console.print(f"   ✅ Success - Method: {result.method}, Size: {len(result.content)} bytes")
        else:
            console.print(f"   ❌ Failed: {result.error}")
        
        # Test 2: HTML crawling
        console.print("\n[yellow]2. Testing HTML crawler[/yellow]")
        config = CrawlConfig(max_pages=1, max_depth=0)
        articles = await crawl_html("https://www.reuters.com/world", config=config)
        console.print(f"   ✅ Found {len(articles)} articles")
        
        # Test 3: Mixed sources
        console.print("\n[yellow]3. Testing mixed sources loading[/yellow]")
        sources = await load_mixed_sources()
        console.print(f"   ✅ Loaded {len(sources['RSS'])} RSS, {len(sources['HTML'])} HTML sources")
        
        console.print("\n[green]All tests passed![/green]")
    
    try:
        asyncio.run(_test())
    except Exception as e:
        console.print(f"[red]Test failed: {e}[/red]")


if __name__ == "__main__":
    app()