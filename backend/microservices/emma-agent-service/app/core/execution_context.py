"""
Execution Context for Emma Agent Service Tools.

This module provides thread-safe context variables that are automatically
available to all tools during execution, eliminating the need for LLMs
to extract and pass tenant_id correctly.

ARCHITECTURE:
┌─────────────────────────────────────────────────────────────┐
│              API Entry Point (query/stream)                  │
│                                                             │
│  1. set_execution_context(tenant_id="xxx", user_id="yyy")   │
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐│
│  │         LangGraph / Emma executes                       ││
│  │                          │                               ││
│  │                          ▼                               ││
│  │  ┌───────────────────────────────────────────────────┐  ││
│  │  │         Tool function (e.g., document_search)     │  ││
│  │  │                                                   │  ││
│  │  │  tenant_id = get_tenant_id_or_raise()  # "xxx" ✓  │  ││
│  │  │  user_id = get_user_id()               # "yyy" ✓  │  ││
│  │  │                                                   │  ││
│  │  └───────────────────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  2. clear_execution_context()                               │
└─────────────────────────────────────────────────────────────┘

Usage in tools:
    from app.core.execution_context import get_tenant_id_or_raise, get_user_id

    async def document_search(query: str, ...) -> str:
        tenant_id = get_tenant_id_or_raise()
        user_id = get_user_id()
        ...

Usage in entry points:
    from app.core.execution_context import set_execution_context, clear_execution_context

    set_execution_context(tenant_id=tenant_id, user_id=user_id)
    try:
        result = await execute(...)
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
_user_role_ids_var: ContextVar[Optional[list]] = ContextVar('user_role_ids', default=None)
_is_admin_var: ContextVar[bool] = ContextVar('is_admin', default=False)
_session_id_var: ContextVar[Optional[str]] = ContextVar('session_id', default=None)
_document_id_var: ContextVar[Optional[str]] = ContextVar('document_id', default=None)
_extra_context_var: ContextVar[Dict[str, Any]] = ContextVar('extra_context', default={})


def set_execution_context(
    tenant_id: str,
    user_id: Optional[str] = None,
    user_role_ids: Optional[list] = None,
    is_admin: bool = False,
    session_id: Optional[str] = None,
    document_id: Optional[str] = None,
    **extra: Any
) -> None:
    """
    Set execution context for the current async task.

    This context is automatically available to all tools
    called during this execution, regardless of how deeply nested.

    Args:
        tenant_id: Tenant identifier (REQUIRED)
        user_id: Optional user identifier
        user_role_ids: Optional list of role IDs the user belongs to (for ACL filtering)
        is_admin: Whether the user is an admin (bypasses ACL checks)
        session_id: Optional session identifier
        document_id: Optional focus document ID (for document-specific queries)
        **extra: Additional context values
    """
    _tenant_id_var.set(tenant_id)

    if user_id:
        _user_id_var.set(user_id)

    if user_role_ids:
        _user_role_ids_var.set(user_role_ids)

    _is_admin_var.set(is_admin)

    if session_id:
        _session_id_var.set(session_id)

    if document_id:
        _document_id_var.set(document_id)

    if extra:
        _extra_context_var.set(extra)

    logger.debug(f"🔐 Execution context set: tenant={tenant_id}, user={user_id}, doc={document_id}, roles={len(user_role_ids or [])}, admin={is_admin}")


def clear_execution_context() -> None:
    """
    Clear all execution context variables.

    Call this in a finally block after execution completes.
    """
    _tenant_id_var.set(None)
    _user_id_var.set(None)
    _user_role_ids_var.set(None)
    _is_admin_var.set(False)
    _session_id_var.set(None)
    _document_id_var.set(None)
    _extra_context_var.set({})

    logger.debug("🔓 Execution context cleared")


def get_tenant_id() -> Optional[str]:
    """Get the current tenant_id from execution context."""
    return _tenant_id_var.get()


def get_user_id() -> Optional[str]:
    """Get the current user_id from execution context."""
    return _user_id_var.get()


def get_user_role_ids() -> Optional[list]:
    """Get the current user's role IDs from execution context."""
    return _user_role_ids_var.get()


def get_is_admin() -> bool:
    """Get whether the current user is an admin."""
    return _is_admin_var.get()


def get_session_id() -> Optional[str]:
    """Get the current session_id from execution context."""
    return _session_id_var.get()


def get_document_id() -> Optional[str]:
    """Get the focus document_id from execution context."""
    return _document_id_var.get()


def resolve_document_id(llm_provided: Optional[str] = None) -> Optional[str]:
    """
    Resolve document_id with priority: context > LLM provided.

    Args:
        llm_provided: The document_id the LLM passed (may be wrong/placeholder)

    Returns:
        The correct document_id from context, or llm_provided as fallback,
        or None if no document_id is available
    """
    context_doc_id = _document_id_var.get()

    if context_doc_id:
        if llm_provided and llm_provided != context_doc_id:
            logger.debug(
                f"🔒 document_id resolved: LLM passed '{llm_provided}', "
                f"using context '{context_doc_id}'"
            )
        return context_doc_id

    if llm_provided:
        placeholders = ['contract_', 'doc_', 'document_', '12345', '67890', 'example', 'test']
        is_placeholder = any(p in llm_provided.lower() for p in placeholders)
        if is_placeholder:
            logger.warning(
                f"⚠️ LLM provided placeholder-like document_id: {llm_provided}, ignoring"
            )
            return None
        return llm_provided

    return None


def get_extra_context() -> Dict[str, Any]:
    """Get additional context values."""
    return _extra_context_var.get()


def get_tenant_id_or_raise() -> str:
    """
    Get tenant_id or raise an error if not set.

    Use this in tools that REQUIRE tenant isolation.

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

    Args:
        llm_provided: The tenant_id the LLM passed (may be wrong)

    Returns:
        The correct tenant_id from context, or llm_provided as fallback

    Raises:
        ValueError: If no tenant_id is available from any source
    """
    context_tenant_id = _tenant_id_var.get()

    if context_tenant_id:
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
