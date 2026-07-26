"""WebSocket endpoint for real-time task execution logs."""

import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from qd_server.services.log_stream import log_stream

logger = logging.getLogger("qd2.ws")

router = APIRouter()


async def _authenticate_ws(token: str) -> int | None:
    """Validate JWT and return user_id, or None."""
    from qd_server.middleware.auth import decode_token

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        return int(payload["sub"])
    except Exception:
        return None


@router.websocket("/api/ws/logs")
async def ws_logs(websocket: WebSocket, token: str = Query("")):
    """Real-time task execution log stream (auth via ?token=)."""
    user_id = await _authenticate_ws(token)
    if user_id is None:
        await websocket.close(code=4401, reason="Unauthorized")
        return

    await websocket.accept()
    q = log_stream.subscribe(user_id)

    try:
        # send buffered history first
        for event in log_stream.buffer(user_id):
            await websocket.send_json({**event, "replay": True})

        while True:
            # heartbeat every 30s to keep connection alive through proxies
            try:
                event = await asyncio.wait_for(q.get(), timeout=30)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WS closed: %s", e)
    finally:
        log_stream.unsubscribe(user_id, q)
