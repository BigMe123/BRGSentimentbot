import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sentiment_bot.bayesian import fit_hierarchical, sample_predictive


def simulate_data() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n = 100
    times = np.arange(n)
    sectors = rng.choice(["s1", "s2"], size=n)
    alpha = {"s1": 0.1, "s2": -0.1}
    mu = 0.5
    beta = 0.2
    vol = mu + np.array([alpha[s] for s in sectors]) + beta * times
    vol += rng.normal(0, 0.1, size=n)
    return pd.DataFrame({"sector": sectors, "time": times, "volatility": vol})


def test_fit_and_predict() -> None:
    df = simulate_data()
    res = fit_hierarchical(df, draws=200, tune=200)
    mu_post = res.trace.posterior["mu"].values.mean()
    assert abs(mu_post - 0.5) < 0.2

    preds = sample_predictive(res, np.array([101, 102]), ["s1", "s2"])
    assert list(preds.columns) == ["mean", "lower95", "upper95"]
    assert preds.shape == (2, 3)
