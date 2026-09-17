"""Realtime layer (spec §15): backend → WebSocket → dashboard. MVP broadcast stub."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

ws_router = APIRouter()
_clients: set[WebSocket] = set()


@ws_router.websocket("/ws/inbox")
async def inbox_ws(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive; client echoes
    except WebSocketDisconnect:
        _clients.discard(ws)


async def broadcast(event: dict) -> None:
    for ws in list(_clients):
        try:
            await ws.send_json(event)
        except Exception:
            _clients.discard(ws)
