"""
Optimized SKB CLI with better performance and model management.
Maintains ML model quality while improving speed.
"""

import asyncio
import typer
from pathlib import Path
from typing import Optional, List, Dict, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
import logging
import time
from concurrent.futures import ThreadPoolExecutor
import aiohttp
import feedparser

from .source_selector import SourceSelector
from .relevance_filter import RelevanceFilter
from .analyzer import analyze

app = typer.Typer(help="Optimized sentiment bot with intelligent source selection")
console = Console()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OptimizedFetcher:
    """Optimized article fetcher with parallel processing."""
    
    def __init__(self, max_concurrent: int = 10, timeout: int = 10):
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.session = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        timeout_config = aiohttp.ClientTimeout(total=self.timeout)
        self.session = aiohttp.ClientSession(timeout=timeout_config)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def fetch_rss(self, url: str) -> List[Dict[str, Any]]:
        """Fetch and parse a single RSS feed."""
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    content = await response.text()
                    # Parse RSS in thread pool to avoid blocking
                    loop = asyncio.get_event_loop()
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        feed = await loop.run_in_executor(executor, feedparser.parse, content)
                    
                    articles = []
                    for entry in feed.entries[:10]:  # Limit articles per feed
                        # Get full text from description or summary
                        text = entry.get('description', '') or entry.get('summary', '')
                        # Also check for content field
                        if not text and hasattr(entry, 'content'):
                            text = entry.content[0].value if entry.content else ''
                        
                        article = {
                            'title': entry.get('title', ''),
                            'url': entry.get('link', ''),
                            'text': text,
                            'published': entry.get('published', ''),
                            'source_url': url,
                            'domain': url.split('/')[2] if '/' in url else url
                        }
                        articles.append(article)
                    return articles
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
        return []
    
    async def fetch_multiple_rss(self, urls: List[str], progress=None) -> List[Dict[str, Any]]:
        """Fetch multiple RSS feeds in parallel with progress tracking."""
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def fetch_with_semaphore(url):
            async with semaphore:
                result = await self.fetch_rss(url)
                if progress:
                    progress.advance(task_id)
                return result
        
        # Create progress task if progress tracker provided
        task_id = None
        if progress:
            task_id = progress.add_task("[cyan]Fetching RSS feeds...", total=len(urls))
        
        # Fetch all feeds concurrently
        tasks = [fetch_with_semaphore(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flatten results
        all_articles = []
        for result in results:
            if isinstance(result, list):
                all_articles.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"Feed fetch error: {result}")
        
        return all_articles


class LazyModelLoader:
    """Lazy loading for ML models to reduce startup time."""
    
    _relevance_filter = None
    _analyzer = None
    
    @classmethod
    def get_relevance_filter(cls):
        """Get or create relevance filter."""
        if cls._relevance_filter is None:
            cls._relevance_filter = RelevanceFilter()
        return cls._relevance_filter
    
    @classmethod
    def analyze_sentiment(cls, text: str):
        """Analyze sentiment with lazy loading."""
        return analyze(text)


@app.command()
def analyze(
    region: Optional[str] = typer.Option(None, "--region", help="Target region (asia, middle_east, europe, americas, africa)"),
    topic: Optional[str] = typer.Option(None, "--topic", help="Target topic (elections, security, economy, politics, energy, climate, tech)"),
    strict: bool = typer.Option(False, "--strict", help="Strict mode - only exact matches"),
    expand: bool = typer.Option(False, "--expand", help="Expand to include global specialists"),
    min_sources: int = typer.Option(20, "--min-sources", help="Minimum number of sources (reduced for speed)"),
    max_articles: int = typer.Option(100, "--max-articles", help="Maximum articles to process"),
    timeout: int = typer.Option(30, "--timeout", help="Timeout per feed in seconds"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug output"),
    sample: bool = typer.Option(False, "--sample", help="Sample mode - show articles without filtering"),
) -> None:
    """
    Optimized analysis with intelligent source selection and relevance filtering.
    
    Examples:
        poetry run python -m sentiment_bot.cli_skb_optimized analyze --region asia --topic elections
        poetry run python -m sentiment_bot.cli_skb_optimized analyze --region middle_east --strict
        poetry run python -m sentiment_bot.cli_skb_optimized analyze --topic energy --expand
    """
    
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Display configuration
    console.print(Panel.fit(
        f"[bold cyan]Optimized Configuration[/bold cyan]\n"
        f"Region: {region or 'All'}\n"
        f"Topic: {topic or 'All'}\n"
        f"Mode: {'Strict' if strict else 'Flexible'}\n"
        f"Expand: {expand}\n"
        f"Min Sources: {min_sources}\n"
        f"Max Articles: {max_articles}\n"
        f"Timeout: {timeout}s",
        title="SKB Analysis (Optimized)"
    ))
    
    async def run_optimized_analysis():
        start_time = time.time()
        
        # Initialize selector (lightweight)
        selector = SourceSelector()
        
        # Select sources
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("[bold]📚 Selecting Sources...[/bold]", total=None)
            
            plan = selector.select_sources(
                region=region,
                topic=topic,
                strict=strict,
                expand=expand,
                min_sources=min_sources,
                budget_seconds=300
            )
            
            progress.update(task, completed=True)
        
        # Display selected sources
        table = Table(title="Selected Sources", show_header=True)
        table.add_column("Domain", style="cyan")
        table.add_column("Priority", style="yellow")
        table.add_column("Topics", style="green")
        
        for source in plan.sources[:10]:  # Show top 10
            topics_str = ", ".join(source.topics[:3])
            table.add_row(
                source.domain,
                f"{source.priority:.2f}",
                topics_str
            )
        
        if len(plan.sources) > 10:
            table.add_row("...", f"+ {len(plan.sources) - 10} more", "")
        
        console.print(table)
        
        # Check diversity
        meets_diversity, issues = plan.meets_diversity_requirements()
        if not meets_diversity:
            console.print(f"[yellow]⚠️ Diversity issues: {', '.join(issues)}[/yellow]")
        
        # Get RSS URLs
        rss_urls = selector.get_rss_urls_for_selection(plan)
        console.print(f"\n[bold]🔍 Fetching from {len(rss_urls)} RSS feeds...[/bold]")
        
        # Fetch articles with progress tracking
        articles = []
        async with OptimizedFetcher(max_concurrent=10, timeout=timeout) as fetcher:
            with Progress(
                "[progress.description]{task.description}",
                BarColumn(),
                "[progress.percentage]{task.percentage:>3.0f}%",
                console=console
            ) as progress:
                articles = await fetcher.fetch_multiple_rss(rss_urls[:min_sources], progress)
        
        console.print(f"[green]✓ Fetched {len(articles)} articles in {time.time() - start_time:.1f}s[/green]")
        
        if not articles:
            console.print("[red]No articles fetched! Check network connection and RSS feeds.[/red]")
            return
        
        # Sample mode - skip filtering
        if sample:
            console.print("\n[yellow]🔬 Sample Mode - Showing raw articles without filtering[/yellow]")
            for i, article in enumerate(articles[:5], 1):
                console.print(f"\n{i}. [cyan]{article.get('title', 'No title')}[/cyan]")
                console.print(f"   Domain: {article.get('domain', 'Unknown')}")
                text_preview = article.get('text', '')[:200]
                if text_preview:
                    console.print(f"   Text: {text_preview}...")
            console.print(f"\n[dim]Showing 5 of {len(articles)} total articles[/dim]")
            return
        
        # Apply relevance filtering with progress
        console.print("\n[bold]🎯 Applying Relevance Filters...[/bold]")
        
        relevance_filter = LazyModelLoader.get_relevance_filter()
        filtered_articles = []
        region_mismatches = 0
        topic_mismatches = 0
        
        with Progress(
            "[progress.description]{task.description}",
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Filtering articles...", total=len(articles))
            
            for article in articles[:max_articles]:  # Limit processing
                # Boost region score if from a region-specific source
                if region and article.get('domain') in [s.domain for s in plan.sources]:
                    # This is from a source we selected for this region
                    article['_region_boost'] = True
                
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
                    if debug and len(articles) <= 10:  # Show debug for first few
                        logger.debug(f"Filtered: {article.get('title', 'No title')[:50]}")
                        logger.debug(f"  Region: {score.region_score:.2f}, Topic: {score.topic_score:.2f}")
                        logger.debug(f"  Reason: {score.drop_reason}")
                    if score.drop_reason == 'region_mismatch':
                        region_mismatches += 1
                    elif score.drop_reason == 'topic_mismatch':
                        topic_mismatches += 1
                
                progress.advance(task)
        
        console.print(f"[green]✓ {len(filtered_articles)} articles passed filters[/green]")
        if region_mismatches > 0:
            console.print(f"[dim]  Region mismatches: {region_mismatches}[/dim]")
        if topic_mismatches > 0:
            console.print(f"[dim]  Topic mismatches: {topic_mismatches}[/dim]")
        
        # Analyze sentiment on filtered articles
        if filtered_articles:
            console.print("\n[bold]🧠 Analyzing Sentiment...[/bold]")
            
            total_words = 0
            sentiments = []
            
            # Process in batches for better progress tracking
            batch_size = 10
            with Progress(
                "[progress.description]{task.description}",
                BarColumn(),
                "[progress.percentage]{task.percentage:>3.0f}%",
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Analyzing sentiment...", total=min(len(filtered_articles), 20))
                
                for i, article in enumerate(filtered_articles[:20]):  # Analyze top 20
                    text = article.get('text', '')
                    total_words += len(text.split())
                    
                    # Analyze sentiment
                    result = LazyModelLoader.analyze_sentiment(text)
                    sentiment = result.sentiment
                    sentiments.append(sentiment)
                    article['sentiment'] = sentiment
                    
                    progress.advance(task)
            
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
                    f"Certainty: {certainty:.3f}\n"
                    f"Time: {time.time() - start_time:.1f}s",
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
        
        console.print(f"\n[dim]Total execution time: {time.time() - start_time:.1f}s[/dim]")
    
    # Run async function
    asyncio.run(run_optimized_analysis())


@app.command()
def quick_test(
    region: str = typer.Argument("asia", help="Region to test"),
    topic: str = typer.Argument("elections", help="Topic to test"),
) -> None:
    """Quick test with minimal processing for development."""
    
    console.print(f"[bold]Quick Test: {region} + {topic}[/bold]\n")
    
    # Test source selection
    selector = SourceSelector()
    plan = selector.select_sources(region=region, topic=topic, min_sources=10)
    
    console.print(f"✓ Found {len(plan.sources)} sources")
    console.print(f"✓ RSS feeds: {len(selector.get_rss_urls_for_selection(plan))}")
    
    # Test relevance filter
    relevance_filter = LazyModelLoader.get_relevance_filter()
    
    test_article = {
        'title': 'India elections see high turnout in Maharashtra',
        'text': 'Mumbai saw record voter turnout in the state elections today. The electoral commission reported 65% participation.',
        'url': 'https://example.com/india/elections'
    }
    
    score = relevance_filter.verify_relevance(test_article, target_region=region, target_topic=topic)
    console.print(f"\n[bold]Test Article Relevance:[/bold]")
    console.print(f"  Region Score: {score.region_score:.2f}")
    console.print(f"  Topic Score: {score.topic_score:.2f}")
    console.print(f"  Should Keep: {score.should_keep}")
    console.print(f"  Signals: {score.region_signals + score.topic_signals}")


if __name__ == "__main__":
    app()