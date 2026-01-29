"""
Reasoning Tracker - Dynamic Step Registration for Emma Traceability

This module provides a context-aware system for tracking reasoning steps
during tool execution. Any tool or connector can register steps dynamically.

Usage in tools:
    from app.agents.langgraph.reasoning_tracker import ReasoningTracker

    async def my_custom_tool(query: str, ...) -> Dict[str, Any]:
        tracker = ReasoningTracker.get_current()

        tracker.add_step("query_analysis", f"Analizando: {query}")

        # Connect to external DB
        tracker.add_step("connection", "Conectando a PostgreSQL externo...")
        results = await external_db.query(...)

        tracker.add_step("data_extraction", f"Encontrados {len(results)} registros")

        return {
            "response": format_results(results),
            "reasoning_steps": tracker.get_steps()  # Auto-collected
        }

For connectors:
    class AlfrescoConnector:
        async def search(self, query: str) -> list:
            tracker = ReasoningTracker.get_current()
            tracker.add_step("connector", "Conectando a Alfresco CMIS...")
            # ... search logic
            tracker.add_step("connector", f"Alfresco: {len(results)} documentos")
            return results

The tracker uses contextvars for async-safe per-request isolation.
"""

import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class StepType(str, Enum):
    """Standard step types for consistency in UI display."""
    # Core reasoning steps
    QUERY_ANALYSIS = "query_analysis"
    ROUTING = "routing"

    # Interleaved thinking steps (ReACT-style)
    THINKING = "thinking"           # LLM's internal reasoning before action
    TOOL_CALL = "tool_call"         # Decision to call a tool
    TOOL_EXECUTION = "tool_execution"  # Tool is running
    OBSERVATION = "observation"     # Result from tool (what the LLM sees)
    REFLECTION = "reflection"       # LLM's analysis after seeing results

    # Connection/connector steps
    CONNECTION = "connection"
    CONNECTOR = "connector"

    # Search and data steps
    SEARCH = "search"
    DATA_EXTRACTION = "data_extraction"
    TRANSFORMATION = "transformation"
    VALIDATION = "validation"

    # Final steps
    RESPONSE = "response"
    ERROR = "error"
    CUSTOM = "custom"


@dataclass
class ReasoningStep:
    """A single reasoning step for traceability."""
    type: str
    content: str
    confidence: float = 1.0
    entities: List[str] = field(default_factory=list)
    source: Optional[str] = None  # Tool/connector name that generated this step
    timestamp_ms: float = field(default_factory=lambda: time.time() * 1000)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type,
            "content": self.content,
            "confidence": self.confidence,
            "entities": self.entities,
            "source": self.source,
            "timestamp_ms": self.timestamp_ms,
            "metadata": self.metadata,
        }


# Context variable for async-safe per-request tracking
_current_tracker: ContextVar[Optional["ReasoningTracker"]] = ContextVar(
    "reasoning_tracker", default=None
)


