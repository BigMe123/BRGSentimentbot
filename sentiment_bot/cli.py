"""Command line interface using :mod:`typer`."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from . import scheduler
from .config import settings, REGION_MAP, TOPIC_MAP, WINDOWS
from .analyzer import (
    display_analysis_results,
    display_ingestion_summary,
)
from .interactive import (
    REGION_CHOICES,
    TOPIC_CHOICES,
    WINDOW_CHOICES,
    REGION_KEYS,
    TOPIC_KEYS,
    WINDOW_KEYS,
    parse_multi_selection,
    parse_single_selection,
)


def _try_parse_iso(dt_str: str) -> datetime | None:
    """Parse ISO formatted datetimes safely."""
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


app = typer.Typer(help="Async news sentiment and volatility bot")


def _safe_run(coro) -> None:
    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        typer.echo("Interrupted. Exiting cleanly.")
    except Exception as e:
        typer.echo(f"Something went wrong, but we handled it: {e}")


@app.command()
def live(interval: Optional[int] = None) -> None:
    """Continuously run the bot."""

    _safe_run(scheduler.run_live(interval or settings.INTERVAL))


def menu_after_run(stats: dict, results: dict, articles) -> None:
    try:
        console = Console()
        choices = ["Summary", "Articles", "Analysis", "Exit"]
        while True:
            choice = Prompt.ask(
                "What would you like to view?", choices=choices, default="Summary"
            )
            if choice == "Summary":
                display_ingestion_summary(stats)
            elif choice == "Articles":
                console.rule("Fetched Articles")
                for art in articles:
                    console.print(f"- {art.title}")
            elif choice == "Analysis":
                display_analysis_results(results)
            else:
                break
    except Exception as e:
        Console().print(f"Display issue (continuing): {e}")


@app.command()
def interactive(
    format: str = typer.Option(
        "table", "--format", help="Output format: table/json/csv"
    )
) -> None:
    """Prompt for region, topic and time window before analysing."""

    from . import analyzer, fetcher

    console = Console()

    def _prompt(message: str, choices, keys, multi: bool):
        while True:
            for idx, (label, _) in enumerate(choices, start=1):
                console.print(f"{idx}. {label}")
            answer = Prompt.ask(message)
            try:
                if multi:
                    return parse_multi_selection(answer, keys)
                return parse_single_selection(answer, keys)
            except ValueError:
                console.print("Invalid selection, please try again.")

    regions = _prompt("Select region(s)", REGION_CHOICES, REGION_KEYS, True)
    topics = _prompt("Select topic(s)", TOPIC_CHOICES, TOPIC_KEYS, True)
    window_key = _prompt("Select time frame", WINDOW_CHOICES, WINDOW_KEYS, False)
    window = WINDOWS[window_key]

    async def _main() -> None:
        articles, stats = await fetcher.gather_rss()
        if not articles or stats.get("total", 0) == 0:
            console.print("No articles found")
            return

        start_ts = datetime.now(timezone.utc) - window
        filtered = []
        for art in articles:
            pub = art.published
            if isinstance(pub, datetime):
                pub_dt = pub if pub.tzinfo else pub.replace(tzinfo=timezone.utc)
            else:
                pub_dt = _try_parse_iso(pub or "")
            if pub_dt and pub_dt < start_ts:
                continue
            text = f"{art.title} {art.text}".lower()
            if regions:
                region_words = [
                    w.lower() for r in regions for w in REGION_MAP.get(r, [])
                ]
                if not any(w in text for w in region_words):
                    continue
            if topics:
                topic_words = [w.lower() for t in topics for w in TOPIC_MAP.get(t, [])]
                if not any(w in text for w in topic_words):
                    continue
            filtered.append(art)

        if not filtered:
            console.print("No articles found")
            return

        analyses = [analyzer.analyze(a.text) for a in filtered]
        snapshot = analyzer.aggregate(analyses)

        if format == "json":
            console.print(
                json.dumps(
                    {
                        "regions": regions or ["all"],
                        "topics": topics or ["all"],
                        "time_frame": window_key,
                        "total_articles": len(filtered),
                        "confidence": snapshot.confidence,
                        "volatility": snapshot.volatility,
                        "top_keywords": snapshot.triggers or [],
                    },
                    indent=2,
                )
            )
            return

        if format == "csv":
            import csv
            from io import StringIO

            out = StringIO()
            writer = csv.writer(out)
            writer.writerow(["title", "source", "volatility", "url"])
            per_art = []
            for art, res in zip(filtered, analyses):
                vol = (abs(res.vader) + abs(res.bert)) / 2
                per_art.append((vol, art))
            # sort by volatility only, avoid comparing ArticleData objects
            for vol, art in sorted(per_art, key=lambda x: x[0], reverse=True)[:5]:
                writer.writerow(
                    [art.title, urlparse(art.url).netloc, f"{vol:.3f}", art.url]
                )
            console.print(out.getvalue())
            return

        header = Table(
            "Selected Regions",
            "Selected Topics",
            "Time Frame",
            "Total Articles",
            "Confidence",
            "Analyzer Mode",
        )
        header.add_row(
            ", ".join(regions) or "All",
            ", ".join(topics) or "All",
            window_key.replace("_", " "),
            str(len(filtered)),
            f"{snapshot.confidence:.2f}",
            "standard",
        )
        console.print(header)

        vol_table = Table("Metric", "Value")
        vol_table.add_row("Volatility", f"{snapshot.volatility:.3f}")
        console.print(vol_table)

        if snapshot.triggers:
            console.print(f"Top volatile keywords: {', '.join(snapshot.triggers[:5])}")

        per_art = []
        for art, res in zip(filtered, analyses):
            vol = (abs(res.vader) + abs(res.bert)) / 2
            per_art.append((vol, art))
        if per_art:
            art_table = Table("Title", "Source", "Volatility", "URL")
            # sort by volatility only, avoid comparing ArticleData objects
            for vol, art in sorted(per_art, key=lambda x: x[0], reverse=True)[:5]:
                art_table.add_row(
                    art.title, urlparse(art.url).netloc, f"{vol:.3f}", art.url
                )
            console.print(art_table)

    _safe_run(_main())


@app.command()
def once(
    feeds: Optional[str] = typer.Option(None, "--feeds", help="Custom RSS feeds file path"),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level: DEBUG, INFO, WARNING, ERROR")
) -> None:
    """Run a single fetch/analyse cycle with interactive output."""
    from . import analyzer, fetcher
    import logging
    
    # Set logging level
    logging.getLogger('sentiment_bot.fetcher').setLevel(getattr(logging, log_level.upper()))

    async def _main() -> None:
        try:
            if feeds:
                # Load custom feeds from file
                with open(feeds, 'r') as f:
                    feed_urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                articles, stats = await fetcher.gather_rss(feed_urls)
            else:
                articles, stats = await fetcher.gather_rss()
        except Exception as e:
            typer.echo(f"Fetch error handled: {e}")
            articles, stats = [], {
                "total": 0,
                "attempted": 0,
                "success_rate": 0,
                "words_collected": 0,
                "unique_domains": 0,
                "cache_hits": 0,
                "circuit_breakers": 0,
                "data_quality": 0,
            }
        topics = [t.lower() for t in settings.TOPICS]
        if topics:
            filtered = []
            for art in articles:
                haystack = f"{art.title} {art.text}".lower()
                if any(t in haystack for t in topics):
                    filtered.append(art)
            if filtered:
                articles = filtered

        try:
            analyses = [analyzer.analyze(a.text) for a in articles]
            snapshot = analyzer.aggregate(analyses)
        except Exception as e:
            typer.echo(f"Analysis error handled: {e}")
            snapshot = type("S", (), {"volatility": 0.0, "confidence": 0.0})()
        results = {
            "volatility": snapshot.volatility,
            "model_confidence": snapshot.confidence,
            "articles": articles,
        }
        menu_after_run(stats, results, articles)

    _safe_run(_main())


@app.command()
def once_filtered(
    region: str = typer.Option(..., "--region", help="Region filter (asia, europe, middle_east, africa, americas, oceania)"),
    topic: str = typer.Option(..., "--topic", help="Topic filter (elections, defense, economy, technology, climate, health)"),
    feeds: Optional[str] = typer.Option(None, "--feeds", help="Custom RSS feeds file path"),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level: DEBUG, INFO, WARNING, ERROR"),
    max_concurrency: int = typer.Option(200, "--max-concurrency", help="Maximum concurrent requests"),
    per_domain: int = typer.Option(3, "--per-domain", help="Maximum requests per domain")
) -> None:
    """Run single cycle with region and topic filtering."""
    from . import analyzer, fetcher
    from .filter import get_supported_regions, get_supported_topics
    import logging
    
    # Set logging level
    logging.getLogger('sentiment_bot.fetcher').setLevel(getattr(logging, log_level.upper()))
    logging.getLogger('sentiment_bot.filter').setLevel(getattr(logging, log_level.upper()))
    
    # Validate region and topic
    supported_regions = get_supported_regions()
    supported_topics = get_supported_topics()
    
    if region.lower() not in supported_regions:
        typer.echo(f"Error: Region '{region}' not supported.")
        typer.echo(f"Supported regions: {', '.join(supported_regions)}")
        return
    
    if topic.lower() not in supported_topics:
        typer.echo(f"Error: Topic '{topic}' not supported.")
        typer.echo(f"Supported topics: {', '.join(supported_topics)}")
        return
    
    async def _main() -> None:
        console = Console()
        console.print(f"[bold]Fetching articles for Region: {region}, Topic: {topic}[/bold]")
        
        try:
            if feeds:
                # Load custom feeds from file
                with open(feeds, 'r') as f:
                    feed_urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                articles, stats = await fetcher.gather_rss(feed_urls, region=region, topic=topic)
            else:
                articles, stats = await fetcher.gather_rss(region=region, topic=topic)
            
            # Display collection stats
            display_ingestion_summary(stats)
            
            if stats.get("filtered", 0) > 0:
                console.print(f"\n[yellow]Filtered out {stats['filtered']} irrelevant articles[/yellow]")
            
            if articles:
                # Analyze sentiment
                results = await analyzer.run_analysis(articles)
                display_analysis_results(results)
                
                # Show top relevant articles
                console.rule("Top Relevant Articles")
                for i, art in enumerate(articles[:5], 1):
                    console.print(f"{i}. [bold]{art.title}[/bold]")
                    console.print(f"   URL: {art.url}")
                    console.print(f"   Preview: {art.text[:200]}...")
                    console.print()
                
                # Interactive menu
                menu_after_run(stats, results, articles)
            else:
                console.print("[red]No articles matched the specified region and topic filters.[/red]")
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback
            if log_level.upper() == "DEBUG":
                traceback.print_exc()

    _safe_run(_main())


@app.command()
def chat() -> None:
    """Interactive Q&A."""
    if getattr(settings, "SAFE_MODE", True):
        typer.echo("SAFE_MODE enabled; chat disabled.")
        return
    try:
        from langchain.embeddings import SentenceTransformerEmbeddings
        from langchain.vectorstores import FAISS
        from .chat_agent import ChatAgent
    except Exception as e:
        typer.echo("LangChain/FAISS not available; chat disabled.")
        return

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        typer.echo(
            "OPENAI_API_KEY is missing or empty. Please set it before using chat."
        )
        return

    embeddings = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
    path = Path("faiss_index")
    if path.exists():
        vs = FAISS.load_local(
            str(path), embeddings, allow_dangerous_deserialization=True
        )
    else:  # empty store
        vs = FAISS.from_texts([], embeddings)
    agent = ChatAgent(vs, api_key)

    while True:
        q = typer.prompt("query")
        if not q:
            break
        typer.echo(agent.ask(q))


@app.command()
def rules() -> None:
    """Print currently configured rules."""

    from .rules import load_rules

    for rule in load_rules():
        typer.echo(f"when {rule.when} -> {rule.then}")


@app.command()
def fetch(urls: List[str] = typer.Option(..., "--urls")) -> None:
    """Fetch RSS feeds and print article snippets."""
    from .fetcher import gather_rss

    async def _main() -> None:
        articles, _ = await gather_rss(urls)
        for art in articles:
            snippet = art.text.replace("\n", " ")[:80]
            typer.echo(f"{art.url} -> {snippet}")

    _safe_run(_main())


@app.command()
def simulate(paths: int = 100) -> None:
    """Run a Monte Carlo simulation using stored snapshots."""
    from .simulate import monte_carlo, save_csv

    try:
        con = sqlite3.connect(settings.DB_PATH)
        rows = con.execute(
            "SELECT volatility FROM snapshot ORDER BY id DESC LIMIT 24"
        ).fetchall()
        series = [r[0] for r in rows][::-1]
        con.close()
    except Exception:
        series = [0.0] * 24
    df = monte_carlo(series, paths)
    save_csv(df)
    typer.echo(f"saved {settings.SIM_PATH}")


@app.command()
def serve() -> None:
    """Run the WebSocket server with live snapshots."""
    if getattr(settings, "SAFE_MODE", True):
        typer.echo("SAFE_MODE enabled; serve disabled.")
        return
    try:
        from . import scheduler, ws_server
    except Exception:
        typer.echo("WebSocket server not available.")
        return

    async def _main() -> None:
        latest = {"volatility": 0.0, "confidence": 0.0}

        async def updater() -> None:
            nonlocal latest
            while True:
                snap = await scheduler.run_once()
                latest = {
                    "volatility": snap.volatility,
                    "confidence": snap.confidence,
                }
                await asyncio.sleep(settings.INTERVAL * 60)

        await asyncio.gather(updater(), ws_server.serve(lambda: latest))

    _safe_run(_main())


@app.command()
def web() -> None:
    """Run WebSocket server and Gradio GUI."""
    if getattr(settings, "SAFE_MODE", True):
        typer.echo("SAFE_MODE enabled; web disabled.")
        return
    try:
        from . import scheduler, ws_server
        from .gui import launch as launch_gui
    except Exception:
        typer.echo("Web/GUI dependencies missing.")
        return

    async def _main() -> None:
        latest = {"volatility": 0.0, "confidence": 0.0}

        async def updater() -> None:
            nonlocal latest
            while True:
                snap = await scheduler.run_once()
                latest = {
                    "volatility": snap.volatility,
                    "confidence": snap.confidence,
                }
                await asyncio.sleep(settings.INTERVAL * 60)

        loop = asyncio.get_running_loop()
        await asyncio.gather(
            updater(),
            ws_server.serve(lambda: latest),
            loop.run_in_executor(None, launch_gui),
        )

    _safe_run(_main())


@app.command()
def forecast(
    engine: str = typer.Option("vae", help="vae or gan"),
    steps: int = typer.Option(5, "--steps"),
    samples: int = typer.Option(50, "--samples"),
) -> None:
    """Run forecasting model."""
    if getattr(settings, "SAFE_MODE", True):
        typer.echo("SAFE_MODE enabled; forecast disabled.")
        return
    try:
        import pandas as pd
        from sentiment_bot.forecast import GANForecast, VAEForecast
    except Exception:
        typer.echo("Forecast dependencies missing.")
        return

    series = pd.Series([0.1, 0.2, 0.15, 0.18, 0.22, 0.19, 0.21, 0.2, 0.23, 0.25])
    Model = VAEForecast if engine == "vae" else GANForecast
    model = Model().fit(series, epochs=20)
    df = model.forecast(steps, samples)

    from rich.console import Console
    from rich.table import Table

    table = Table("step", "mean", "lower", "upper")
    for i, row in df.iterrows():
        table.add_row(
            str(i), f"{row['mean']:.3f}", f"{row['lower']:.3f}", f"{row['upper']:.3f}"
        )
    Console().print(table)


@app.command()
def bayesian(path: Optional[Path] = None) -> None:
    """Fit a hierarchical Bayesian model on data."""
    from .bayesian import fit_hierarchical, load_example_data

    df = load_example_data(path)
    res = fit_hierarchical(df)
    typer.echo(f"posterior mean volatility: {float(res.ppc['vol'].mean()):.3f}")


@app.command()
def graph(question: str = "What about Apple?") -> None:
    """Query a tiny knowledge graph."""

    triples = [("Apple", "competes", "Google"), ("Google", "acquires", "YouTube")]
    from .knowledge_graph import GraphEmbedder, ingest_triples

    kg = ingest_triples(triples)
    emb = GraphEmbedder()
    emb.fit(kg)
    typer.echo(emb.query_graph(question))


@app.command()
def multimodal(image_url: str, video_url: str) -> None:
    """Extract text from image and video."""

    from .multimodal import aggregate_article_text

    article = {"text": "", "image_url": image_url, "video_url": video_url}
    typer.echo(aggregate_article_text(article))


@app.command()
def meta() -> None:
    """Run a minimal meta-learning loop."""
    from datasets import Dataset
    from .meta_learning import MAMLTrainer

    trainer = MAMLTrainer()
    ds = Dataset.from_dict({"text": ["good", "bad"], "label": [1, 0]})
    trainer.meta_train([ds])
    trainer.adapt(ds)
    typer.echo("meta-learning completed")


@app.command()
def privacy_demo() -> None:
    """Demonstrate differential privacy decorator."""

    from .privacy import dp_mechanism

    @dp_mechanism(epsilon=5.0, delta=1e-5)
    def compute(x: int) -> int:
        return x * 2

    compute(2)
    typer.echo(f"eps={compute.epsilon:.2f}, delta={compute.delta:.1e}")


@app.command()
def explain(text: str = "A sample article") -> None:
    """Explain model prediction for given text."""

    from .explain import explain_article

    attributions = explain_article(text)
    typer.echo(json.dumps(attributions, indent=2))


@app.command()
def stream(
    kafka_bootstrap: str, topic: str
) -> None:  # pragma: no cover - requires infra
    """Run the streaming job."""

    from .streaming import start_stream

    start_stream(kafka_bootstrap, topic)


@app.command()
def quantum() -> None:
    """Optimise a tiny sentiment portfolio."""

    from .quantum_opt import optimize_portfolio

    typer.echo(optimize_portfolio())


@app.command()
def once_fast(
    feeds: Optional[str] = typer.Option(None, "--feeds", help="Path to feeds file"),
    max_concurrency: int = typer.Option(200, "--max-concurrency", help="Max concurrent operations"),
    per_domain: int = typer.Option(3, "--per-domain", help="Max concurrent requests per domain"),
    browser_pool_size: int = typer.Option(5, "--browser-pool", help="Number of browser pages in pool"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
    topic: Optional[str] = typer.Option(None, "--topic", help="Filter by topic"),
    region: Optional[str] = typer.Option(None, "--region", help="Filter by region"),
) -> None:
    """
    Run the FAST pipeline once with high-throughput 3-stage processing.
    
    Features:
    - Concurrent fetch with curl_cffi → aiohttp fallback
    - Smart JS detection and Playwright pooling
    - Streaming NLP with async parse_and_score
    - Real-time results as they complete
    """
    from .pipeline import run_pipeline
    from .browser_pool import PlaywrightPool
    from .logging import setup_logging
    from .analyzer import aggregate
    from rich.console import Console
    from rich.live import Live
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    import time
    
    console = Console()
    
    # Setup logging
    setup_logging(level="DEBUG" if debug else "INFO")
    
    async def _run_fast():
        console.print("[bold cyan]🚀 Starting FAST Pipeline[/bold cyan]")
        console.print(f"Concurrency: {max_concurrency} | Per-domain: {per_domain} | Browser pool: {browser_pool_size}")
        
        # Load feeds
        if feeds and Path(feeds).exists():
            with open(feeds, 'r') as f:
                lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                # Parse mixed sources (RSS|url or HTML|url)
                urls = []
                for line in lines:
                    if '|' in line:
                        _, url = line.split('|', 1)
                        urls.append(url.strip())
                    else:
                        urls.append(line)
        else:
            # Default feeds
            urls = [
                "https://feeds.bbci.co.uk/news/world/rss.xml",
                "https://feeds.reuters.com/reuters/worldNews",
                "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
            ]
            console.print(f"[yellow]Using default feeds (use --feeds to specify custom)[/yellow]")
        
        console.print(f"Processing {len(urls)} sources...")
        
        # Initialize browser pool
        playwright_pool = None
        if browser_pool_size > 0:
            try:
                from .browser_pool import PlaywrightPool
                playwright_pool = PlaywrightPool(pages=browser_pool_size)
                await playwright_pool.start()
                console.print(f"[green]✓ Browser pool started with {browser_pool_size} pages[/green]")
            except Exception as e:
                console.print(f"[yellow]Browser pool failed to start: {e}[/yellow]")
                console.print("[yellow]Continuing without JS rendering[/yellow]")
        
        # Process through pipeline
        results = []
        analyses = []
        start_time = time.time()
        
        # Progress tracking
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("Processing articles", total=len(urls))
            
            async for article in run_pipeline(
                urls,
                max_concurrency=max_concurrency,
                per_domain=per_domain,
                playwright_pool=playwright_pool
            ):
                results.append(article)
                progress.update(task, advance=1)
                
                # Apply filters if specified
                if topic or region:
                    text_to_check = f"{article.title} {article.text}".lower()
                    if topic and topic.lower() not in text_to_check:
                        continue
                    if region and region.lower() not in text_to_check:
                        continue
                
                # Analyze sentiment if we have text
                if article.text and len(article.text) > 50:
                    from .analyzer import analyze
                    analysis = analyze(article.text)
                    analyses.append(analysis)
                
                # Show result
                transport_icon = {
                    'curl_cffi': '🔥',
                    'aiohttp': '🌐',
                    'playwright': '🎭',
                }.get(article.transport, '❓')
                
                timing = article.timing_ms.get('total_ms', 0)
                timing_color = 'green' if timing < 500 else 'yellow' if timing < 1000 else 'red'
                
                console.print(
                    f"{transport_icon} [{timing_color}]{timing}ms[/{timing_color}] "
                    f"{article.domain}: {article.title[:60]}... ({article.word_count} words)"
                )
        
        # Close browser pool
        if playwright_pool:
            await playwright_pool.close()
        
        # Calculate aggregate metrics
        elapsed = time.time() - start_time
        
        console.print("\n[bold green]═══ PIPELINE COMPLETE ═══[/bold green]")
        
        # Stats table
        stats_table = Table(title="Pipeline Statistics", show_header=True)
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Value", style="yellow")
        
        stats_table.add_row("Total URLs", str(len(urls)))
        stats_table.add_row("Successful", str(len([r for r in results if r.text])))
        stats_table.add_row("Failed", str(len([r for r in results if not r.text])))
        stats_table.add_row("Total Time", f"{elapsed:.2f}s")
        stats_table.add_row("Avg Time/URL", f"{(elapsed/len(urls)*1000):.0f}ms")
        
        # Transport breakdown
        transports = {}
        for r in results:
            transports[r.transport] = transports.get(r.transport, 0) + 1
        stats_table.add_row("Transports", str(transports))
        
        console.print(stats_table)
        
        # Sentiment analysis if we have results
        if analyses:
            snapshot = aggregate(analyses)
            
            console.print("\n[bold cyan]═══ SENTIMENT ANALYSIS ═══[/bold cyan]")
            sentiment_table = Table(show_header=True)
            sentiment_table.add_column("Metric", style="cyan")
            sentiment_table.add_column("Value", style="yellow")
            sentiment_table.add_column("Status", style="green")
            
            sentiment_table.add_row(
                "Volatility",
                f"{snapshot.volatility:.4f}",
                "🔴 HIGH" if snapshot.volatility > 0.5 else "🟡 MODERATE" if snapshot.volatility > 0.3 else "🟢 LOW"
            )
            sentiment_table.add_row(
                "Certainty",
                f"{snapshot.confidence:.4f}",
                "✅ HIGH" if snapshot.confidence > 0.5 else "⚠️ MODERATE" if snapshot.confidence > 0.3 else "❌ LOW"
            )
            sentiment_table.add_row("Articles Analyzed", str(len(analyses)), "")
            
            console.print(sentiment_table)
            
            if snapshot.triggers:
                console.print(f"\n[bold]Trigger Words:[/bold] {', '.join(snapshot.triggers[:10])}")
        
        # Show warnings if any
        all_warnings = []
        for r in results:
            all_warnings.extend(r.warnings)
        
        if all_warnings:
            unique_warnings = list(set(all_warnings))
            console.print(f"\n[yellow]Warnings ({len(unique_warnings)} unique):[/yellow]")
            for w in unique_warnings[:5]:
                console.print(f"  - {w}")
    
    _safe_run(_run_fast())
