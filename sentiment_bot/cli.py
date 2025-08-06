"""Command line interface using :mod:`typer`."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from pathlib import Path
from typing import List, Optional

import pandas as pd
import typer
from datasets import Dataset
from langchain.embeddings import SentenceTransformerEmbeddings
from langchain.vectorstores import FAISS

from . import scheduler, ws_server
from .bayesian import fit_hierarchical, load_example_data
from .chat_agent import ChatAgent
from .config import settings
from .fetcher import fetch_and_parse
from .gui import launch as launch_gui
from .meta_learning import MAMLTrainer
from .simulate import monte_carlo, save_csv

app = typer.Typer(help="Async news sentiment and volatility bot")


@app.command()
def live(interval: Optional[int] = None) -> None:
    """Continuously run the bot."""

    asyncio.run(scheduler.run_live(interval or settings.INTERVAL))


@app.command()
def once() -> None:
    """Run a single fetch/analyse cycle."""

    asyncio.run(scheduler.run_once())


@app.command()
def chat() -> None:
    """Interactive Q&A."""

    embeddings = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
    path = Path("faiss_index")
    if path.exists():
        vs = FAISS.load_local(str(path), embeddings, allow_dangerous_deserialization=True)
    else:  # empty store
        vs = FAISS.from_texts([], embeddings)
    agent = ChatAgent(vs, os.getenv("OPENAI_API_KEY", ""))

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

    async def _main() -> None:
        articles = await fetch_and_parse(urls)
        for art in articles:
            snippet = art.text.replace("\n", " ")[:80]
            typer.echo(f"{art.url} -> {snippet}")

    asyncio.run(_main())


@app.command()
def simulate(paths: int = 100) -> None:
    """Run a Monte Carlo simulation using stored snapshots."""

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

    asyncio.run(_main())


@app.command()
def web() -> None:
    """Run WebSocket server and Gradio GUI."""

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
            updater(), ws_server.serve(lambda: latest), loop.run_in_executor(None, launch_gui)
        )

    asyncio.run(_main())


@app.command()
def forecast(
    engine: str = typer.Option("vae", help="vae or gan"),
    steps: int = typer.Option(5, "--steps"),
    samples: int = typer.Option(50, "--samples"),
) -> None:
    """Run forecasting model."""

    import pandas as pd
    from sentiment_bot.forecast import GANForecast, VAEForecast

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
