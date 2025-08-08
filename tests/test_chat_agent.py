import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest
from sentiment_bot.config import SAFE_MODE

if SAFE_MODE:
    pytest.skip("SAFE_MODE enabled", allow_module_level=True)

openai = pytest.importorskip("openai")
emb_mod = pytest.importorskip("langchain.embeddings")
vec_mod = pytest.importorskip("langchain.vectorstores")
import sentiment_bot.chat_agent as ca  # noqa: E402

FakeEmbeddings = emb_mod.FakeEmbeddings
FAISS = vec_mod.FAISS


def test_chat_agent(monkeypatch):
    embeddings = FakeEmbeddings(size=3)
    vs = FAISS.from_texts(["a", "b"], embeddings)

    class DummyResp:
        choices = [types.SimpleNamespace(message=types.SimpleNamespace(content="hi"))]
        def dict(self):
            return {"choices": [{"message": {"role": "assistant", "content": "hi"}}]}

    dummy_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=lambda **kwargs: DummyResp())
        )
    )
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: dummy_client)

    agent = ca.ChatAgent(vs, openai_api_key="key")
    assert agent.ask("hello") == "hi"
