"""Gradio web interface for the bot."""

from __future__ import annotations

import gradio as gr

from .chat_agent import chat_loop
from .config import settings


def launch() -> None:  # pragma: no cover - requires network
    def _chat(message, history):
        return "No data", history + [(message, "No data")]

    iface = gr.ChatInterface(_chat)
    iface.launch(server_port=settings.GRADIO_PORT, share=False)
