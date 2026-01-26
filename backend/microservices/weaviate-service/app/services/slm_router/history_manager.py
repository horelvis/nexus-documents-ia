"""
History Manager: Conversation History for SLM Context

This module manages conversation history to enable contextual routing:
1. Store query/response pairs with TOON plans
2. Resolve references to previous context ("them", "those", "more")
3. Continue operations from previous turns
4. Compress history for SLM prompt context

Key features:
- Redis-backed storage with TTL for session cleanup
- Entity retention across turns for reference resolution
- Compact formatting to stay within token limits

Version 1.0 - January 2026
"""

import asyncio
import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from dataclasses import dataclass

from .toon_schema import TOONPlan, TOONRoute, ExtractedEntity, TOONGuardrails

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

MAX_TURNS = TOONGuardrails.HISTORY["max_turns"]
MAX_TOKENS_HISTORY = TOONGuardrails.HISTORY["max_tokens"]
ENTITY_RETENTION = TOONGuardrails.HISTORY["entity_retention"]
HISTORY_TTL = TOONGuardrails.HISTORY["ttl_seconds"]


# =============================================================================
# MODELS
# =============================================================================

class ConversationTurn(BaseModel):
    """
    A single turn in the conversation history.

    Contains the essential information needed for context resolution.
    """
    turn_id: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Query info
    query: str
    query_language: str = "es"  # es, en, etc.

    # TOON plan (compact form)
    toon_route: TOONRoute
    toon_confidence: float = 0.0

    # Extracted entities (for reference resolution)
    entities: List[Dict[str, str]] = Field(default_factory=list)
    # Each: {name, type, graph_label}

    # Result summary (for continuation)
    result_summary: str = ""
    # Examples: "count=5", "found 3 documents", "listed 10 contracts"

    # Graph operation details (for continuation)
    graph_operation: Optional[str] = None
    graph_limit: int = 50

    def to_compact_dict(self) -> Dict[str, Any]:
        """Convert to compact dict for storage."""
        return {
            "t": self.turn_id,
            "q": self.query[:100],  # Truncate for storage
            "r": self.toon_route.value,
            "c": round(self.toon_confidence, 2),
            "e": self.entities[:ENTITY_RETENTION],
            "s": self.result_summary[:50],
            "o": self.graph_operation,
            "l": self.graph_limit
        }

    @classmethod
    def from_compact_dict(cls, data: Dict[str, Any], turn_id: int = 0) -> "ConversationTurn":
        """Create from compact dict."""
        return cls(
            turn_id=data.get("t", turn_id),
            query=data.get("q", ""),
            toon_route=TOONRoute(data.get("r", "VECTOR_ONLY")),
            toon_confidence=data.get("c", 0.0),
            entities=data.get("e", []),
            result_summary=data.get("s", ""),
            graph_operation=data.get("o"),
            graph_limit=data.get("l", 50)
        )


class ConversationHistory(BaseModel):
    """
    Complete conversation history for a session.
    """
    session_id: str
    tenant_id: str
    turns: List[ConversationTurn] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    # Accumulated entities across turns (for reference resolution)
    entity_memory: List[Dict[str, str]] = Field(default_factory=list)

    def add_turn(self, turn: ConversationTurn):
        """Add a new turn and update entity memory."""
        turn.turn_id = len(self.turns) + 1
        self.turns.append(turn)
        self.last_updated = datetime.utcnow()

        # Update entity memory (keep most recent, unique by name)
        seen_names = set()
        new_memory = []

        # Add new entities first (most recent)
        for entity in turn.entities:
            name = entity.get('name', '').lower()
            if name and name not in seen_names:
                new_memory.append(entity)
                seen_names.add(name)

        # Add existing entities
        for entity in self.entity_memory:
            name = entity.get('name', '').lower()
            if name and name not in seen_names and len(new_memory) < ENTITY_RETENTION:
                new_memory.append(entity)
                seen_names.add(name)

        self.entity_memory = new_memory

        # Keep only last N turns
        if len(self.turns) > MAX_TURNS:
            self.turns = self.turns[-MAX_TURNS:]

    def get_last_turn(self) -> Optional[ConversationTurn]:
        """Get the most recent turn."""
        return self.turns[-1] if self.turns else None

    def get_last_entities(self) -> List[Dict[str, str]]:
        """Get entities from the last turn."""
        last = self.get_last_turn()
        return last.entities if last else []

    def get_entity_by_type(self, entity_type: str) -> Optional[Dict[str, str]]:
        """Get most recent entity of a specific type."""
        for entity in self.entity_memory:
            if entity.get('type') == entity_type:
                return entity
        return None


# =============================================================================
# REFERENCE RESOLUTION
# =============================================================================

