"""Hierarchical Bayesian volatility model using PyMC."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class InferenceResult:
    """Container for fitted model and posterior predictive samples."""

    trace: object
    ppc: object


def fit_hierarchical(data: pd.DataFrame) -> InferenceResult:
    """Fit a simple hierarchical model.

    Parameters
    ----------
    data: DataFrame
        Columns: ``sector``, ``time`` and ``volatility``.
    """

    import pymc as pm  # Imported lazily to keep import time fast

    sectors = data["sector"].unique()
    sector_idx = pd.Categorical(data["sector"], sectors).codes
    with pm.Model() as model:
        mu_global = pm.Normal("mu_global", 0.0, 1.0)
        sigma_global = pm.HalfNormal("sigma_global", 1.0)
        alpha = pm.Normal("alpha", mu=0.0, sigma=sigma_global, shape=len(sectors))
        beta_time = pm.Normal("beta_time", 0.0, 1.0)
        mu = mu_global + alpha[sector_idx] + beta_time * data["time"].values
        sigma = pm.HalfNormal("sigma", 1.0)
        pm.Normal(
            "obs",
            mu=mu,
            sigma=sigma,
            observed=data["volatility"].values,
        )
        trace = pm.sample(100, tune=100, chains=1, progressbar=False, random_seed=0)
        ppc = pm.sample_posterior_predictive(trace, progressbar=False)
    return InferenceResult(trace=trace, ppc=ppc)


def posterior_predictive_samples(result: InferenceResult) -> pd.Series:
    """Return posterior predictive mean as a series."""

    import numpy as np

    draws = result.ppc["obs"]
    mean = draws.mean(axis=0)
    return pd.Series(mean)
