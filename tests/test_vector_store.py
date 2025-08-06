import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

pytest.importorskip("faiss")
from sentiment_bot.vector_store import VectorStore


def test_identity_query(tmp_path) -> None:
    path = tmp_path / "store.gz"
    vs = VectorStore(3, path)
    ids = [0, 1, 2]
    vectors = np.eye(3, dtype=np.float32)
    vs.add(ids, vectors)
    for i in range(3):
        res = vs.query(vectors[i], topk=1)
        assert res[0] == ids[i]
    vs.save()
    vs2 = VectorStore.load(path)
    assert vs2.query([1, 0, 0], topk=1)[0] == 0
