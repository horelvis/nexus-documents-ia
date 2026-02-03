"""WebSocket Manager — Real-time notification push.

Manages WebSocket connections per user, listening on a Redis Pub/Sub
channel for new notifications and forwarding them to connected clients.

Usage (in FastAPI router):
    @app.websocket("/emma/ws/notifications")
    async def ws_notifications(websocket: WebSocket):
        user_id = await authenticate_ws(websocket)
        await ws_manager.connect(websocket, user_id)
        try:
            while True:
                await websocket.receive_text()  # Keep-alive
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket, user_id)
"""
import asyncio
import json
import logging
from collections import defaultdict
from typing import Dict, List, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages per-user WebSocket connections for notification push."""

    def __init__(self):
        # user_id → set of active WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        self._redis_listener_task = None

    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        self._connections[user_id].add(websocket)
        logger.info(f"WebSocket connected: user={user_id} (total={self._total_connections()})")

        # Start Redis listener if not running
        if self._redis_listener_task is None or self._redis_listener_task.done():
            self._redis_listener_task = asyncio.create_task(self._redis_listener())

    def disconnect(self, websocket: WebSocket, user_id: str):
        """Remove a WebSocket connection."""
        self._connections[user_id].discard(websocket)
        if not self._connections[user_id]:
            del self._connections[user_id]
        logger.info(f"WebSocket disconnected: user={user_id} (total={self._total_connections()})")

    async def send_to_user(self, user_id: str, data: dict):
        """Send data to all connections of a specific user."""
        connections = self._connections.get(user_id, set())
        dead = set()
        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            connections.discard(ws)

    async def broadcast_to_tenant(self, tenant_id: str, data: dict):
        """Broadcast to all connected users (used for system notifications)."""
        for user_id, connections in self._connections.items():
            dead = set()
            for ws in connections:
                try:
                    await ws.send_json(data)
                except Exception:
                    dead.add(ws)
            for ws in dead:
                connections.discard(ws)

    async def _redis_listener(self):
        """Listen on Redis Pub/Sub for notifications and push to WebSockets."""
        try:
            import redis.asyncio as aioredis
            from app.core.config import settings

            r = aioredis.Redis(
                host=getattr(settings, "REDIS_HOST", "redis"),
                port=int(getattr(settings, "REDIS_PORT", 6379)),
                decode_responses=True,
            )
            pubsub = r.pubsub()
            await pubsub.subscribe("emma:notifications:realtime")

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    notification = json.loads(message["data"])
                    user_id = notification.get("user_id", "")

                    if user_id == "system":
                        # Broadcast to all connected users
                        await self.broadcast_to_tenant(
                            notification.get("tenant_id", ""),
                            notification,
                        )
                    else:
                        await self.send_to_user(user_id, notification)

                except Exception as e:
                    logger.error(f"Error processing WS notification: {e}")

        except Exception as e:
            logger.error(f"Redis WS listener failed: {e}")
            # Auto-restart after delay
            await asyncio.sleep(5)
            if self._total_connections() > 0:
                self._redis_listener_task = asyncio.create_task(self._redis_listener())

    def _total_connections(self) -> int:
        return sum(len(conns) for conns in self._connections.values())


# Global singleton
ws_manager = WebSocketManager()
