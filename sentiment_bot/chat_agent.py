"""Retrieval augmented chat agent."""

from __future__ import annotations

from typing import List, Tuple

from langchain.chains import ConversationalRetrievalChain
from langchain.chat_models import ChatOpenAI
from langchain.embeddings import SentenceTransformerEmbeddings  # noqa: F401
from langchain.vectorstores.faiss import FAISS


class ChatAgent:
    """Thin wrapper around a :class:`ConversationalRetrievalChain`."""

    def __init__(self, vs: FAISS, openai_api_key: str) -> None:
        llm = ChatOpenAI(openai_api_key=openai_api_key, temperature=0)
        self.chain = ConversationalRetrievalChain.from_llm(llm, vs.as_retriever())
        self.history: List[Tuple[str, str]] = []

    def ask(self, query: str) -> str:
        """Ask a question and return the answer."""
        print(f"[DEBUG] Prompt sent: {query}")
        result = self.chain({"question": query, "chat_history": self.history})
        response: str | None = result.get("answer")
        print(f"[DEBUG] Response: {response}")
        self.history.append((query, response or ""))
        if response:
            return response.strip()
        else:
            print(
                "[ERROR] Model returned None. Possible issue with OpenAI API or input."
            )
            return (
                "[Error] No response received from model. Try again later or check logs."
            )
