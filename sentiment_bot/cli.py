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


if __name__ == "__main__":  # pragma: no cover - manual
    app()
