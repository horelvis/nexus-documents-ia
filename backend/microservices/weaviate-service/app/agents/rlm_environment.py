"""
RLM Environment - External Context Storage

Provides a REPL-like environment for RLM processing using in-memory
storage for efficient external context storage and retrieval.

Key features:
- Store large contexts in RAM (not in LLM context window)
- Enable random access to document sections
- Cache intermediate results for reuse
- Support parallel sub-task processing
- Redis fallback for distributed scenarios

Reference: RLM paper arXiv:2512.24601 - Section 3.2 "External Environment"

Design Decision (per paper):
- RAM is the primary storage for lowest latency (~0.001ms vs ~1-2ms for Redis)
- Context is ephemeral (lives only during query processing)
- No persistence needed (if process dies, query fails anyway)
- Redis fallback only for distributed worker scenarios
"""

import logging
import json
import hashlib
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class StoredContext:
    """A context stored in the RLM environment"""

    context_id: str
    tenant_id: str
    document_id: Optional[str]
    content: str
    total_tokens: int
    created_at: datetime
    expires_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextSection:
    """A section of stored context"""

    section_id: str
    context_id: str
    start_offset: int
    end_offset: int
    content: str
    tokens: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryEntry:
    """An entry in the in-memory store with TTL support"""

    value: Any  # Direct Python object, no serialization needed
    expires_at: datetime


