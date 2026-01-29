"""
Langfuse Observability Configuration for Emma v2

Provides LLM tracing, session tracking, and analytics for the Emma v2 agent.

Features:
- Trace: Full request lifecycle tracking with nested spans
- Session: Multi-turn conversation grouping
- Generation: LLM call details (model, tokens, latency)
- Score: Custom metrics (tokens_saved, sil_fast_path, iterations)

Architecture:
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  POST /emma/v2/query                                                     │
    │  └── Root Trace (trace_id, session_id=thread_id)                        │
    │      ├── metadata: tenant_id, user_id, domain                            │
    │      │                                                                   │
    │      ├── [SIL Fast Path] (span: "sil.process_query")                    │
    │      │   └── Cypher execution, tokens_saved                             │
    │      │                                                                   │
    │      ├── [Agentic Loop] (span: "emma.agentic_loop")                     │
    │      │   ├── Generation: llm.chat (model, tokens, latency)              │
    │      │   └── Tool Executions                                            │
    │      │       ├── span: "tool.search"                                    │
    │      │       ├── span: "tool.read_document"                             │
    │      │       └── span: "tool.analyze"                                   │
    │      │                                                                   │
    │      └── Scores                                                         │
    │          ├── tokens_saved: int                                          │
    │          ├── sil_answered: bool                                         │
    │          └── iterations: int                                            │
    └─────────────────────────────────────────────────────────────────────────┘

Usage:
    from app.core.langfuse_config import (
        get_langfuse,
        observe,
        langfuse_context,
        create_trace,
    )

    @observe(name="emma.execute")
    async def execute(self, query: str, context: ExecutionContext):
        langfuse_context.update_current_observation(
            session_id=context.thread_id,
            user_id=context.user_id,
            metadata={"tenant_id": context.tenant_id}
        )
        # ... implementation

References:
- https://langfuse.com/docs/sdk/python/decorators
- https://langfuse.com/docs/tracing
"""

import logging
import random
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

from app.core.config import settings

logger = logging.getLogger(__name__)

# Type for decorated functions
F = TypeVar("F", bound=Callable[..., Any])

# Global Langfuse client (lazy initialization)
_langfuse_client = None
_langfuse_initialized = False


def get_langfuse():
    """
    Get or create the global Langfuse client.

    Returns None if Langfuse is disabled or not configured.
    """
    global _langfuse_client, _langfuse_initialized

    if _langfuse_initialized:
        return _langfuse_client

    _langfuse_initialized = True

    if not settings.langfuse_enabled:
        logger.info("Langfuse observability disabled (LANGFUSE_ENABLED=false)")
        return None

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning(
            "Langfuse keys not configured. Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY. "
            "Observability will be disabled."
        )
        return None

    try:
        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            flush_at=settings.langfuse_flush_at,
            flush_interval=settings.langfuse_flush_interval,
            debug=settings.langfuse_debug,
        )

        logger.info(f"✅ Langfuse initialized (host={settings.langfuse_host})")
        return _langfuse_client

    except ImportError:
        logger.warning("Langfuse SDK not installed. Run: pip install langfuse")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Langfuse: {e}")
        return None


def is_langfuse_enabled() -> bool:
    """Check if Langfuse is enabled and properly configured."""
    return get_langfuse() is not None


def should_sample() -> bool:
    """Determine if this request should be sampled for tracing."""
    if not is_langfuse_enabled():
        return False
    return random.random() < settings.langfuse_sample_rate


