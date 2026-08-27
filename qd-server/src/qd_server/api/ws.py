"""WebSocket endpoint for real-time task execution logs."""

import asyncio
import logging
import secrets
import threading

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from qd_server.services.log_stream import log_stream

logger = logging.getLogger("qd2.ws")

router = APIRouter()


class _ConnectionSlots:
    def __init__(self) -> None:
        self._active = 0
        self._lock = threading.Lock()

    def acquire(self, maximum: int) -> bool:
        with self._lock:
            if self._active >= maximum:
                return False
            self._active += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)


_connection_slots = _ConnectionSlots()


async def _authenticate_ws(token: str) -> int | None:
    """Validate JWT and current account status, then return user_id."""
    from sqlmodel import select

    from qd_server.config import get_settings
    from qd_server.middleware.auth import decode_token
    from qd_server.models.user import User

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        user_id = int(payload["sub"])
        async with get_settings().db.scoped_session() as session:
            result = await session.execute(
                select(User.id).where(User.id == user_id, User.is_active == True)
            )
            return user_id if result.scalar_one_or_none() is not None else None
    except Exception:
        return None


@router.websocket("/api/ws/logs")
async def ws_logs(websocket: WebSocket, token: str = Query("")):
    """Real-time task execution log stream (auth via ?token=)."""
    user_id = await _authenticate_ws(token)
    if user_id is None:
        await websocket.close(code=4401, reason="Unauthorized")
        return

    from qd_server.config import get_settings

    settings = get_settings()
    if not _connection_slots.acquire(settings.ws_max_connections):
        await websocket.close(code=4429, reason="Too many WebSocket connections")
        return

    q = None
    try:
        await websocket.accept()
        q = log_stream.subscribe(user_id, settings.ws_max_queue_size)
        # send buffered history first
        for event in log_stream.buffer(user_id):
            await websocket.send_json({**event, "replay": True})

        loop = asyncio.get_running_loop()
        next_ping_at = loop.time() + settings.ws_ping_interval
        while True:
            wait_seconds = max(0, next_ping_at - loop.time())
            try:
                event = await asyncio.wait_for(q.get(), timeout=wait_seconds)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                ping_id = secrets.token_urlsafe(8)
                await websocket.send_json({"type": "ping", "id": ping_id})
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_json(),
                        timeout=settings.ws_ping_timeout,
                    )
                except asyncio.TimeoutError:
                    await websocket.close(code=4408, reason="WebSocket heartbeat timed out")
                    return
                if message.get("type") != "pong" or message.get("id") != ping_id:
                    await websocket.close(code=4408, reason="WebSocket heartbeat timed out")
                    return
                next_ping_at = loop.time() + settings.ws_ping_interval
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WS closed: %s", e)
    finally:
        if q is not None:
            log_stream.unsubscribe(user_id, q)
        _connection_slots.release()
