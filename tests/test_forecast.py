import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")
from sentiment_bot.forecast import TimeSeriesGAN


def test_forecast_shape():
    series = pd.Series(np.sin(np.linspace(0, 1, 30)))
    model = TimeSeriesGAN(seq_len=5).fit(series, epochs=5)
    result = model.forecast(3, samples=5)
    df = result.forecast
    assert list(df.columns) == ["mean", "lower", "upper"]
    assert len(df) == 3