class LangfuseContext:
    """
    Thread-local context for Langfuse observations.

    Provides a way to update the current observation from nested functions
    without passing the observation object explicitly.
    """

    def __init__(self):
        self._observation_stack: List[Any] = []

    def push_observation(self, observation: Any) -> None:
        """Push an observation onto the stack."""
        self._observation_stack.append(observation)

    def pop_observation(self) -> Optional[Any]:
        """Pop an observation from the stack."""
        if self._observation_stack:
            return self._observation_stack.pop()
        return None

    def get_current_observation(self) -> Optional[Any]:
        """Get the current observation without removing it."""
        if self._observation_stack:
            return self._observation_stack[-1]
        return None

    def update_current_observation(
        self,
        *,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        input: Optional[Any] = None,
        output: Optional[Any] = None,
        level: Optional[str] = None,
        status_message: Optional[str] = None,
        version: Optional[str] = None,
        **kwargs,
    ) -> None:
        """
        Update the current observation with additional data.

        This is the primary way to add context during execution.
        """
        obs = self.get_current_observation()
        if obs is None:
            return

        try:
            update_kwargs = {}
            if name is not None:
                update_kwargs["name"] = name
            if metadata is not None:
                # Merge with existing metadata
                existing = getattr(obs, "metadata", {}) or {}
                update_kwargs["metadata"] = {**existing, **metadata}
            if session_id is not None:
                update_kwargs["session_id"] = session_id
            if user_id is not None:
                update_kwargs["user_id"] = user_id
            if input is not None:
                update_kwargs["input"] = input
            if output is not None:
                update_kwargs["output"] = output
            if level is not None:
                update_kwargs["level"] = level
            if status_message is not None:
                update_kwargs["status_message"] = status_message
            if version is not None:
                update_kwargs["version"] = version

            # Add any additional kwargs
            update_kwargs.update(kwargs)

            if hasattr(obs, "update"):
                obs.update(**update_kwargs)

        except Exception as e:
            logger.debug(f"Failed to update observation: {e}")

    def score(
        self,
        name: str,
        value: Union[float, int, bool],
        comment: Optional[str] = None,
        data_type: Optional[str] = None,
    ) -> None:
        """
        Add a score to the current trace.

        Use this for custom metrics like tokens_saved, sil_fast_path, etc.

        Args:
            name: Score name (e.g., "tokens_saved", "sil_answered")
            value: Score value (numeric or boolean)
            comment: Optional comment explaining the score
            data_type: "NUMERIC" or "BOOLEAN" (auto-detected if not specified)
        """
        obs = self.get_current_observation()
        if obs is None:
            return

        try:
            # Get the trace from the observation
            trace = getattr(obs, "trace", None) or obs

            if hasattr(trace, "score"):
                # Auto-detect data type
                if data_type is None:
                    data_type = "BOOLEAN" if isinstance(value, bool) else "NUMERIC"

                # Convert bool to int for scoring
                if isinstance(value, bool):
                    value = 1 if value else 0

                trace.score(
                    name=name,
                    value=value,
                    comment=comment,
                    data_type=data_type,
                )

        except Exception as e:
            logger.debug(f"Failed to add score '{name}': {e}")


# Global context instance
langfuse_context = LangfuseContext()


def create_trace(
    name: str,
    *,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    input: Optional[Any] = None,
    tags: Optional[List[str]] = None,
    version: Optional[str] = None,
    release: Optional[str] = None,
    public: bool = False,
):
    """
    Create a new Langfuse trace.

    Use this at the top level of a request (e.g., in API endpoints).

    Args:
        name: Trace name (e.g., "emma.query")
        session_id: Session/conversation ID for grouping multi-turn interactions
        user_id: User identifier
        metadata: Additional metadata (e.g., tenant_id, domain)
        input: Input data (e.g., query string)
        tags: Tags for filtering (e.g., ["production", "labor-domain"])
        version: Application version
        release: Release identifier
        public: Whether the trace should be publicly accessible

    Returns:
        Trace object or None if Langfuse is disabled
    """
    client = get_langfuse()
    if client is None:
        return None

    if not should_sample():
        return None

    try:
        trace = client.trace(
            name=name,
            session_id=session_id,
            user_id=user_id,
            metadata=metadata,
            input=input,
            tags=tags,
            version=version,
            release=release,
            public=public,
        )
        return trace
    except Exception as e:
        logger.debug(f"Failed to create trace: {e}")
        return None


@contextmanager
def trace_context(
    name: str,
    *,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    input: Optional[Any] = None,
    tags: Optional[List[str]] = None,
):
    """
    Context manager for creating a trace with automatic cleanup.

    Usage:
        with trace_context("emma.query", session_id=thread_id) as trace:
            # ... do work
            if trace:
                trace.update(output=result)
    """
    trace = create_trace(
        name=name,
        session_id=session_id,
        user_id=user_id,
        metadata=metadata,
        input=input,
        tags=tags,
    )

    if trace:
        langfuse_context.push_observation(trace)

    try:
        yield trace
    finally:
        if trace:
            langfuse_context.pop_observation()
            try:
                # Ensure events are flushed
                client = get_langfuse()
                if client:
                    client.flush()
            except Exception:
                pass


