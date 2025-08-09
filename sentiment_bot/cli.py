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
def once() -> None:
    """Run a single fetch/analyse cycle with interactive output."""
    from . import analyzer, fetcher

    async def _main() -> None:
        try:
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
