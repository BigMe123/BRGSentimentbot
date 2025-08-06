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
    """Launch a simple chat interface backed by :class:`ChatAgent`."""

    vector_path = Path(os.getenv("VECTOR_INDEX_PATH", settings.VECTOR_INDEX_PATH))
    openai_key = os.getenv("OPENAI_API_KEY", "")

    embeddings = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
    if vector_path.exists():
        vs = FAISS.load_local(
            str(vector_path), embeddings, allow_dangerous_deserialization=True
        )
    else:
        vs = FAISS.from_texts([], embeddings)

    agent = ChatAgent(vs, openai_key)

    with gr.Blocks() as demo:
        chatbot = gr.Chatbot()
        msg = gr.Textbox(placeholder="Ask something...")

        def respond(message: str, history: list[tuple[str, str]]):
            reply = agent.ask(message)
            history = history + [(message, reply)]
            return "", history

        msg.submit(respond, [msg, chatbot], [msg, chatbot])

    demo.launch(server_port=settings.GRADIO_PORT, share=False)
