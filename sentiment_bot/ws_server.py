"""WebSocket server broadcasting snapshots."""

from __future__ import annotations

import asyncio
import json
from typing import Callable, Iterable

import websockets

from .config import settings


async def serve(get_snapshot: Callable[[], dict]) -> None:  # pragma: no cover - network
    """Start a WebSocket server that sends ``get_snapshot`` result every 5s."""

    clients: set[websockets.WebSocketServerProtocol] = set()

    async def handler(websocket):
        clients.add(websocket)
        try:
            await asyncio.Future()
        finally:
            clients.remove(websocket)

    async def broadcaster():
        while True:
            if clients:
                payload = json.dumps(get_snapshot())
                await asyncio.gather(*(c.send(payload) for c in clients))
            await asyncio.sleep(5)

    async with websockets.serve(handler, "0.0.0.0", settings.WEBSOCKET_PORT):
        await broadcaster()