class ReferencePatterns:
    """
    Patterns for detecting reference words in queries.

    These patterns indicate the user is referring to previous context.
    """

    # Continuation patterns (continue previous operation)
    CONTINUATION_ES = [
        "sí", "si", "ok", "vale", "adelante", "hazlo",
        "muéstramelos", "muestramelos", "enséñamelos",
        "listámelos", "dámelos", "dime"
    ]
    CONTINUATION_EN = [
        "yes", "ok", "sure", "show me", "list them",
        "go ahead", "do it", "tell me"
    ]

    # Reference patterns (use entities from history)
    REFERENCE_ES = [
        "esos", "esas", "ellos", "ellas", "los mismos",
        "las mismas", "aquellos", "aquellas", "estos", "estas"
    ]
    REFERENCE_EN = [
        "them", "those", "these", "the same", "that one",
        "the ones"
    ]

    # More patterns (increase limit)
    MORE_ES = ["más", "mas", "otros", "otras", "adicionales"]
    MORE_EN = ["more", "additional", "other", "others"]

    @classmethod
    def detect_continuation(cls, query: str) -> bool:
        """Check if query indicates continuation of previous operation."""
        query_lower = query.lower().strip()

        # Check for exact matches or starts with
        for pattern in cls.CONTINUATION_ES + cls.CONTINUATION_EN:
            if query_lower == pattern or query_lower.startswith(f"{pattern} "):
                return True

        return False

    @classmethod
    def detect_reference(cls, query: str) -> bool:
        """Check if query references previous entities."""
        query_lower = query.lower()

        for pattern in cls.REFERENCE_ES + cls.REFERENCE_EN:
            if pattern in query_lower:
                return True

        return False

    @classmethod
    def detect_more(cls, query: str) -> bool:
        """Check if query asks for more results."""
        query_lower = query.lower()

        for pattern in cls.MORE_ES + cls.MORE_EN:
            if pattern in query_lower:
                return True

        return False


# =============================================================================
# HISTORY MANAGER
# =============================================================================

