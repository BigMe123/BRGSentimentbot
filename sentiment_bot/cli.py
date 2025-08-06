"""Command line interface using :mod:`typer`."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from . import chat_agent, scheduler
from .config import settings
from .rules import load_rules
from .simulate import monte_carlo, save_csv
from .ws_server import serve as serve_ws
from .gui import launch as launch_gui

app = typer.Typer(help="Async news sentiment and volatility bot")


@app.command()
def live(interval: int = settings.INTERVAL) -> None:
    """Continuously run the bot."""

    asyncio.run(scheduler.run_live(interval))


@app.command()
def once() -> None:
    """Run a single fetch/analyse cycle."""

    asyncio.run(scheduler.run_once())


@app.command()
def chat() -> None:
    """Start an interactive chat session."""

    chat_agent.chat_loop()


@app.command()
def rules() -> None:
    """Print currently configured rules."""

    for rule in load_rules():
        typer.echo(f"when {rule.when} -> {rule.then}")


@app.command()
def simulate(paths: int = 100) -> None:
    """Run a Monte Carlo simulation with dummy data."""

    data = [0.1, 0.2, 0.3]
    df = monte_carlo(data, paths)
    save_csv(df)
    typer.echo(f"saved {settings.SIM_PATH}")


@app.command()
def serve() -> None:
    """Run the WebSocket server."""

    async def _main() -> None:
        snapshot = {"volatility": 0.0, "confidence": 0.0}

        def _snap() -> dict:
            return snapshot

        await serve_ws(_snap)

    asyncio.run(_main())


@app.command()
def web() -> None:
    """Run WebSocket server and Gradio GUI."""

    async def _main() -> None:
        async def ws_runner() -> None:
            snapshot = {"volatility": 0.0, "confidence": 0.0}

            def _snap() -> dict:
                return snapshot

            await serve_ws(_snap)

        asyncio.create_task(ws_runner())
        launch_gui()

    asyncio.run(_main())


@app.command()
def forecast(n_steps: int = 5) -> None:
    """Run GAN volatility forecast on synthetic data."""

    import pandas as pd

    from .forecast import TimeSeriesGAN

    series = pd.Series([0.1, 0.2, 0.15, 0.18, 0.22, 0.19, 0.21, 0.2, 0.23, 0.25])
    model = TimeSeriesGAN(seq_len=5).fit(series, epochs=10)
    result = model.forecast(n_steps)
    typer.echo(result.forecast.to_string())


@app.command()
def bayesian() -> None:
    """Fit a hierarchical Bayesian model on dummy data."""

    import pandas as pd

    from .bayesian import fit_hierarchical

    df = pd.DataFrame(
        {
            "sector": ["tech", "tech", "fin", "fin"],
            "time": [0, 1, 0, 1],
            "volatility": [0.1, 0.2, 0.15, 0.25],
        }
    )
    res = fit_hierarchical(df)
    typer.echo(f"posterior draws: {len(res.trace.posterior.dims['chain'])}")


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
    """Run a dummy meta-learning loop."""

    from datasets import Dataset

    from .meta_learning import MAMLTrainer

    trainer = MAMLTrainer()
    ds = Dataset.from_dict({"text": ["hello"], "label": [1]})
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
def stream(kafka_bootstrap: str, topic: str) -> None:  # pragma: no cover - requires infra
    """Run the streaming job."""

    from .streaming import start_stream

    start_stream(kafka_bootstrap, topic)


@app.command()
def quantum() -> None:
    """Optimise a tiny sentiment portfolio."""

    from .quantum_opt import optimize_portfolio

    res = optimize_portfolio([0.1, 0.2])
    typer.echo(f"optimal weights: {res}")


if __name__ == "__main__":  # pragma: no cover - manual
    app()
