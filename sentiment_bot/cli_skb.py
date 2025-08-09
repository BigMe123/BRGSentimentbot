"""
Enhanced CLI with Source Knowledge Base (SKB) integration.
Uses intelligent source selection and relevance filtering.
"""

import asyncio
import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import logging

from .source_selector import SourceSelector
from .relevance_filter import RelevanceFilter
from .fetcher_enhanced import enhanced_gather_all_sources, ArticleData
from .analyzer import analyze

app = typer.Typer(help="Sentiment bot with intelligent source selection")
console = Console()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.command()
def analyze(
    region: Optional[str] = typer.Option(None, "--region", help="Target region (asia, middle_east, europe, americas, africa)"),
    topic: Optional[str] = typer.Option(None, "--topic", help="Target topic (elections, security, economy, politics, energy, climate, tech)"),
    strict: bool = typer.Option(False, "--strict", help="Strict mode - only exact matches"),
    expand: bool = typer.Option(False, "--expand", help="Expand to include global specialists"),
    discover: bool = typer.Option(False, "--discover", help="Enable active source discovery"),
    budget: int = typer.Option(300, "--budget", help="Time budget in seconds"),
    min_sources: int = typer.Option(30, "--min-sources", help="Minimum number of sources"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug output"),
) -> None:
    """
    Analyze news with intelligent source selection and relevance filtering.
    
    Examples:
        poetry run python -m sentiment_bot.cli_skb analyze --region asia --topic elections
        poetry run python -m sentiment_bot.cli_skb analyze --region middle_east --strict
        poetry run python -m sentiment_bot.cli_skb analyze --topic energy --expand
    """
    
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Display configuration
    console.print(Panel.fit(
        f"[bold cyan]Configuration[/bold cyan]\n"
        f"Region: {region or 'All'}\n"
        f"Topic: {topic or 'All'}\n"
        f"Mode: {'Strict' if strict else 'Flexible'}\n"
        f"Expand: {expand}\n"
        f"Budget: {budget}s\n"
        f"Min Sources: {min_sources}",
        title="SKB Analysis"
    ))
    
    async def run_analysis():
        # Initialize components
        selector = SourceSelector()
        relevance_filter = RelevanceFilter()
        
        # Select sources
        console.print("\n[bold]📚 Selecting Sources...[/bold]")
        plan = selector.select_sources(
            region=region,
            topic=topic,
            strict=strict,
            expand=expand,
            min_sources=min_sources,
            budget_seconds=budget
        )
        
        # Display selected sources
        table = Table(title="Selected Sources", show_header=True)
        table.add_column("Domain", style="cyan")
        table.add_column("Priority", style="yellow")
        table.add_column("Topics", style="green")
        table.add_column("Policy", style="magenta")
        
        for source in plan.sources[:10]:  # Show top 10
            topics_str = ", ".join(source.topics[:3])
            table.add_row(
                source.domain,
                f"{source.priority:.2f}",
                topics_str,
                source.policy
            )
        
        if len(plan.sources) > 10:
            table.add_row("...", f"+ {len(plan.sources) - 10} more", "", "")
        
        console.print(table)
        
        # Check diversity
        meets_diversity, issues = plan.meets_diversity_requirements()
        if not meets_diversity:
            console.print(f"[yellow]⚠️ Diversity issues: {', '.join(issues)}[/yellow]")
        
        # Get RSS URLs
        rss_urls = selector.get_rss_urls_for_selection(plan)
        console.print(f"\n[bold]🔍 Fetching from {len(rss_urls)} RSS feeds...[/bold]")
        
        # Fetch articles using enhanced fetcher
        articles, stats = await enhanced_gather_all_sources(
            feeds=rss_urls[:5],  # Cap to 5 feeds for faster testing
            topic_filter=topic,
            region_filter=region,
            use_thresholds=True
        )
        
        console.print(f"[green]✓ Fetched {len(articles)} articles[/green]")
        
        # Apply relevance filtering
        console.print("\n[bold]🎯 Applying Relevance Filters...[/bold]")
        
        filtered_articles = []
        region_mismatches = 0
        topic_mismatches = 0
        
        for article in articles:
            score = relevance_filter.verify_relevance(
                article,
                target_region=region,
                target_topic=topic,
                strict=strict
            )
            
            if score.should_keep:
                # Add relevance metadata
                article['relevance_score'] = score.weight
                article['region_signals'] = score.region_signals
                article['topic_signals'] = score.topic_signals
                filtered_articles.append(article)
            else:
                if score.drop_reason == 'region_mismatch':
                    region_mismatches += 1
                elif score.drop_reason == 'topic_mismatch':
                    topic_mismatches += 1
        
        console.print(f"[green]✓ {len(filtered_articles)} articles passed filters[/green]")
        if region_mismatches > 0:
            console.print(f"[dim]  Region mismatches: {region_mismatches}[/dim]")
        if topic_mismatches > 0:
            console.print(f"[dim]  Topic mismatches: {topic_mismatches}[/dim]")
        
        # Analyze sentiment
        if filtered_articles:
            console.print("\n[bold]🧠 Analyzing Sentiment...[/bold]")
            
            total_words = 0
            sentiments = []
            
            for article in filtered_articles[:20]:  # Analyze top 20 for faster testing
                text = article.get('text', '')
                total_words += len(text.split())
                
                # Analyze sentiment
                result = analyze(text)
                sentiment = result.sentiment
                sentiments.append(sentiment)
                article['sentiment'] = sentiment
            
            # Calculate volatility
            if sentiments:
                import statistics
                avg_sentiment = statistics.mean(sentiments)
                volatility = statistics.stdev(sentiments) if len(sentiments) > 1 else 0
                certainty = min(1.0, len(sentiments) / 100)
                
                # Display results
                console.print(Panel.fit(
                    f"[bold green]Analysis Results[/bold green]\n"
                    f"Articles Analyzed: {len(sentiments)}\n"
                    f"Total Words: {total_words:,}\n"
                    f"Avg Sentiment: {avg_sentiment:.3f}\n"
                    f"Volatility: {volatility:.3f}\n"
                    f"Certainty: {certainty:.3f}",
                    title="Results"
                ))
                
                # Show top articles
                console.print("\n[bold]📰 Top Articles:[/bold]")
                for i, article in enumerate(filtered_articles[:5], 1):
                    signals = ", ".join(article.get('region_signals', [])[:3])
                    console.print(f"{i}. [cyan]{article.get('title', 'No title')}[/cyan]")
                    console.print(f"   Relevance: {article.get('relevance_score', 0):.2f} | Signals: {signals}")
                    console.print(f"   Sentiment: {article.get('sentiment', 0):.3f}")
                    console.print()
        else:
            console.print("[red]No articles found matching criteria![/red]")
        
        # Discovery suggestion
        if discover and len(filtered_articles) < 50:
            console.print("\n[yellow]💡 Tip: Source discovery could find more sources. Run with --discover[/yellow]")
    
    # Run async function
    asyncio.run(run_analysis())


@app.command()
def list_sources(
    region: Optional[str] = typer.Option(None, "--region", help="Filter by region"),
    topic: Optional[str] = typer.Option(None, "--topic", help="Filter by topic"),
) -> None:
    """List available sources in the SKB."""
    
    selector = SourceSelector()
    
    # Get sources
    if region and region in selector.sources_by_region:
        sources = selector.sources_by_region[region]
        title = f"Sources for {region.upper()}"
    elif topic and topic in selector.sources_by_topic:
        sources = selector.sources_by_topic[topic]
        title = f"Sources for {topic.upper()}"
    else:
        sources = selector.all_sources
        title = "All Sources"
    
    # Display table
    table = Table(title=title, show_header=True)
    table.add_column("Domain", style="cyan")
    table.add_column("Name", style="yellow")
    table.add_column("Region", style="green")
    table.add_column("Topics", style="blue")
    table.add_column("Priority", style="magenta")
    
    for source in sorted(sources, key=lambda s: s.priority, reverse=True)[:30]:
        topics_str = ", ".join(source.topics[:3])
        if len(source.topics) > 3:
            topics_str += f" +{len(source.topics) - 3}"
        
        table.add_row(
            source.domain,
            source.name,
            source.region,
            topics_str,
            f"{source.priority:.2f}"
        )
    
    console.print(table)
    
    if len(sources) > 30:
        console.print(f"\n[dim]Showing top 30 of {len(sources)} sources[/dim]")


@app.command()
def validate(
    region: Optional[str] = typer.Option(None, "--region", help="Region to validate"),
    topic: Optional[str] = typer.Option(None, "--topic", help="Topic to validate"),
) -> None:
    """Validate SKB configuration and quotas."""
    
    selector = SourceSelector()
    
    console.print("[bold]🔍 Validating Source Knowledge Base...[/bold]\n")
    
    # Check regions
    regions = selector.skb.get('regions', {})
    console.print(f"✓ Regions configured: {len(regions)}")
    for region_key in regions:
        sources = selector.sources_by_region.get(region_key, [])
        console.print(f"  • {region_key}: {len(sources)} sources")
    
    # Check topics
    topics = selector.skb.get('topic_specialists', {})
    console.print(f"\n✓ Topic specialists: {len(topics)} topics")
    for topic_key in topics:
        sources = selector.sources_by_topic.get(topic_key, [])
        console.print(f"  • {topic_key}: {len(sources)} sources")
    
    # Test selection
    if region or topic:
        console.print(f"\n[bold]Testing selection for region={region}, topic={topic}...[/bold]")
        
        plan = selector.select_sources(
            region=region,
            topic=topic,
            min_sources=30
        )
        
        meets, issues = plan.meets_diversity_requirements()
        
        if meets:
            console.print("[green]✓ Selection meets diversity requirements[/green]")
        else:
            console.print("[red]✗ Diversity issues found:[/red]")
            for issue in issues:
                console.print(f"  • {issue}")
        
        # Check RSS coverage
        rss_count = sum(1 for s in plan.sources if s.rss_endpoints)
        console.print(f"\nRSS coverage: {rss_count}/{len(plan.sources)} sources have RSS feeds")
        
        # Language diversity
        languages = set()
        for source in plan.sources:
            languages.update(source.languages)
        console.print(f"Languages: {', '.join(sorted(languages))}")


if __name__ == "__main__":
    app()