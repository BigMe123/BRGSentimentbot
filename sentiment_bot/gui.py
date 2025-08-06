# sentiment_bot/gui.py
"""Gradio web interface for the sentiment bot."""

from __future__ import annotations
import os
from pathlib import Path

import gradio as gr
from langchain.embeddings import SentenceTransformerEmbeddings
from langchain.vectorstores import FAISS

from .chat_agent import ChatAgent
from .config import settings

def launch() -> None:  # pragma: no cover – requires network & UI
    """
    Start a Gradio chat UI on settings.GRADIO_PORT.
    Loads an existing FAISS index from VECTOR_INDEX_PATH or creates an empty one.
    """

    # Prepare embeddings & vector store
    embeddings = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
    vector_path = Path(os.getenv("VECTOR_INDEX_PATH", settings.VECTOR_INDEX_PATH))

    if vector_path.exists():
        vs = FAISS.load_local(
            str(vector_path),
            embeddings,
            allow_dangerous_deserialization=True
        )
    else:
        vs = FAISS.from_texts([], embeddings)

    # Instantiate chat agent with your OpenAI API key
    openai_key = "sk-REPLACE_WITH_YOUR_API_KEY"
    agent = ChatAgent(vs, openai_key)

    # Build Gradio UI
    with gr.Blocks(title="Sentiment Bot Chat") as demo:
        chatbot = gr.Chatbot(label="Bot")
        user_input = gr.Textbox(
            placeholder="Ask me about recent sentiment trends…",
            label="Your question",
        )
        send_btn = gr.Button("Send")

        def respond(message: str, history: list[tuple[str, str]]):
            reply = agent.ask(message)
            history = history + [(message, reply)]
            return "", history

        send_btn.click(respond, inputs=[user_input, chatbot], outputs=[user_input, chatbot])
        user_input.submit(respond, inputs=[user_input, chatbot], outputs=[user_input, chatbot])

    demo.launch(
        server_name="0.0.0.0",
        server_port=settings.GRADIO_PORT,
        share=False,
    )