class RLMEnvironment:
    """
    RLM External Environment for context storage.

    Uses in-memory storage (RAM) as primary for optimal performance,
    with optional Redis fallback for distributed scenarios.

    Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    RLM ENVIRONMENT                          │
    ├─────────────────────────────────────────────────────────────┤
    │  ┌─────────────┐    ┌──────────────────────────────────────┐│
    │  │  LLM Call   │    │      In-Memory Store (PRIMARY)       ││
    │  │  (8K ctx)   │────│  context:{id} → StoredContext obj    ││
    │  │             │    │  section:{id} → ContextSection obj   ││
    │  │  "Get sec 3"│────│  result:{id}:{task} → result string  ││
    │  └─────────────┘    └──────────────────────────────────────┘│
    │           │                        │                        │
    │           │         (if RLM_USE_REDIS=true)                 │
    │           │                        ▼                        │
    │           │         ┌──────────────────────────────────────┐│
    │           │         │      Redis Store (FALLBACK)          ││
    │           │         │  For distributed worker scenarios    ││
    │           │         └──────────────────────────────────────┘│
    │           ▼                                                 │
    │  LLM processes section 3 with full attention                │
    └─────────────────────────────────────────────────────────────┘

    Performance comparison:
    - RAM: ~0.001ms per operation (direct dict access)
    - Redis: ~1-2ms per operation (network + serialization)
    """

    def __init__(self):
        # Primary: In-memory storage
        self._memory_store: Dict[str, MemoryEntry] = {}
        self._memory_lock = Lock()

        # Fallback: Redis (only if explicitly enabled)
        self._redis = None
        self._use_redis_fallback = False

        self._initialized = False

        # Default TTL: 1 hour for contexts
        self._default_ttl = 3600

        # Key prefixes
        self._context_prefix = "rlm:context:"
        self._section_prefix = "rlm:section:"
        self._result_prefix = "rlm:result:"
        self._index_prefix = "rlm:index:"

        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval = 60  # seconds

    async def initialize(self):
        """Initialize the RLM environment"""
        if self._initialized:
            return

        # Check if Redis fallback is explicitly requested via settings
        from ..core.config import settings
        use_redis = settings.rlm_use_redis

        if use_redis:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    decode_responses=True,
                )

                # Test connection
                await self._redis.ping()

                self._use_redis_fallback = True
                logger.warning(
                    "⚠️ RLMEnvironment using Redis FALLBACK mode "
                    "(RLM_USE_REDIS=true). This adds ~1-2ms latency per operation. "
                    "Only use for distributed worker scenarios."
                )

            except Exception as e:
                logger.error(
                    f"❌ RLMEnvironment Redis fallback failed: {e}. "
                    "Continuing with RAM-only mode."
                )
                self._redis = None
                self._use_redis_fallback = False

        # Start cleanup task for expired entries
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_entries())

        self._initialized = True

        if not self._use_redis_fallback:
            logger.info(
                "✅ RLMEnvironment initialized with RAM storage (optimal performance)"
            )

    async def _cleanup_expired_entries(self):
        """Periodically clean up expired entries from memory"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)

                now = datetime.now()
                expired_keys = []

                with self._memory_lock:
                    for key, entry in self._memory_store.items():
                        if entry.expires_at <= now:
                            expired_keys.append(key)

                    for key in expired_keys:
                        del self._memory_store[key]

                if expired_keys:
                    logger.debug(f"🧹 Cleaned up {len(expired_keys)} expired RLM entries")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"⚠️ RLM cleanup error: {e}")

    async def store_context(
        self,
        content: str,
        tenant_id: str,
        document_id: Optional[str] = None,
        ttl: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Store a large context in the environment.

        Args:
            content: Full document/context content
            tenant_id: Tenant identifier
            document_id: Optional document ID
            ttl: Time-to-live in seconds
            metadata: Additional metadata

        Returns:
            Context ID for retrieval
        """
        await self.initialize()

        # Generate context ID
        context_id = self._generate_context_id(content, tenant_id)

        # Calculate tokens (rough estimate: 1 token ≈ 4 chars)
        total_tokens = len(content) // 4

        # Create stored context
        stored = StoredContext(
            context_id=context_id,
            tenant_id=tenant_id,
            document_id=document_id,
            content=content,
            total_tokens=total_tokens,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=ttl or self._default_ttl),
            metadata=metadata or {},
        )

        # Store in memory (primary) or Redis (fallback)
        await self._store(
            key=f"{self._context_prefix}{context_id}",
            value=stored,
            ttl=ttl or self._default_ttl,
        )

        # Create section index for random access
        await self._index_sections(stored)

        logger.info(
            f"📦 Stored context {context_id}: {total_tokens} tokens, "
            f"TTL: {ttl or self._default_ttl}s, "
            f"storage: {'Redis' if self._use_redis_fallback else 'RAM'}"
        )

        return context_id

    async def get_context(self, context_id: str) -> Optional[StoredContext]:
        """Retrieve a stored context"""
        await self.initialize()

        value = await self._get(f"{self._context_prefix}{context_id}")

        if value is None:
            return None

        # If using Redis, we need to deserialize
        if self._use_redis_fallback and isinstance(value, str):
            return self._deserialize_context(value)

        # RAM storage returns the object directly
        return value

    async def get_section(
        self,
        context_id: str,
        start_offset: int,
        end_offset: int,
    ) -> Optional[ContextSection]:
        """
        Get a specific section of a stored context.

        Enables random access to document sections without
        loading the entire context into memory.

        Args:
            context_id: Context identifier
            start_offset: Character offset start
            end_offset: Character offset end

        Returns:
            ContextSection with the requested content
        """
        await self.initialize()

        # Try to get from section cache first
        section_key = f"{self._section_prefix}{context_id}:{start_offset}:{end_offset}"
        cached = await self._get(section_key)

        if cached is not None:
            if self._use_redis_fallback and isinstance(cached, str):
                return self._deserialize_section(cached)
            return cached

        # Load from full context
        context = await self.get_context(context_id)
        if not context:
            return None

        # Extract section
        content = context.content[start_offset:end_offset]
        section = ContextSection(
            section_id=f"{context_id}_{start_offset}_{end_offset}",
            context_id=context_id,
            start_offset=start_offset,
            end_offset=end_offset,
            content=content,
            tokens=len(content) // 4,
        )

        # Cache the section
        await self._store(
            key=section_key,
            value=section,
            ttl=self._default_ttl // 2,  # Sections expire faster
        )

        return section

    async def cache_result(
        self,
        context_id: str,
        task_id: str,
        result: str,
        ttl: Optional[int] = None,
    ) -> None:
        """
        Cache an intermediate result for reuse.

        Enables efficient reprocessing and parallel sub-task execution.

        Args:
            context_id: Context identifier
            task_id: Task identifier
            result: Task result to cache
            ttl: Time-to-live in seconds
        """
        await self.initialize()

        key = f"{self._result_prefix}{context_id}:{task_id}"

        # Store result with metadata
        cache_entry = {
            "result": result,
            "cached_at": datetime.now().isoformat(),
        }

        await self._store(
            key=key,
            value=cache_entry,
            ttl=ttl or self._default_ttl,
        )

    async def get_cached_result(
        self,
        context_id: str,
        task_id: str,
    ) -> Optional[str]:
        """Retrieve a cached result"""
        await self.initialize()

        key = f"{self._result_prefix}{context_id}:{task_id}"
        value = await self._get(key)

        if value is None:
            return None

        # If using Redis, it's a JSON string
        if self._use_redis_fallback and isinstance(value, str):
            parsed = json.loads(value)
            return parsed.get("result")

        # RAM storage returns dict directly
        return value.get("result")

    async def get_section_index(
        self,
        context_id: str,
    ) -> List[Tuple[int, int, str]]:
        """
        Get the section index for a context.

        Returns a list of (start, end, section_type) tuples
        for efficient navigation.
        """
        await self.initialize()

        key = f"{self._index_prefix}{context_id}"
        value = await self._get(key)

        if value is None:
            return []

        # If using Redis, it's a JSON string
        if self._use_redis_fallback and isinstance(value, str):
            return json.loads(value)

        # RAM storage returns list directly
        return value

    async def delete_context(self, context_id: str) -> bool:
        """Delete a stored context and all associated data"""
        await self.initialize()

        try:
            # Delete main context
            await self._delete(f"{self._context_prefix}{context_id}")

            # Delete index
            await self._delete(f"{self._index_prefix}{context_id}")

            # Delete cached results and sections
            if self._use_redis_fallback and self._redis:
                # Redis: pattern delete
                keys = await self._redis.keys(f"{self._result_prefix}{context_id}:*")
                if keys:
                    await self._redis.delete(*keys)

                section_keys = await self._redis.keys(f"{self._section_prefix}{context_id}:*")
                if section_keys:
                    await self._redis.delete(*section_keys)
            else:
                # RAM: iterate and delete matching keys
                with self._memory_lock:
                    keys_to_delete = [
                        k for k in self._memory_store.keys()
                        if k.startswith(f"{self._result_prefix}{context_id}:") or
                           k.startswith(f"{self._section_prefix}{context_id}:")
                    ]
                    for k in keys_to_delete:
                        del self._memory_store[k]

            logger.info(f"🗑️ Deleted context {context_id}")
            return True

        except Exception as e:
            logger.warning(f"⚠️ Failed to delete context {context_id}: {e}")
            return False

    async def get_stats(self) -> Dict[str, Any]:
        """Get environment statistics"""
        await self.initialize()

        with self._memory_lock:
            memory_entries = len(self._memory_store)

            # Calculate memory usage estimate
            total_content_size = 0
            context_count = 0
            for key, entry in self._memory_store.items():
                if key.startswith(self._context_prefix):
                    context_count += 1
                    if isinstance(entry.value, StoredContext):
                        total_content_size += len(entry.value.content)

        return {
            "storage_mode": "redis_fallback" if self._use_redis_fallback else "ram",
            "memory_entries": memory_entries,
            "context_count": context_count,
            "estimated_memory_mb": total_content_size / (1024 * 1024),
            "cleanup_interval_seconds": self._cleanup_interval,
            "default_ttl_seconds": self._default_ttl,
        }

    async def _index_sections(self, context: StoredContext) -> None:
        """Create a section index for efficient navigation"""
        import re

        # Find section boundaries
        patterns = [
            (r"\n#{1,3}\s+(.+)", "header"),
            (r"\n(?:CAPÍTULO|ARTÍCULO|SECCIÓN|CLÁUSULA)\s+(.+)", "legal"),
            (r"\n\d+\.\d*\s+([A-ZÁÉÍÓÚ].+)", "numbered"),
        ]

        sections = []
        content = context.content

        for pattern, section_type in patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                sections.append((match.start(), match.end(), section_type))

        # Sort by position
        sections.sort(key=lambda x: x[0])

        # Store index
        key = f"{self._index_prefix}{context.context_id}"
        await self._store(
            key=key,
            value=sections,
            ttl=self._default_ttl,
        )

    def _generate_context_id(self, content: str, tenant_id: str) -> str:
        """Generate a unique context ID"""
        hash_input = f"{tenant_id}:{content[:1000]}:{datetime.now().isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    async def _store(self, key: str, value: Any, ttl: int) -> None:
        """Store a value in RAM (primary) or Redis (fallback)"""
        if self._use_redis_fallback and self._redis:
            # Redis: needs serialization
            if isinstance(value, StoredContext):
                serialized = self._serialize_context(value)
            elif isinstance(value, ContextSection):
                serialized = self._serialize_section(value)
            elif isinstance(value, (dict, list)):
                serialized = json.dumps(value)
            else:
                serialized = str(value)

            await self._redis.setex(key, ttl, serialized)
        else:
            # RAM: store object directly (no serialization)
            with self._memory_lock:
                self._memory_store[key] = MemoryEntry(
                    value=value,
                    expires_at=datetime.now() + timedelta(seconds=ttl),
                )

    async def _get(self, key: str) -> Optional[Any]:
        """Get a value from RAM (primary) or Redis (fallback)"""
        if self._use_redis_fallback and self._redis:
            return await self._redis.get(key)
        else:
            with self._memory_lock:
                entry = self._memory_store.get(key)
                if entry and entry.expires_at > datetime.now():
                    return entry.value
                elif entry:
                    # Expired, clean up
                    del self._memory_store[key]
                return None

    async def _delete(self, key: str) -> None:
        """Delete a key from RAM or Redis"""
        if self._use_redis_fallback and self._redis:
            await self._redis.delete(key)
        else:
            with self._memory_lock:
                self._memory_store.pop(key, None)

    def _serialize_context(self, context: StoredContext) -> str:
        """Serialize a StoredContext to JSON (only for Redis fallback)"""
        return json.dumps({
            "context_id": context.context_id,
            "tenant_id": context.tenant_id,
            "document_id": context.document_id,
            "content": context.content,
            "total_tokens": context.total_tokens,
            "created_at": context.created_at.isoformat(),
            "expires_at": context.expires_at.isoformat(),
            "metadata": context.metadata,
        })

    def _deserialize_context(self, data: str) -> StoredContext:
        """Deserialize a StoredContext from JSON (only for Redis fallback)"""
        parsed = json.loads(data)
        return StoredContext(
            context_id=parsed["context_id"],
            tenant_id=parsed["tenant_id"],
            document_id=parsed.get("document_id"),
            content=parsed["content"],
            total_tokens=parsed["total_tokens"],
            created_at=datetime.fromisoformat(parsed["created_at"]),
            expires_at=datetime.fromisoformat(parsed["expires_at"]),
            metadata=parsed.get("metadata", {}),
        )

    def _serialize_section(self, section: ContextSection) -> str:
        """Serialize a ContextSection to JSON (only for Redis fallback)"""
        return json.dumps({
            "section_id": section.section_id,
            "context_id": section.context_id,
            "start_offset": section.start_offset,
            "end_offset": section.end_offset,
            "content": section.content,
            "tokens": section.tokens,
            "metadata": section.metadata,
        })

    def _deserialize_section(self, data: str) -> ContextSection:
        """Deserialize a ContextSection from JSON (only for Redis fallback)"""
        parsed = json.loads(data)
        return ContextSection(
            section_id=parsed["section_id"],
            context_id=parsed["context_id"],
            start_offset=parsed["start_offset"],
            end_offset=parsed["end_offset"],
            content=parsed["content"],
            tokens=parsed["tokens"],
            metadata=parsed.get("metadata", {}),
        )

    async def shutdown(self):
        """Cleanup on shutdown"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        if self._redis:
            await self._redis.close()

        logger.info("🛑 RLMEnvironment shutdown complete")


# Global instance
rlm_environment = RLMEnvironment()