class ReasoningTracker:
    """
    Context-aware reasoning step tracker.

    Provides a centralized way for tools and connectors to register
    their reasoning steps without tight coupling.

    Features:
    - Async-safe via contextvars (each request has its own tracker)
    - Auto-numbering of steps
    - Source attribution (which tool/connector generated the step)
    - Timestamp tracking for latency analysis
    - Nested context support (sub-operations)

    Example:
        # In agent execution
        with ReasoningTracker.create() as tracker:
            result = await tool.execute(query)
            steps = tracker.get_steps()

        # Inside the tool (any depth)
        tracker = ReasoningTracker.get_current()
        tracker.add_step("search", "Buscando en índice...")
    """

    def __init__(self):
        self._steps: List[ReasoningStep] = []
        self._step_counter = 0
        self._current_source: Optional[str] = None
        self._start_time = time.time()

    @classmethod
    def create(cls) -> "ReasoningTracker":
        """Create and set a new tracker as current."""
        tracker = cls()
        _current_tracker.set(tracker)
        return tracker

    @classmethod
    def get_current(cls) -> "ReasoningTracker":
        """
        Get the current tracker or create a dummy one.

        Returns a no-op tracker if none is set, allowing tools
        to safely call add_step() even when not in a tracked context.
        """
        tracker = _current_tracker.get()
        if tracker is None:
            # Return a dummy tracker that does nothing
            # This allows tools to work both with and without tracking
            tracker = cls()
            logger.debug("No active tracker, using untracked instance")
        return tracker

    @classmethod
    def clear(cls):
        """Clear the current tracker."""
        _current_tracker.set(None)

    def __enter__(self) -> "ReasoningTracker":
        """Context manager entry."""
        _current_tracker.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        _current_tracker.set(None)
        return False

    def set_source(self, source: str):
        """Set the current source (tool/connector name) for subsequent steps."""
        self._current_source = source

    def add_step(
        self,
        step_type: str,
        content: str,
        confidence: float = 1.0,
        entities: Optional[List[str]] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ReasoningStep:
        """
        Add a reasoning step.

        Args:
            step_type: Type of step (use StepType enum for consistency)
            content: Human-readable description of what's happening
            confidence: Confidence level (0.0 to 1.0)
            entities: Optional list of entities involved
            source: Override the current source
            metadata: Additional metadata

        Returns:
            The created ReasoningStep
        """
        self._step_counter += 1

        step = ReasoningStep(
            type=step_type,
            content=content,
            confidence=confidence,
            entities=entities or [],
            source=source or self._current_source,
            metadata={
                "step_number": self._step_counter,
                **(metadata or {}),
            },
        )

        self._steps.append(step)

        logger.debug(
            f"📝 ReasoningStep #{self._step_counter}: [{step_type}] {content[:50]}..."
        )

        return step

    def add_connector_step(
        self,
        connector_name: str,
        action: str,
        details: Optional[str] = None,
        confidence: float = 1.0,
    ) -> ReasoningStep:
        """
        Convenience method for connector steps.

        Args:
            connector_name: Name of the connector (e.g., "Alfresco", "SharePoint")
            action: What the connector is doing
            details: Optional additional details

        Example:
            tracker.add_connector_step("Alfresco", "searching", "query='contracts'")
        """
        content = f"{connector_name}: {action}"
        if details:
            content += f" ({details})"

        return self.add_step(
            step_type=StepType.CONNECTOR,
            content=content,
            confidence=confidence,
            source=connector_name.lower(),
            metadata={"connector": connector_name, "action": action},
        )

    def add_search_step(
        self,
        source_name: str,
        query: str,
        result_count: Optional[int] = None,
    ) -> ReasoningStep:
        """
        Convenience method for search steps.

        Args:
            source_name: Where we're searching (e.g., "Weaviate", "Elasticsearch")
            query: The search query
            result_count: Optional number of results found
        """
        if result_count is not None:
            content = f"Búsqueda en {source_name}: {result_count} resultados para '{query[:30]}...'"
        else:
            content = f"Buscando en {source_name}: '{query[:50]}...'"

        return self.add_step(
            step_type=StepType.SEARCH,
            content=content,
            source=source_name.lower(),
            metadata={"query": query, "result_count": result_count},
        )

    def add_error_step(
        self,
        error_message: str,
        source: Optional[str] = None,
    ) -> ReasoningStep:
        """Add an error step."""
        return self.add_step(
            step_type=StepType.ERROR,
            content=f"Error: {error_message}",
            confidence=0.0,
            source=source,
        )

    # =========================================================================
    # Interleaved Thinking Methods (ReACT-style)
    # =========================================================================

    def add_thinking_step(
        self,
        thought: str,
        confidence: float = 1.0,
    ) -> ReasoningStep:
        """
        Add a thinking step - LLM's internal reasoning before taking action.

        This captures the "chain of thought" that happens BEFORE tool calls.

        Args:
            thought: The LLM's reasoning/thinking content
            confidence: How confident the reasoning is

        Example:
            tracker.add_thinking_step("Necesito buscar documentos del 2006 para contar expedientes")
        """
        return self.add_step(
            step_type=StepType.THINKING,
            content=thought,
            confidence=confidence,
            metadata={"interleaved": True},
        )

    def add_tool_call_step(
        self,
        tool_name: str,
        reason: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> ReasoningStep:
        """
        Add a tool call decision step.

        Captures WHY the LLM decided to call a specific tool.

        Args:
            tool_name: Name of the tool being called
            reason: Why this tool was chosen
            arguments: Tool arguments (summarized)
        """
        content = f"Llamando a {tool_name}: {reason}"
        return self.add_step(
            step_type=StepType.TOOL_CALL,
            content=content,
            metadata={
                "tool": tool_name,
                "reason": reason,
                "arguments": arguments or {},
            },
        )

    def add_observation_step(
        self,
        tool_name: str,
        observation: str,
        success: bool = True,
    ) -> ReasoningStep:
        """
        Add an observation step - what the LLM sees after tool execution.

        This is the result that the LLM will reason about.

        Args:
            tool_name: Which tool produced this observation
            observation: Summary of what was observed
            success: Whether the tool succeeded
        """
        emoji = "✓" if success else "✗"
        content = f"{emoji} {tool_name}: {observation}"
        return self.add_step(
            step_type=StepType.OBSERVATION,
            content=content,
            confidence=1.0 if success else 0.5,
            metadata={"tool": tool_name, "success": success},
        )

    def add_reflection_step(
        self,
        reflection: str,
        decision: Optional[str] = None,
        confidence: float = 1.0,
    ) -> ReasoningStep:
        """
        Add a reflection step - LLM's analysis AFTER seeing tool results.

        This is the key to interleaved thinking: reasoning about observations.

        Args:
            reflection: What the LLM concludes from the observation
            decision: Next action decision (continue, finish, etc.)
            confidence: Confidence in the reflection
        """
        content = reflection
        if decision:
            content += f" → {decision}"

        return self.add_step(
            step_type=StepType.REFLECTION,
            content=content,
            confidence=confidence,
            metadata={"decision": decision, "interleaved": True},
        )

    def get_steps(self) -> List[Dict[str, Any]]:
        """Get all steps as dictionaries."""
        return [step.to_dict() for step in self._steps]

    def get_step_count(self) -> int:
        """Get the number of steps recorded."""
        return len(self._steps)

    def get_elapsed_ms(self) -> float:
        """Get elapsed time since tracker creation."""
        return (time.time() - self._start_time) * 1000

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the tracking session."""
        return {
            "total_steps": len(self._steps),
            "elapsed_ms": self.get_elapsed_ms(),
            "sources": list(set(s.source for s in self._steps if s.source)),
            "step_types": list(set(s.type for s in self._steps)),
        }


# Convenience function for quick step addition
def track_step(
    step_type: str,
    content: str,
    **kwargs,
) -> Optional[ReasoningStep]:
    """
    Quick helper to add a step to the current tracker.

    Can be called from anywhere - if no tracker is active,
    the step is silently ignored.

    Example:
        from app.agents.langgraph.reasoning_tracker import track_step

        track_step("search", "Buscando documentos...")
    """
    tracker = _current_tracker.get()
    if tracker:
        return tracker.add_step(step_type, content, **kwargs)
    return None
