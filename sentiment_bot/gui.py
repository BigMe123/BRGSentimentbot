"""Gradio web interface for the bot."""

from __future__ import annotations

import os
from pathlib import Path

import gradio as gr
from langchain.embeddings import SentenceTransformerEmbeddings
from langchain.vectorstores import FAISS

from .chat_agent import ChatAgent
from .config import settings


def launch() -> None:  # pragma: no cover - requires network
    embeddings = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
    path = Path("faiss_index")
    if path.exists():
        vs = FAISS.load_local(
            str(path), embeddings, allow_dangerous_deserialization=True
        )
    else:  # empty store
        vs = FAISS.from_texts([], embeddings)
    agent = ChatAgent(vs, os.getenv("OPENAI_API_KEY", "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"))

    def _chat(message, history):
        answer = agent.ask(message)
        return answer, history + [(message, answer)]

    iface = gr.ChatInterface(_chat)
    iface.launch(server_port=settings.GRADIO_PORT, share=False)
