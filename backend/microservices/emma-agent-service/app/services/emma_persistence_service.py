"""
Emma Session Persistence Service

Provides durable storage for Emma AI chat session metadata in PostgreSQL.

Architecture (Phase 1c — dual persistence with PostgresSaver):
    ┌─────────────────────────────────────────────────────────────────────┐
    │                     Session Flow                                     │
    │                                                                      │
    │   User sends message                                                 │
    │         │                                                            │
    │         ▼                                                            │
    │   ┌──────────────────┐                                               │
    │   │  PostgresSaver   │  ◄── Conversation state (LangGraph)           │
    │   │  (checkpoints)   │      - Full messages + graph state            │
    │   └──────────────────┘      - Thread-scoped, auto-restored           │
    │                                                                      │
    │   ┌──────────────────┐                                               │
    │   │   POSTGRESQL     │  ◄── UI metadata (slim)                       │
    │   │  emma_sessions   │      - Title, timestamps, archive/pin         │
    │   │  (metadata only) │      - Document context, last message preview │
    │   └──────────────────┘                                               │
    │                                                                      │
    │   ┌──────────────────┐                                               │
    │   │      REDIS       │  ◄── Session TTL tracking                     │
    │   │  emma:thread:    │      - Active session keepalive               │
    │   └──────────────────┘                                               │
    │                                                                      │
    └─────────────────────────────────────────────────────────────────────┘

When LANGGRAPH_CHECKPOINTER_ENABLED=true (default), full conversation
history is stored by PostgresSaver.  This service stores only UI metadata
(title, archive/pin, document_context, message_count, previews).

When checkpointer is disabled (fallback), this service stores full messages
in the JSONB column as before.

Usage:
    persistence = get_emma_persistence_service()

    # Save a message pair (called after each Emma response)
    await persistence.save_message(
        session_id="thread-123",
        user_id="user-456",
        tenant_id="tenant-789",
        user_message="What contracts do we have?",
        assistant_response="I found 5 contracts...",
        sources=[{"document_id": "...", "title": "..."}],
        session_metadata={"knowledge_source": "documents"}
    )

    # List user's sessions
    sessions = await persistence.get_user_sessions(user_id, tenant_id)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID
import uuid as uuid_module

import asyncpg
import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis key prefix (must match emma.py)
THREAD_KEY_PREFIX = "emma:thread:"
THREAD_TTL_SECONDS = 3600


class EmmaPersistenceService:
    """
    Service for persisting Emma chat sessions to PostgreSQL.

    Follows the same pattern as AnalysisPersistenceService:
    - Uses asyncpg connection pool for efficient database access
    - Singleton pattern for resource management
    - Non-blocking saves (called via asyncio.create_task)
    """

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._redis: Optional[redis.Redis] = None
        self._db_url = self._get_db_url()

    def _get_db_url(self) -> str:
        """Convert SQLAlchemy URL to asyncpg format."""
        db_url = settings.database_url
        if "postgresql+asyncpg://" in db_url:
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        return db_url

    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._db_url,
                min_size=1,
                max_size=5,
                command_timeout=30
            )
        return self._pool

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._redis is None:
            self._redis = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
            )
        return self._redis

    async def close(self):
        """Close connection pool and Redis client."""
        if self._pool:
            await self._pool.close()
            self._pool = None
        if self._redis:
            await self._redis.close()
            self._redis = None

    # =========================================================================
    # Core Persistence Methods
    # =========================================================================

    async def touch_session(self, session_id: str, tenant_id: str) -> None:
        """
        Extend TTL of Redis keys associated with a session.

        When checkpointer is active, only the session metadata key is touched
        (conversation state lives in PostgresSaver, not Redis).

        Args:
            session_id: Session/thread identifier
            tenant_id: Tenant identifier
        """
        try:
            r = await self._get_redis()
            keys = [f"{THREAD_KEY_PREFIX}{session_id}"]
            # Legacy conv key only needed without checkpointer
            if not settings.langgraph_checkpointer_enabled:
                keys.append(f"emma:conv:{tenant_id}:{session_id}")
            for key in keys:
                if await r.exists(key):
                    await r.expire(key, THREAD_TTL_SECONDS)
                    logger.debug(f"Extended TTL for {key}")
        except Exception as e:
            logger.warning(f"Failed to touch session {session_id}: {e}")

    async def save_message(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
        user_message: str,
        assistant_response: str,
        sources: Optional[List[Dict[str, Any]]] = None,
        tools_used: Optional[List[str]] = None,
        knowledge_source: Optional[str] = None,
        session_metadata: Optional[Dict[str, Any]] = None,
        document_context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Save a conversation turn to PostgreSQL.

        When PostgresSaver checkpointer is active, only UI metadata is stored
        (title, message_count, timestamps, document_context, last_message_preview).
        Full conversation history lives in the PostgresSaver checkpoint tables.

        When checkpointer is disabled (fallback), full messages are stored in
        the JSONB column as before.

        This method is designed to be called via asyncio.create_task()
        after each Emma response, so it doesn't block the user.

        Args:
            session_id: Thread/session identifier
            user_id: User's UUID
            tenant_id: Tenant's UUID
            user_message: The user's query
            assistant_response: Emma's response
            sources: Optional list of document sources cited
            tools_used: Optional list of tools that were called
            knowledge_source: "documents" | "graph" | "general"
            session_metadata: Additional session_metadata to merge
            document_context: Document context to persist (file IDs, etc.)

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            pool = await self._get_pool()
            now = datetime.now(timezone.utc)
            use_checkpointer = settings.langgraph_checkpointer_enabled

            async with pool.acquire() as conn:
                # Check if session exists
                session = await conn.fetchrow(
                    """
                    SELECT id, messages, message_count, title, session_metadata
                    FROM emma_sessions
                    WHERE session_id = $1
                    """,
                    session_id
                )

                # Build message objects (full or slim depending on checkpointer)
                user_msg = {
                    "role": "user",
                    "content": user_message,
                    "timestamp": now.isoformat()
                }

                assistant_msg = {
                    "role": "assistant",
                    "content": assistant_response,
                    "timestamp": now.isoformat()
                }

                if sources:
                    assistant_msg["sources"] = sources
                if tools_used:
                    assistant_msg["tools_used"] = tools_used
                if knowledge_source:
                    assistant_msg["knowledge_source"] = knowledge_source

                if session:
                    # Update existing session
                    existing_session_metadata = session['session_metadata'] or {}
                    if isinstance(existing_session_metadata, str):
                        existing_session_metadata = json.loads(existing_session_metadata)
                    if session_metadata:
                        existing_session_metadata.update(session_metadata)
                    if knowledge_source:
                        existing_session_metadata["last_knowledge_source"] = knowledge_source
                    if document_context:
                        existing_session_metadata["document_context"] = document_context

                    if use_checkpointer:
                        # Slim mode: only update metadata + message_count + preview
                        # Full messages are in PostgresSaver checkpoint tables.
                        new_count = (session['message_count'] or 0) + 2
                        # Store last message preview for session list display
                        existing_session_metadata["last_user_message"] = user_message[:150]
                        existing_session_metadata["last_assistant_preview"] = assistant_response[:150]

                        await conn.execute(
                            """
                            UPDATE emma_sessions
                            SET message_count = $2,
                                session_metadata = $3,
                                last_message_at = $4,
                                updated_at = $4
                            WHERE id = $1
                            """,
                            session['id'],
                            new_count,
                            json.dumps(existing_session_metadata),
                            now
                        )
                        logger.debug(f"Updated session {session_id}: count={new_count} (slim, checkpointer)")

                    else:
                        # Legacy mode: store full messages in JSONB
                        existing_messages = session['messages'] or []
                        if isinstance(existing_messages, str):
                            existing_messages = json.loads(existing_messages)
                        existing_messages.append(user_msg)
                        existing_messages.append(assistant_msg)

                        await conn.execute(
                            """
                            UPDATE emma_sessions
                            SET messages = $2,
                                message_count = $3,
                                session_metadata = $4,
                                last_message_at = $5,
                                updated_at = $5
                            WHERE id = $1
                            """,
                            session['id'],
                            json.dumps(existing_messages),
                            len(existing_messages),
                            json.dumps(existing_session_metadata),
                            now
                        )
                        logger.debug(f"Updated session {session_id}: {len(existing_messages)} messages (legacy)")

                else:
                    # Create new session
                    new_id = uuid_module.uuid4()

                    # Auto-generate title from first user message
                    title = user_message[:100]
                    if len(user_message) > 100:
                        title += "..."

                    # Build session metadata
                    new_metadata = session_metadata or {}
                    if knowledge_source:
                        new_metadata["last_knowledge_source"] = knowledge_source
                    if document_context:
                        new_metadata["document_context"] = document_context

                    if use_checkpointer:
                        # Slim mode: empty messages array, store previews in metadata
                        new_metadata["last_user_message"] = user_message[:150]
                        new_metadata["last_assistant_preview"] = assistant_response[:150]
                        messages_json = json.dumps([])
                        message_count = 2  # Track count even though messages are in checkpointer
                    else:
                        # Legacy mode: full messages
                        messages_json = json.dumps([user_msg, assistant_msg])
                        message_count = 2

                    await conn.execute(
                        """
                        INSERT INTO emma_sessions (
                            id, user_id, tenant_id, session_id,
                            title, messages, message_count,
                            is_archived, is_pinned, session_metadata,
                            last_message_at, created_at, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $11, $11)
                        """,
                        new_id,
                        UUID(user_id),
                        UUID(tenant_id),
                        session_id,
                        title,
                        messages_json,
                        message_count,
                        False,  # is_archived
                        False,  # is_pinned
                        json.dumps(new_metadata),
                        now
                    )

                    logger.info(f"Created new session {session_id} for user {user_id}")

                return True

        except Exception as e:
            logger.error(f"Failed to save message to session {session_id}: {e}")
            return False

    async def create_session(
        self,
        user_id: str,
        tenant_id: str,
        session_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new empty session explicitly.

        Used by the frontend to create a session before the first query,
        so the sidebar can show it immediately.

        Args:
            user_id: User's UUID
            tenant_id: Tenant's UUID
            session_id: Optional session ID (auto-generated if not provided)
            title: Optional title (defaults to "Nueva conversación")

        Returns:
            Created session dict, or None on failure
        """
        try:
            pool = await self._get_pool()
            now = datetime.now(timezone.utc)
            new_id = uuid_module.uuid4()
            if not session_id:
                session_id = str(uuid_module.uuid4())

            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO emma_sessions (
                        id, user_id, tenant_id, session_id,
                        title, messages, message_count,
                        is_archived, is_pinned, session_metadata,
                        last_message_at, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $11, $11)
                    """,
                    new_id,
                    UUID(user_id),
                    UUID(tenant_id),
                    session_id,
                    title or "Nueva conversación",
                    json.dumps([]),
                    0,
                    False,
                    False,
                    json.dumps({}),
                    now,
                )

            logger.info(f"Created empty session {session_id} for user {user_id}")
            return {
                "id": str(new_id),
                "user_id": user_id,
                "tenant_id": tenant_id,
                "session_id": session_id,
                "title": title or "Nueva conversación",
                "message_count": 0,
                "is_archived": False,
                "is_pinned": False,
                "created_at": now.isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            return None

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a session by its ID.

        Returns the full session data including all messages.
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        id, user_id, tenant_id, session_id,
                        title, messages, message_count, total_tokens,
                        is_archived, is_pinned, session_metadata,
                        last_message_at, created_at, updated_at
                    FROM emma_sessions
                    WHERE session_id = $1
                    """,
                    session_id
                )

                if not row:
                    return None

                messages = row['messages'] or []
                if isinstance(messages, str):
                    messages = json.loads(messages)
                metadata = row['session_metadata'] or {}
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)

                return {
                    "id": str(row['id']),
                    "user_id": str(row['user_id']),
                    "tenant_id": str(row['tenant_id']),
                    "session_id": row['session_id'],
                    "title": row['title'],
                    "messages": messages,
                    "message_count": row['message_count'],
                    "total_tokens": row['total_tokens'],
                    "is_archived": row['is_archived'],
                    "is_pinned": row['is_pinned'],
                    "metadata": metadata,  # Map to API field name
                    "last_message_at": row['last_message_at'].isoformat() if row['last_message_at'] else None,
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                    "updated_at": row['updated_at'].isoformat() if row['updated_at'] else None,
                }

        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None

    async def get_user_sessions(
        self,
        user_id: str,
        tenant_id: str,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        List sessions for a user.

        Returns paginated list with session summaries (not full messages).
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                # Build query
                where_clause = "user_id = $1 AND tenant_id = $2"
                params = [UUID(user_id), UUID(tenant_id)]
                param_idx = 3

                if not include_archived:
                    where_clause += " AND is_archived = false"

                # Get total count
                count_row = await conn.fetchrow(
                    f"SELECT COUNT(*) as total FROM emma_sessions WHERE {where_clause}",
                    *params
                )
                total = count_row['total']

                # Get sessions (ordered by pinned first, then last_message_at)
                # Slim query: only load messages when needed for preview extraction
                rows = await conn.fetch(
                    f"""
                    SELECT
                        id, session_id, title, message_count,
                        is_pinned, is_archived,
                        messages, session_metadata,
                        last_message_at, created_at
                    FROM emma_sessions
                    WHERE {where_clause}
                    ORDER BY is_pinned DESC, last_message_at DESC
                    LIMIT ${param_idx} OFFSET ${param_idx + 1}
                    """,
                    *params, limit, offset
                )

                sessions = []
                for row in rows:
                    # Try metadata previews first (checkpointer mode),
                    # fall back to scanning messages JSONB (legacy mode)
                    meta = row['session_metadata'] or {}
                    if isinstance(meta, str):
                        meta = json.loads(meta)

                    first_user_msg = meta.get("last_user_message")
                    last_assistant_msg = meta.get("last_assistant_preview")

                    # Fallback: extract from messages JSONB (legacy sessions)
                    if first_user_msg is None or last_assistant_msg is None:
                        messages = row['messages'] or []
                        if isinstance(messages, str):
                            messages = json.loads(messages)
                        for msg in messages:
                            if msg.get('role') == 'user' and first_user_msg is None:
                                first_user_msg = msg.get('content', '')[:150]
                                if len(msg.get('content', '')) > 150:
                                    first_user_msg += "..."
                            if msg.get('role') == 'assistant':
                                last_assistant_msg = msg.get('content', '')[:150]
                                if len(msg.get('content', '')) > 150:
                                    last_assistant_msg += "..."

                    sessions.append({
                        "id": str(row['id']),
                        "session_id": row['session_id'],
                        "title": row['title'] or (first_user_msg or "")[:100],
                        "message_count": row['message_count'],
                        "is_pinned": row['is_pinned'],
                        "is_archived": row['is_archived'],
                        "last_message_at": row['last_message_at'].isoformat() if row['last_message_at'] else None,
                        "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                        "first_message_preview": first_user_msg,
                        "last_message_preview": last_assistant_msg,
                    })

                return {
                    "sessions": sessions,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + len(sessions) < total
                }

        except Exception as e:
            logger.error(f"Failed to get sessions for user {user_id}: {e}")
            return {
                "sessions": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
                "has_more": False
            }

    async def update_session(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
        title: Optional[str] = None,
        is_archived: Optional[bool] = None,
        is_pinned: Optional[bool] = None
    ) -> bool:
        """
        Update session properties (title, archive status, pin status).

        Args:
            session_id: Session to update
            user_id: Must match session owner
            tenant_id: Must match session tenant
            title: New title (optional)
            is_archived: Archive status (optional)
            is_pinned: Pin status (optional)

        Returns:
            True if updated, False if not found or error
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                # Build dynamic update
                updates = ["updated_at = $4"]
                params = [session_id, UUID(user_id), UUID(tenant_id), datetime.now(timezone.utc)]
                param_idx = 5

                if title is not None:
                    updates.append(f"title = ${param_idx}")
                    params.append(title)
                    param_idx += 1

                if is_archived is not None:
                    updates.append(f"is_archived = ${param_idx}")
                    params.append(is_archived)
                    param_idx += 1

                if is_pinned is not None:
                    updates.append(f"is_pinned = ${param_idx}")
                    params.append(is_pinned)
                    param_idx += 1

                if len(updates) == 1:
                    # No changes requested
                    return True

                result = await conn.execute(
                    f"""
                    UPDATE emma_sessions
                    SET {', '.join(updates)}
                    WHERE session_id = $1 AND user_id = $2 AND tenant_id = $3
                    """,
                    *params
                )

                # Check if row was updated
                return "UPDATE 1" in result

        except Exception as e:
            logger.error(f"Failed to update session {session_id}: {e}")
            return False

    async def delete_session(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str
    ) -> bool:
        """
        Delete a session permanently.

        Also clears the session from Redis if present.
        """
        try:
            pool = await self._get_pool()
            redis_client = await self._get_redis()

            async with pool.acquire() as conn:
                result = await conn.execute(
                    """
                    DELETE FROM emma_sessions
                    WHERE session_id = $1 AND user_id = $2 AND tenant_id = $3
                    """,
                    session_id,
                    UUID(user_id),
                    UUID(tenant_id)
                )

                # Also clear from Redis
                key = f"{THREAD_KEY_PREFIX}{session_id}"
                await redis_client.delete(key)
                await redis_client.delete(f"{key}:knowledge_source")

                deleted = "DELETE 1" in result
                if deleted:
                    logger.info(f"Deleted session {session_id}")

                return deleted

        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False

    # =========================================================================
    # Redis Integration
    # =========================================================================

    async def load_session_to_redis(self, session_id: str) -> bool:
        """
        Load a session from PostgreSQL to Redis for continuing.

        When PostgresSaver checkpointer is active, conversation continuity
        is handled by the checkpointer — this method is a no-op that returns
        True (session is always "loaded" via the checkpoint).

        In legacy mode (no checkpointer), loads messages into Redis so
        Emma v2 can access them.

        Args:
            session_id: Session to load

        Returns:
            True if loaded successfully, False otherwise
        """
        # With checkpointer, conversation continuity is automatic —
        # the graph restores state from the checkpoint on ainvoke().
        if settings.langgraph_checkpointer_enabled:
            logger.debug(f"Session {session_id}: checkpointer active, no Redis load needed")
            return True

        try:
            session = await self.get_session(session_id)
            if not session:
                logger.warning(f"Session {session_id} not found in PostgreSQL")
                return False

            # Convert to Redis format (simplified messages)
            redis_messages = []
            for msg in session.get('messages', []):
                redis_messages.append({
                    "role": msg.get('role'),
                    "content": msg.get('content')
                })

            # Load into Redis
            redis_client = await self._get_redis()
            key = f"{THREAD_KEY_PREFIX}{session_id}"

            await redis_client.setex(
                key,
                THREAD_TTL_SECONDS,
                json.dumps(redis_messages)
            )

            # Also restore knowledge_source if available
            last_ks = session.get('metadata', {}).get('last_knowledge_source')
            if last_ks:
                await redis_client.setex(
                    f"{key}:knowledge_source",
                    THREAD_TTL_SECONDS,
                    last_ks
                )

            logger.info(
                f"Loaded session {session_id} to Redis: "
                f"{len(redis_messages)} messages, knowledge_source={last_ks}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to load session {session_id} to Redis: {e}")
            return False

    async def session_exists_in_redis(self, session_id: str) -> bool:
        """Check if a session is currently in Redis."""
        try:
            redis_client = await self._get_redis()
            key = f"{THREAD_KEY_PREFIX}{session_id}"
            return await redis_client.exists(key) > 0
        except Exception as e:
            logger.warning(f"Failed to check Redis for session {session_id}: {e}")
            return False


# =============================================================================
# Singleton Factory
# =============================================================================

_persistence_service: Optional[EmmaPersistenceService] = None


def get_emma_persistence_service() -> EmmaPersistenceService:
    """Get or create the persistence service singleton."""
    global _persistence_service
    if _persistence_service is None:
        _persistence_service = EmmaPersistenceService()
    return _persistence_service


async def close_emma_persistence_service() -> None:
    """Close the persistence service (call on shutdown)."""
    global _persistence_service
    if _persistence_service:
        await _persistence_service.close()
        _persistence_service = None