def observe(
    name: Optional[str] = None,
    *,
    as_type: Optional[str] = None,  # "span" or "generation"
    capture_input: bool = True,
    capture_output: bool = True,
    transform_input: Optional[Callable] = None,
    transform_output: Optional[Callable] = None,
) -> Callable[[F], F]:
    """
    Decorator to observe a function with Langfuse.

    Creates a span or generation observation for the decorated function.

    Args:
        name: Observation name (defaults to function name)
        as_type: "span" for general operations, "generation" for LLM calls
        capture_input: Whether to capture function arguments as input
        capture_output: Whether to capture return value as output
        transform_input: Optional function to transform input before logging
        transform_output: Optional function to transform output before logging

    Usage:
        @observe(name="emma.execute")
        async def execute(self, query: str, context: ExecutionContext):
            # ...

        @observe(as_type="generation", name="llm.chat")
        async def chat(self, messages, tools=None):
            # ...
    """
    def decorator(func: F) -> F:
        obs_name = name or func.__name__

        # Check if it's an async function
        import asyncio
        is_async = asyncio.iscoroutinefunction(func)

        if is_async:
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                if not is_langfuse_enabled():
                    return await func(*args, **kwargs)

                parent = langfuse_context.get_current_observation()
                if parent is None:
                    # No parent trace, run without observation
                    return await func(*args, **kwargs)

                try:
                    # Create observation
                    if as_type == "generation":
                        obs = parent.generation(name=obs_name)
                    else:
                        obs = parent.span(name=obs_name)

                    langfuse_context.push_observation(obs)

                    # Capture input
                    if capture_input:
                        input_data = _format_input(args, kwargs, transform_input)
                        if input_data:
                            obs.update(input=input_data)

                    # Execute function
                    result = await func(*args, **kwargs)

                    # Capture output
                    if capture_output:
                        output_data = transform_output(result) if transform_output else result
                        try:
                            obs.update(output=output_data)
                        except Exception:
                            # Output might not be serializable
                            pass

                    obs.end()
                    return result

                except Exception as e:
                    if obs:
                        obs.update(
                            level="ERROR",
                            status_message=str(e),
                        )
                        obs.end()
                    raise
                finally:
                    langfuse_context.pop_observation()

            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                if not is_langfuse_enabled():
                    return func(*args, **kwargs)

                parent = langfuse_context.get_current_observation()
                if parent is None:
                    return func(*args, **kwargs)

                obs = None
                try:
                    if as_type == "generation":
                        obs = parent.generation(name=obs_name)
                    else:
                        obs = parent.span(name=obs_name)

                    langfuse_context.push_observation(obs)

                    if capture_input:
                        input_data = _format_input(args, kwargs, transform_input)
                        if input_data:
                            obs.update(input=input_data)

                    result = func(*args, **kwargs)

                    if capture_output:
                        output_data = transform_output(result) if transform_output else result
                        try:
                            obs.update(output=output_data)
                        except Exception:
                            pass

                    obs.end()
                    return result

                except Exception as e:
                    if obs:
                        obs.update(level="ERROR", status_message=str(e))
                        obs.end()
                    raise
                finally:
                    langfuse_context.pop_observation()

            return sync_wrapper

    return decorator


def _format_input(
    args: tuple,
    kwargs: dict,
    transform: Optional[Callable] = None,
) -> Optional[Dict[str, Any]]:
    """Format function arguments for logging."""
    try:
        if transform:
            return transform(args, kwargs)

        # Default: just include kwargs (skip self)
        result = {}
        if kwargs:
            result.update(kwargs)

        # Include positional args (skip self for methods)
        if args:
            # Skip first arg if it looks like 'self'
            start_idx = 1 if args and hasattr(args[0], "__class__") else 0
            for i, arg in enumerate(args[start_idx:], start=start_idx):
                if isinstance(arg, (str, int, float, bool, list, dict)):
                    result[f"arg_{i}"] = arg

        return result if result else None

    except Exception:
        return None


def flush_langfuse() -> None:
    """
    Force flush all pending Langfuse events.

    Call this before application shutdown or after critical operations.
    """
    client = get_langfuse()
    if client:
        try:
            client.flush()
        except Exception as e:
            logger.debug(f"Failed to flush Langfuse: {e}")


def shutdown_langfuse() -> None:
    """
    Shutdown Langfuse client gracefully.

    Call this during application shutdown.
    """
    global _langfuse_client, _langfuse_initialized

    if _langfuse_client:
        try:
            _langfuse_client.flush()
            _langfuse_client.shutdown()
        except Exception as e:
            logger.debug(f"Error during Langfuse shutdown: {e}")
        finally:
            _langfuse_client = None
            _langfuse_initialized = False


# =============================================================================
# Convenience Functions for Emma v2
# =============================================================================

def trace_emma_query(
    query: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    domain: Optional[str] = None,
):
    """
    Create a trace for an Emma v2 query.

    Convenience function that sets up the standard metadata.
    """
    return create_trace(
        name="emma.query",
        session_id=thread_id,
        user_id=user_id,
        metadata={
            "tenant_id": tenant_id,
            "domain": domain,
            "version": "2.0",
        },
        input={"query": query},
        tags=["emma-v2", f"domain:{domain or 'general'}"],
    )


def score_emma_result(
    tokens_saved: int = 0,
    sil_answered: bool = False,
    iterations: int = 0,
    tools_called: Optional[List[str]] = None,
    latency_ms: float = 0.0,
) -> None:
    """
    Score an Emma v2 result with standard metrics.

    Call this at the end of query execution.
    """
    langfuse_context.score("tokens_saved", tokens_saved, "Tokens saved via SIL fast path")
    langfuse_context.score("sil_answered", sil_answered, "Query answered by SIL without RAG")
    langfuse_context.score("iterations", iterations, "Number of agentic loop iterations")
    langfuse_context.score("latency_ms", latency_ms, "Total execution time in milliseconds")

    if tools_called:
        langfuse_context.score("tools_count", len(tools_called), "Number of tools called")
