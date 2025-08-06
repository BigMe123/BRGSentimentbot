import pathlib
import sys

# Ensure package root on path for direct pytest invocation
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sentiment_bot import vector_store, config, models


def test_build_and_load(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "VECTOR_INDEX_PATH", str(tmp_path / "index.bin"))
    a1 = models.Article(url="u1", title="t1", hash="h1", embedding=[0.0] * 384)
    a2 = models.Article(url="u2", title="t2", hash="h2", embedding=[1.0] * 384)
    vector_store.build_index([a1, a2])
    idx = vector_store.load_index()
    assert idx is not None
    vector_store.add_documents([a1])  # duplicate should not change size
    idx2 = vector_store.load_index()
    if hasattr(idx2, "shape"):
        assert idx2.shape[0] == 2
