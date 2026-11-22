from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class RealtimeHub:
    """In-memory WebSocket connection hub organized by channels (user:<id>, role:<role>, trip:<id>, broadcast)."""

    def __init__(self) -> None:
        self._channels: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, websocket: WebSocket, channels: list[str]) -> None:
        await websocket.accept()
        for ch in channels:
            self._channels[ch].add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        empty = []
        for ch, sockets in self._channels.items():
            sockets.discard(websocket)
            if not sockets:
                empty.append(ch)
        for ch in empty:
            del self._channels[ch]

    async def publish(self, channels: list[str], event_type: str, payload: dict[str, Any]) -> None:
        message = {"event": event_type, "data": payload}
        targets: set[WebSocket] = set()
        for ch in channels:
            targets.update(self._channels.get(ch, set()))

        stale: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws)


realtime_hub = RealtimeHub()
