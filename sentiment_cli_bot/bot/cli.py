"""Command line entry-point using :mod:`typer`."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from . import scheduler

app = typer.Typer(help="Async news sentiment and volatility bot")


@app.command()
def live(interval: int = 30) -> None:
    """Continuously scrape & print dashboard every ``interval`` minutes."""

    asyncio.run(scheduler.run_live(interval))


@app.command()
def once() -> None:
    """Run one scrape-analysis-print cycle."""

    asyncio.run(scheduler.run_once())


@app.command()
def export(path: str = "snapshot.json") -> None:
    """Dump last snapshot in JSON.

    This demo implementation simply creates an empty placeholder file.
    A future version will persist real snapshots to SQLite and export the
    most recent one.
    """

    Path(path).write_text(json.dumps({"todo": True}))
    typer.echo(f"wrote {path}")


if __name__ == "__main__":  # pragma: no cover - manual invocation
    app()
