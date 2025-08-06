import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import sentiment_bot.chat_agent as ca
from langchain_community.vectorstores import FAISS
from langchain.embeddings.base import Embeddings


class DummyEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[0.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [0.0, 0.0, 0.0]


class DummyChain:
    def __call__(self, inputs):
        return {"answer": "hi"}


def test_chat_agent(monkeypatch):
    embeddings = DummyEmbeddings()
    vs = FAISS.from_texts(["a", "b"], embedding=embeddings)

    dummy = DummyChain()
    monkeypatch.setattr(
        ca,
        "ConversationalRetrievalChain",
        types.SimpleNamespace(from_llm=lambda llm, retriever: dummy),
    )
    monkeypatch.setattr(ca, "ChatOpenAI", lambda **kwargs: object())

    agent = ca.ChatAgent(vs, openai_api_key="key")
    ans = agent.ask("hello")
    assert isinstance(ans, str) and len(ans) > 0
