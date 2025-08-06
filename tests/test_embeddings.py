import pathlib
import sys

# Ensure package root on path for direct pytest invocation
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sentiment_bot import embeddings


def test_encode_shape() -> None:
    vec = embeddings.encode("hello world")
    assert len(vec) == embeddings._dim
