import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sentiment_bot.embeddings import encode


def test_encode_shape() -> None:
    arr = encode(["hello", "world"])
    assert arr.shape == (2, 384)
    assert arr.dtype == np.float32
