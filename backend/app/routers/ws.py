"""Phase 12 — authenticated WebSocket /ws. JWT via ?token=... query param."""
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.security import decode_token
from app.websocket import hub

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, token: str = Query(default="")):
    try:
        claims = decode_token(token) if token else {}
        tenant_id = claims.get("tenant_id")
        if not isinstance(tenant_id, int):
            await websocket.close(code=4401)
            return
    except Exception:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    await hub.register(tenant_id, websocket)
    try:
        await websocket.send_json({"type": "hello", "tenant_id": tenant_id})
        while True:
            msg = await websocket.receive_text()
            # Echo ping to confirm liveness; cheap keep-alive for Flutter client.
            await websocket.send_json({"type": "ack", "echo": msg[:100]})
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unregister(tenant_id, websocket)
