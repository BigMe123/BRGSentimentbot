"""Monte Carlo scenario simulation utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import settings


def monte_carlo(snapshot_series: list[float], paths: int) -> pd.DataFrame:
    """Run a simple Monte Carlo simulation returning a :class:`DataFrame`."""

    series = np.array(snapshot_series, dtype="float32")
    mu = float(series.mean())
    sigma = float(series.std() or 1e-6)
    steps = len(series)
    sims = np.random.normal(mu, sigma, size=(paths, steps))
    return pd.DataFrame(sims)


def save_csv(df: pd.DataFrame, path: str | None = None) -> None:
    """Persist simulation results to ``settings.SIM_PATH``."""

    df.to_csv(path or settings.SIM_PATH, index=False)
