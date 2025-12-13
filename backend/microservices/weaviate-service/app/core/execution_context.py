"""
Execution Context for Agent Framework Tools.

This module provides thread-safe context variables that are automatically
available to all @ai_function tools during execution, eliminating the need
for LLMs to extract and pass tenant_id correctly.

ARCHITECTURE:
┌─────────────────────────────────────────────────────────────┐
│                    EmmaCoordinator.execute()                 │
│                                                             │
│  1. set_execution_context(tenant_id="xxx", user_id="yyy")   │
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              ChatAgent.run() → SearchAgent              ││
│  │                          │                               ││
│  │                          ▼                               ││
│  │  ┌───────────────────────────────────────────────────┐  ││
│  │  │         @ai_function semantic_search()            │  ││
│  │  │                                                   │  ││
│  │  │  # LLM might pass tenant_id="123" (wrong!)        │  ││
│  │  │  tenant_id = get_tenant_id()  # Returns "xxx" ✓   │  ││
│  │  │                                                   │  ││
│  │  └───────────────────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  2. clear_execution_context()                               │
└─────────────────────────────────────────────────────────────┘

Usage in @ai_function tools:
    from app.core.execution_context import get_tenant_id, get_user_id

    @ai_function
    async def semantic_search(
        query: str,
        tenant_id: str,  # LLM provides this, but we override it
        ...
    ) -> str:
        # Get the REAL tenant_id from execution context
        actual_tenant_id = get_tenant_id() or tenant_id
        ...

Usage in EmmaCoordinator:
    from app.core.execution_context import set_execution_context, clear_execution_context

    async def execute(self, query, tenant_id, ...):
        set_execution_context(tenant_id=tenant_id, user_id=user_id)
        try:
            result = await self._emma.run(...)
        finally:
            clear_execution_context()
"""

import logging
from contextvars import ContextVar
from typing import Optional, Any, Dict

logger = logging.getLogger(__name__)

# Context variables for execution
_tenant_id_var: ContextVar[Optional[str]] = ContextVar('tenant_id', default=None)
_user_id_var: ContextVar[Optional[str]] = ContextVar('user_id', default=None)
_session_id_var: ContextVar[Optional[str]] = ContextVar('session_id', default=None)
_extra_context_var: ContextVar[Dict[str, Any]] = ContextVar('extra_context', default={})


def set_execution_context(
    tenant_id: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    **extra: Any
) -> None:
    """
    Set execution context for the current async task.

    This context is automatically available to all @ai_function tools
    called during this execution, regardless of how deeply nested.

    Args:
        tenant_id: Tenant identifier (REQUIRED)
        user_id: Optional user identifier
        session_id: Optional session identifier
        **extra: Additional context values
    """
    _tenant_id_var.set(tenant_id)

    if user_id:
        _user_id_var.set(user_id)

    if session_id:
        _session_id_var.set(session_id)

    if extra:
        _extra_context_var.set(extra)

    logger.debug(f"🔐 Execution context set: tenant={tenant_id}, user={user_id}")


def clear_execution_context() -> None:
    """
    Clear all execution context variables.

    Call this in a finally block after execution completes.
    """
    _tenant_id_var.set(None)
    _user_id_var.set(None)
    _session_id_var.set(None)
    _extra_context_var.set({})

    logger.debug("🔓 Execution context cleared")


def get_tenant_id() -> Optional[str]:
    """
    Get the current tenant_id from execution context.

    Returns:
        Tenant ID if set, None otherwise
    """
    return _tenant_id_var.get()


def get_user_id() -> Optional[str]:
    """
    Get the current user_id from execution context.

    Returns:
        User ID if set, None otherwise
    """
    return _user_id_var.get()


def get_session_id() -> Optional[str]:
    """
    Get the current session_id from execution context.

    Returns:
        Session ID if set, None otherwise
    """
    return _session_id_var.get()


def get_extra_context() -> Dict[str, Any]:
    """
    Get additional context values.

    Returns:
        Dictionary with extra context values
    """
    return _extra_context_var.get()


def get_tenant_id_or_raise() -> str:
    """
    Get tenant_id or raise an error if not set.

    Use this in tools that REQUIRE tenant isolation.

    Returns:
        Tenant ID

    Raises:
        RuntimeError: If tenant_id is not set in context
    """
    tenant_id = _tenant_id_var.get()
    if not tenant_id:
        raise RuntimeError(
            "tenant_id not found in execution context. "
            "Ensure set_execution_context() was called before executing tools."
        )
    return tenant_id


def resolve_tenant_id(llm_provided: Optional[str] = None) -> str:
    """
    Resolve tenant_id with priority: context > LLM provided.

    This is the main function @ai_function tools should use.
    It ensures the context-provided tenant_id takes precedence
    over whatever the LLM might have passed.

    Args:
        llm_provided: The tenant_id the LLM passed (may be wrong)

    Returns:
        The correct tenant_id from context, or llm_provided as fallback

    Raises:
        ValueError: If no tenant_id is available from any source

    Example:
        @ai_function
        async def semantic_search(tenant_id: str, ...) -> str:
            actual_tenant_id = resolve_tenant_id(tenant_id)
            # actual_tenant_id is guaranteed to be from trusted context
    """
    context_tenant_id = _tenant_id_var.get()

    if context_tenant_id:
        # Log if LLM tried to use a different tenant_id (DEBUG level - expected behavior)
        # The LLM often invents placeholder values like "tenant-123" which we safely override
        if llm_provided and llm_provided != context_tenant_id:
            logger.debug(
                f"🔒 tenant_id resolved: LLM passed '{llm_provided}', "
                f"using context '{context_tenant_id}'"
            )
        return context_tenant_id

    if llm_provided:
        logger.warning(
            f"⚠️ No execution context set, using LLM-provided tenant_id: {llm_provided}"
        )
        return llm_provided

    raise ValueError(
        "No tenant_id available. Neither execution context nor LLM provided one."
    )
