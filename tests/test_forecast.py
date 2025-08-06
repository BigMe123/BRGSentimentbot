"""Tests for the lightweight forecasting models."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("torch")

from sentiment_bot.forecast import GANForecast, VAEForecast


@pytest.mark.parametrize("Model", [VAEForecast, GANForecast])
def test_forecast_shape_and_interval(Model) -> None:
    series = pd.Series(np.ones(20))
    df = Model().fit(series).forecast(5, samples=10)
    assert df.shape == (5, 3)
    assert ((df["upper"] - df["lower"]) >= 0).all()


@pytest.mark.parametrize("Model", [VAEForecast, GANForecast])
def test_forecast_mean_close_to_one(Model) -> None:
    series = pd.Series(np.ones(20))
    df = Model().fit(series).forecast(5, samples=10)
    assert np.max(np.abs(df["mean"].to_numpy() - 1.0)) < 0.1

