"""Phase 12: per-tenant WebSocket.

Clients connect to /ws?token=<JWT>. We authenticate from the query string
(WebSockets don't support Authorization headers reliably in browsers), scope
the socket to that JWT's tenant, and register in the hub."""
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.security import decode_token
from app.services import ws_hub

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: str = Query(...)):
    try:
        payload = decode_token(token)
        tenant_id = int(payload["tid"])
    except Exception:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws.accept()
    await ws_hub.register(tenant_id, ws)
    try:
        await ws.send_json({"type": "hello", "payload": {"tenant_id": tenant_id}})
        while True:
            # We don't expect client-sent messages, but keep the socket alive.
            # If the client sends anything, echo a pong for debugging.
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_json({"type": "pong", "payload": {}})
    except WebSocketDisconnect:
        pass
    finally:
        await ws_hub.unregister(tenant_id, ws)
