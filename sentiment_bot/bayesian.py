from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import sqlite3


def load_example_data(path: Path | None = None) -> pd.DataFrame:
    """Load volatility data from SQLite if available, otherwise a toy dataset."""

    db_path = Path(path or "sentiment.db")
    if db_path.exists():
        try:
            con = sqlite3.connect(db_path)
            df = pd.read_sql_query("SELECT sector, time, volatility FROM snapshot", con)
            con.close()
            if not df.empty:
                return df
        except Exception:
            pass
    return pd.DataFrame(
        {
            "sector": ["tech", "tech", "fin", "fin"],
            "time": [0, 1, 0, 1],
            "volatility": [0.1, 0.2, 0.15, 0.25],
        }
    )


@dataclass
class InferenceResult:
    """Container for fitted model and posterior predictive samples."""

    trace: object  # arviz.InferenceData
    ppc: dict


def fit_hierarchical(
    data: pd.DataFrame, draws: int = 500, tune: int = 500
) -> InferenceResult:
    """Fit the hierarchical volatility model using PyMC."""

    import pymc as pm

    sectors = data["sector"].unique().tolist()
    sector_idx = pd.Categorical(data["sector"], sectors).codes
    coords = {"sector": sectors}

    with pm.Model(coords=coords) as model:
        mu = pm.Normal("mu", 0.0, 1.0)
        sigma_obs = pm.HalfNormal("sigma_obs", 1.0)
        sigma_alpha = pm.HalfNormal("sigma_alpha", 1.0)
        alpha = pm.Normal("alpha", 0.0, sigma_alpha, dims="sector")
        beta = pm.Normal("beta", 0.0, 1.0)

        mean = mu + alpha[sector_idx] + beta * data["time"].to_numpy()
        pm.Normal(
            "vol", mu=mean, sigma=sigma_obs, observed=data["volatility"].to_numpy()
        )

        trace = pm.sample(
            draws=draws,
            tune=tune,
            chains=1,
            progressbar=False,
            random_seed=0,
        )
        ppc = pm.sample_posterior_predictive(trace, progressbar=False)

    return InferenceResult(trace=trace, ppc=ppc)


def sample_predictive(
    result: InferenceResult, new_times: np.ndarray, new_sectors: List[str]
) -> pd.DataFrame:
    """Sample posterior predictive for new times and sectors."""

    posterior = result.trace.posterior
    sectors = list(posterior.coords["sector"].values)
    sector_idx = [sectors.index(s) for s in new_sectors]

    mu = posterior["mu"].stack(sample=("chain", "draw")).values
    beta = posterior["beta"].stack(sample=("chain", "draw")).values
    sigma = posterior["sigma_obs"].stack(sample=("chain", "draw")).values
    alpha = (
        posterior["alpha"]
        .stack(sample=("chain", "draw"))
        .transpose("sample", "sector")
        .values
    )

    rng = np.random.default_rng(0)
    preds = []
    for idx, t in zip(sector_idx, new_times):
        mean = mu + alpha[:, idx] + beta * t
        draws = rng.normal(mean, sigma)
        preds.append(draws)
    arr = np.column_stack(preds)

    return pd.DataFrame(
        {
            "mean": arr.mean(axis=0),
            "lower95": np.percentile(arr, 2.5, axis=0),
            "upper95": np.percentile(arr, 97.5, axis=0),
        }
    )
