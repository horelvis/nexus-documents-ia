"""
Conversation Memory for Emma.

Provides persistent conversation storage using Redis with automatic
TTL expiration.

Key format: emma:conv:{session_id}
TTL: 30 minutes by default (configurable)
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

import redis.asyncio as redis

from app.core.config import settings
from .types import ConversationContext, Message, MessageRole

logger = logging.getLogger(__name__)


class ConversationMemory:
    """
    Redis-backed conversation memory.

    Stores conversation history per session with automatic expiration.
    Provides methods to add messages, retrieve history, and manage sessions.

    Memory Limits:
    - MAX_MESSAGES: Maximum number of messages per conversation
    - MAX_TOKENS: Approximate token limit for entire conversation
    - MAX_MESSAGE_LENGTH: Maximum characters per individual message
    """

    # Key prefix for Redis
    KEY_PREFIX = "emma:conv"
    # Default TTL: 30 minutes
    DEFAULT_TTL_SECONDS = 1800
    # Maximum messages to store per conversation
    MAX_MESSAGES = 100
    # Maximum approximate tokens for entire conversation (prevents OOM)
    # Using ~4 chars per token estimation (conservative for multi-language)
    MAX_TOKENS = 32000  # ~128KB of text
    MAX_CHARS = MAX_TOKENS * 4  # 128000 chars total
    # Maximum characters per individual message (truncate longer messages)
    MAX_MESSAGE_LENGTH = 8000  # ~2000 tokens per message

    def __init__(
        self,
        redis_url: Optional[str] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS
    ):
        """
        Initialize conversation memory.

        Args:
            redis_url: Redis connection URL. Uses settings if not provided.
            ttl_seconds: TTL for conversation data in seconds.
        """
        self._redis_url = redis_url or settings.redis_url
        self._ttl = ttl_seconds
        self._redis: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Establish Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info(f"✅ ConversationMemory connected to Redis")

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    def _make_key(self, session_id: str) -> str:
        """Generate Redis key for a conversation."""
        return f"{self.KEY_PREFIX}:{session_id}"

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Uses ~4 chars per token as a conservative estimate
        that works across languages (English ~4, Spanish ~4.5, CJK ~1.5).

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return len(text) // 4 + 1

    def _truncate_message(self, content: str) -> str:
        """
        Truncate message if it exceeds MAX_MESSAGE_LENGTH.

        Args:
            content: Message content

        Returns:
            Truncated content with indicator if truncated
        """
        if len(content) <= self.MAX_MESSAGE_LENGTH:
            return content

        truncated = content[:self.MAX_MESSAGE_LENGTH - 50]
        return truncated + "\n\n[... mensaje truncado por longitud ...]"

    def _trim_conversation_by_tokens(self, messages: List) -> List:
        """
        Trim conversation to fit within MAX_TOKENS limit.

        Keeps most recent messages, removing oldest until within limit.

        Args:
            messages: List of Message objects

        Returns:
            Trimmed list of messages
        """
        total_chars = sum(len(msg.content) for msg in messages)

        if total_chars <= self.MAX_CHARS:
            return messages

        # Remove oldest messages until within limit
        trimmed = list(messages)
        while trimmed and sum(len(msg.content) for msg in trimmed) > self.MAX_CHARS:
            removed = trimmed.pop(0)
            logger.debug(f"Removed old message to fit token limit: {removed.content[:50]}...")

        if len(trimmed) < len(messages):
            logger.info(
                f"Trimmed conversation from {len(messages)} to {len(trimmed)} messages "
                f"({total_chars} -> {sum(len(m.content) for m in trimmed)} chars)"
            )

        return trimmed

    async def get_context(
        self,
        session_id: str,
        user_id: Optional[str] = None
    ) -> ConversationContext:
        """
        Get or create conversation context for a session.

        Args:
            session_id: Session identifier
            user_id: Optional user identifier

        Returns:
            ConversationContext (existing or new)
        """
        await self.connect()

        key = self._make_key(session_id)
        data = await self._redis.get(key)

        if data:
            try:
                context = ConversationContext.from_dict(json.loads(data))
                logger.debug(f"Loaded conversation context: {session_id} ({len(context.messages)} messages)")
                return context
            except Exception as e:
                logger.warning(f"Failed to load conversation {session_id}: {e}")

        # Create new context — tenant_id retained as dataclass field for schema compat (empty)
        context = ConversationContext(
            session_id=session_id,
            tenant_id="",
            user_id=user_id
        )
        logger.debug(f"Created new conversation context: {session_id}")
        return context

    async def save_context(self, context: ConversationContext) -> bool:
        """
        Save conversation context to Redis.

        Applies memory limits:
        1. Truncates individual messages exceeding MAX_MESSAGE_LENGTH
        2. Trims conversation to fit MAX_TOKENS
        3. Limits total messages to MAX_MESSAGES

        Args:
            context: ConversationContext to save

        Returns:
            True if saved successfully
        """
        await self.connect()

        try:
            # Step 1: Truncate individual long messages
            for msg in context.messages:
                original_len = len(msg.content)
                msg.content = self._truncate_message(msg.content)
                if len(msg.content) < original_len:
                    logger.debug(f"Truncated message from {original_len} to {len(msg.content)} chars")

            # Step 2: Trim by message count
            if len(context.messages) > self.MAX_MESSAGES:
                context.messages = context.messages[-self.MAX_MESSAGES:]
                logger.debug(f"Trimmed to MAX_MESSAGES={self.MAX_MESSAGES}")

            # Step 3: Trim by total token/char limit
            context.messages = self._trim_conversation_by_tokens(context.messages)

            key = self._make_key(context.session_id)
            data = json.dumps(context.to_dict())

            # Log if data is still large (shouldn't happen after trimming)
            data_kb = len(data) / 1024
            if data_kb > 100:
                logger.warning(f"Large conversation data: {data_kb:.1f}KB for session {context.session_id[:16]}...")

            await self._redis.setex(key, self._ttl, data)
            logger.debug(f"Saved conversation {context.session_id} ({len(context.messages)} messages, {data_kb:.1f}KB)")
            return True

        except Exception as e:
            logger.error(f"Failed to save conversation {context.session_id}: {e}")
            return False

    async def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        user_id: Optional[str] = None,
        **metadata
    ) -> ConversationContext:
        """Add a message to a conversation and save."""
        context = await self.get_context(session_id, user_id)
        context.add_message(role, content, **metadata)
        await self.save_context(context)
        return context

    async def add_exchange(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        user_id: Optional[str] = None,
        **metadata
    ) -> ConversationContext:
        """Add a user-assistant exchange to conversation."""
        context = await self.get_context(session_id, user_id)
        context.add_user_message(user_message)
        context.add_assistant_message(assistant_message, **metadata)
        await self.save_context(context)
        return context

    async def get_history_for_llm(
        self,
        session_id: str,
        max_messages: int = 20
    ) -> List[dict]:
        """Get conversation history formatted for LLM."""
        context = await self.get_context(session_id)
        return context.get_history_for_llm(max_messages)

    async def clear_session(self, session_id: str) -> bool:
        """Clear a conversation session."""
        await self.connect()

        try:
            key = self._make_key(session_id)
            await self._redis.delete(key)
            logger.info(f"Cleared conversation session: {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear session {session_id}: {e}")
            return False

    async def list_sessions(self) -> List[str]:
        """List all active sessions."""
        await self.connect()

        try:
            pattern = f"{self.KEY_PREFIX}:*"
            keys = []
            async for key in self._redis.scan_iter(match=pattern):
                parts = key.split(":")
                if len(parts) >= 3:
                    keys.append(parts[-1])
            return keys
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []

    async def extend_ttl(self, session_id: str) -> bool:
        """Extend TTL for an active conversation."""
        await self.connect()

        try:
            key = self._make_key(session_id)
            result = await self._redis.expire(key, self._ttl)
            return result
        except Exception as e:
            logger.error(f"Failed to extend TTL for {session_id}: {e}")
            return False


# Singleton instance
_conversation_memory: Optional[ConversationMemory] = None


def get_conversation_memory() -> ConversationMemory:
    """Get the global ConversationMemory singleton."""
    global _conversation_memory
    if _conversation_memory is None:
        _conversation_memory = ConversationMemory()
    return _conversation_memory
