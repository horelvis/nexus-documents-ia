"""Redis-based session management for forge workflows."""

import json
import logging
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.schemas.session import ForgeSession, SessionStatus

logger = logging.getLogger(__name__)

PREFIX = "emma:forge_session"


class SessionStore:
    """Manages forge sessions in Redis with binary blob storage."""

    def __init__(self):
        settings = get_settings()
        self.ttl = settings.forge_session_ttl
        self._redis: aioredis.Redis | None = None
        self._redis_url = f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=False)
        return self._redis

    def _key(self, session_id: str, suffix: str = "") -> str:
        if suffix:
            return f"{PREFIX}:{session_id}:{suffix}"
        return f"{PREFIX}:{session_id}"

    async def create_session(self, user_id: str) -> ForgeSession:
        """Create a new forge session."""
        session_id = f"forge_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        session = ForgeSession(
            session_id=session_id,
            user_id=user_id,
            status=SessionStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
        r = await self._get_redis()
        await r.setex(
            self._key(session_id),
            self.ttl,
            json.dumps(session.model_dump()).encode(),
        )
        return session

    async def get_session(self, session_id: str) -> ForgeSession | None:
        """Retrieve session metadata."""
        r = await self._get_redis()
        data = await r.get(self._key(session_id))
        if not data:
            return None
        return ForgeSession(**json.loads(data))

    async def update_session(self, session: ForgeSession) -> None:
        """Update session metadata, refreshing TTL."""
        session.updated_at = datetime.now(timezone.utc).isoformat()
        r = await self._get_redis()
        await r.setex(
            self._key(session.session_id),
            self.ttl,
            json.dumps(session.model_dump()).encode(),
        )

    async def store_blob(self, session_id: str, suffix: str, data: bytes) -> None:
        """Store binary data (DOCX/PDF bytes) attached to a session."""
        r = await self._get_redis()
        await r.setex(self._key(session_id, suffix), self.ttl, data)

    async def get_blob(self, session_id: str, suffix: str) -> bytes | None:
        """Retrieve binary data attached to a session."""
        r = await self._get_redis()
        return await r.get(self._key(session_id, suffix))

    async def delete_session(self, session_id: str) -> None:
        """Delete a session and all associated blobs."""
        r = await self._get_redis()
        keys = await r.keys(f"{PREFIX}:{session_id}*")
        if keys:
            await r.delete(*keys)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None


_store = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store