class HistoryManager:
    """
    Manages conversation history for SLM context.

    Provides:
    1. Storage and retrieval of conversation turns
    2. Reference resolution for contextual queries
    3. Formatted history for SLM prompts
    """

    def __init__(self):
        self._sessions: Dict[str, ConversationHistory] = {}
        self._redis_client = None
        self._use_redis = False

    async def initialize(self, use_redis: bool = True):
        """Initialize with optional Redis storage."""
        self._use_redis = use_redis

        if use_redis:
            try:
                from ...core.config import settings
                import redis.asyncio as redis

                self._redis_client = redis.from_url(settings.redis_url)
                await self._redis_client.ping()
                logger.info("HistoryManager initialized with Redis storage")
            except Exception as e:
                logger.warning(f"Redis not available, using in-memory storage: {e}")
                self._use_redis = False

    async def get_history(self, session_id: str, tenant_id: str) -> ConversationHistory:
        """
        Get conversation history for a session.

        Creates new history if none exists.
        """
        # Try in-memory cache first
        if session_id in self._sessions:
            return self._sessions[session_id]

        # Try Redis
        if self._use_redis and self._redis_client:
            try:
                data = await self._redis_client.get(f"slm:history:{session_id}")
                if data:
                    history_dict = json.loads(data)
                    history = ConversationHistory(
                        session_id=session_id,
                        tenant_id=tenant_id,
                        turns=[
                            ConversationTurn.from_compact_dict(t, i)
                            for i, t in enumerate(history_dict.get("turns", []), 1)
                        ],
                        entity_memory=history_dict.get("entity_memory", [])
                    )
                    self._sessions[session_id] = history
                    return history
            except Exception as e:
                logger.warning(f"Redis history read error: {e}")

        # Create new history
        history = ConversationHistory(session_id=session_id, tenant_id=tenant_id)
        self._sessions[session_id] = history
        return history

    async def add_turn(
        self,
        session_id: str,
        tenant_id: str,
        query: str,
        plan: TOONPlan,
        result_summary: str = ""
    ) -> ConversationTurn:
        """
        Add a new turn to the conversation history.

        Args:
            session_id: Session identifier
            tenant_id: Tenant identifier
            query: The user's query
            plan: The generated TOON plan
            result_summary: Summary of the result (e.g., "count=5")

        Returns:
            The created ConversationTurn
        """
        history = await self.get_history(session_id, tenant_id)

        # Create turn from plan
        turn = ConversationTurn(
            turn_id=len(history.turns) + 1,
            query=query,
            toon_route=plan.route,
            toon_confidence=plan.confidence,
            entities=[
                {"name": e.name, "type": e.type, "graph_label": e.graph_label or ""}
                for e in plan.entities
            ],
            result_summary=result_summary,
            graph_operation=plan.graph.operation.value if plan.graph.enabled else None,
            graph_limit=plan.graph.limit if plan.graph.enabled else 50
        )

        history.add_turn(turn)

        # Persist to Redis
        await self._persist_history(history)

        logger.debug(
            f"Added turn {turn.turn_id} to session {session_id}: "
            f"route={turn.toon_route.value}, entities={len(turn.entities)}"
        )

        return turn

    async def _persist_history(self, history: ConversationHistory):
        """Persist history to Redis."""
        if not self._use_redis or not self._redis_client:
            return

        try:
            data = {
                "turns": [t.to_compact_dict() for t in history.turns],
                "entity_memory": history.entity_memory
            }
            await self._redis_client.setex(
                f"slm:history:{history.session_id}",
                HISTORY_TTL,
                json.dumps(data)
            )
        except Exception as e:
            logger.warning(f"Redis history write error: {e}")

    async def format_for_prompt(
        self,
        session_id: str,
        tenant_id: str,
        max_tokens: int = MAX_TOKENS_HISTORY
    ) -> str:
        """
        Format conversation history as context for SLM prompt.

        Returns compact string representation within token limit.
        """
        history = await self.get_history(session_id, tenant_id)

        if not history.turns:
            return "No previous conversation"

        parts = []
        estimated_tokens = 0

        # Add most recent turns first (reversed for recency)
        for turn in reversed(history.turns[-MAX_TURNS:]):
            turn_text = (
                f"Turn {turn.turn_id}: \"{turn.query[:80]}\"\n"
                f"  Route: {turn.toon_route.value}"
            )

            if turn.entities:
                entity_names = [e.get('name', '') for e in turn.entities[:3]]
                turn_text += f", Entities: [{', '.join(entity_names)}]"

            if turn.result_summary:
                turn_text += f", Result: {turn.result_summary}"

            # Rough token estimate (4 chars per token)
            turn_tokens = len(turn_text) // 4
            if estimated_tokens + turn_tokens > max_tokens:
                break

            parts.insert(0, turn_text)  # Insert at start to maintain order
            estimated_tokens += turn_tokens

        return "\n".join(parts)

    async def get_last_toon_plan(
        self,
        session_id: str,
        tenant_id: str
    ) -> Optional[str]:
        """
        Get the last TOON plan as a compact string.

        Used for the "previous plan" context in SLM prompt.
        """
        history = await self.get_history(session_id, tenant_id)
        last_turn = history.get_last_turn()

        if not last_turn:
            return None

        return (
            f"Route: {last_turn.toon_route.value}\n"
            f"Operation: {last_turn.graph_operation or 'semantic_search'}\n"
            f"Entities: {json.dumps(last_turn.entities[:5])}\n"
            f"Limit: {last_turn.graph_limit}"
        )

    async def resolve_references(
        self,
        query: str,
        session_id: str,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Resolve references in query using conversation history.

        Returns dict with:
        - is_continuation: True if query continues previous operation
        - is_reference: True if query references previous entities
        - wants_more: True if query asks for more results
        - resolved_entities: Entities resolved from history
        - suggested_operation: Operation to use (from history or inferred)
        - suggested_limit: Limit to use (possibly increased)
        """
        history = await self.get_history(session_id, tenant_id)
        last_turn = history.get_last_turn()

        result = {
            "is_continuation": ReferencePatterns.detect_continuation(query),
            "is_reference": ReferencePatterns.detect_reference(query),
            "wants_more": ReferencePatterns.detect_more(query),
            "resolved_entities": [],
            "suggested_operation": None,
            "suggested_limit": 50
        }

        if not last_turn:
            return result

        # Resolve entities from history
        if result["is_continuation"] or result["is_reference"]:
            result["resolved_entities"] = history.entity_memory[:ENTITY_RETENTION]

        # Suggest operation continuation
        if result["is_continuation"]:
            # If previous was COUNT, continuation should be LIST
            if last_turn.graph_operation == "COUNT":
                result["suggested_operation"] = "LIST"
            else:
                result["suggested_operation"] = last_turn.graph_operation
            result["suggested_limit"] = last_turn.graph_limit

        # Increase limit for "more"
        if result["wants_more"]:
            result["suggested_limit"] = min(last_turn.graph_limit * 2, 100)
            result["suggested_operation"] = "LIST"

        logger.debug(
            f"Reference resolution for '{query[:50]}': "
            f"continuation={result['is_continuation']}, "
            f"reference={result['is_reference']}, "
            f"more={result['wants_more']}, "
            f"entities={len(result['resolved_entities'])}"
        )

        return result

    async def clear_session(self, session_id: str):
        """Clear history for a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]

        if self._use_redis and self._redis_client:
            try:
                await self._redis_client.delete(f"slm:history:{session_id}")
            except Exception:
                pass

    async def close(self):
        """Close resources."""
        if self._redis_client:
            await self._redis_client.close()


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_history_manager: Optional[HistoryManager] = None


def get_history_manager() -> HistoryManager:
    """Get the singleton history manager instance."""
    global _history_manager
    if _history_manager is None:
        _history_manager = HistoryManager()
    return _history_manager


async def initialize_history_manager(use_redis: bool = True) -> HistoryManager:
    """Initialize the singleton history manager."""
    global _history_manager
    _history_manager = HistoryManager()
    await _history_manager.initialize(use_redis)
    return _history_manager
