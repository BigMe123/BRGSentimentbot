"""Interactive chat agent over stored documents."""

from __future__ import annotations


def chat_loop() -> None:
    """Simple REPL that echoes user input.

    A full implementation would integrate LangChain with the vector store.
    The minimal version keeps the interface without heavy dependencies.
    """

    print("Type 'exit' to quit.")
    while True:
        try:
            q = input(">> ")
        except EOFError:  # pragma: no cover - manual
            break
        if q.strip().lower() in {"exit", "quit"}:
            break
        print("No documents available.")
