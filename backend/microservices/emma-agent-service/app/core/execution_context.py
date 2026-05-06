"""
Execution Context for Emma Agent Service Tools.

This module provides thread-safe context variables that are automatically
available to all tools during execution, eliminating the need for LLMs
to extract and pass authentication data correctly.

ARCHITECTURE:
┌─────────────────────────────────────────────────────────────┐
│              API Entry Point (query/stream)                  │
│                                                             │
│  1. set_execution_context(                                  │
│         user_id="yyy",                                      │
│         user_roles=["LEGAL", "SALES"],                      │
│     )                                                       │
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐│
│  │         LangGraph / Emma executes                       ││
│  │                          │                               ││
│  │                          ▼                               ││
│  │  ┌───────────────────────────────────────────────────┐  ││
│  │  │         Tool function (e.g., document_search)     │  ││
│  │  │                                                   │  ││
│  │  │  user_roles = get_user_roles_or_default()         │  ││
│  │  │    # → ["LEGAL", "SALES", "EVERYONE"]             │  ││
│  │  │  user_id = get_user_id_or_raise()                 │  ││
│  │  │                                                   │  ││
│  │  └───────────────────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  2. clear_execution_context()                               │
└─────────────────────────────────────────────────────────────┘

Usage in tools:
    from app.core.execution_context import (
        get_user_id_or_raise,
        get_user_roles_or_default,
    )

    async def document_search(query: str, ...) -> str:
        user_id = get_user_id_or_raise()
        user_roles = get_user_roles_or_default()  # includes EVERYONE
        # Then build an ACL-filtered Weaviate / SQL query.
        ...

Usage in entry points:
    from app.core.execution_context import (
        set_execution_context,
        clear_execution_context,
    )

    set_execution_context(user_id=user_id, user_roles=user_roles)
    try:
        result = await execute(...)
    finally:
        clear_execution_context()

Single-tenant note:
    Before the multi-tenancy removal, this module tracked `tenant_id`
    as the primary ACL scope and `user_role_ids` as a list of UUID
    references into a per-tenant Role table. Both concepts are gone.
    Now the ACL scope is `user_roles: List[str]` — KeyCloak role
    names like ["LEGAL", "SALES"] that are compared against the
    `roles: List[str]` column on Document / IndexedDocument / etc.
    The EVERYONE wildcard is injected via `get_user_roles_or_default()`.
"""

import logging
from contextvars import ContextVar
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)

# Context variables for execution
_user_id_var: ContextVar[Optional[str]] = ContextVar('user_id', default=None)
_user_roles_var: ContextVar[List[str]] = ContextVar('user_roles', default=[])
_is_admin_var: ContextVar[bool] = ContextVar('is_admin', default=False)
_session_id_var: ContextVar[Optional[str]] = ContextVar('session_id', default=None)
_document_id_var: ContextVar[Optional[str]] = ContextVar('document_id', default=None)
_extra_context_var: ContextVar[Dict[str, Any]] = ContextVar('extra_context')


def set_execution_context(
    user_id: Optional[str] = None,
    user_roles: Optional[List[str]] = None,
    is_admin: bool = False,
    session_id: Optional[str] = None,
    document_id: Optional[str] = None,
    **extra: Any,
) -> None:
    """
    Set execution context for the current async task.

    This context is automatically available to all tools
    called during this execution, regardless of how deeply nested.

    Args:
        user_id: Authenticated user identifier (sub claim from the JWT).
        user_roles: KeyCloak role names for this user (without EVERYONE;
            use `get_user_roles_or_default()` to fold in the wildcard).
        is_admin: Whether the user is an admin (bypasses ACL checks).
        session_id: Optional session identifier.
        document_id: Optional focus document ID (for document-specific queries).
        **extra: Additional context values.
    """
    if user_id:
        _user_id_var.set(user_id)

    _user_roles_var.set(list(user_roles or []))
    _is_admin_var.set(is_admin)

    if session_id:
        _session_id_var.set(session_id)

    if document_id:
        _document_id_var.set(document_id)

    if extra:
        _extra_context_var.set(extra)

    logger.debug(
        "🔐 Execution context set: user=%s, doc=%s, roles=%d, admin=%s",
        user_id, document_id, len(user_roles or []), is_admin,
    )


def clear_execution_context() -> None:
    """
    Clear all execution context variables.

    Call this in a finally block after execution completes.
    """
    _user_id_var.set(None)
    _user_roles_var.set([])
    _is_admin_var.set(False)
    _session_id_var.set(None)
    _document_id_var.set(None)
    _extra_context_var.set({})

    logger.debug("🔓 Execution context cleared")


def get_user_id() -> Optional[str]:
    """Get the current user_id from execution context."""
    return _user_id_var.get()


def get_user_id_or_raise() -> str:
    """Get user_id or raise RuntimeError if not set.

    Use this in tools that REQUIRE an authenticated user (e.g. to scope
    a query to the user's own rows or to record audit attribution).

    Raises:
        RuntimeError: If user_id is not set in context.
    """
    user_id = _user_id_var.get()
    if not user_id:
        raise RuntimeError(
            "user_id not found in execution context. "
            "Ensure set_execution_context() was called before executing tools."
        )
    return user_id


def get_user_roles() -> List[str]:
    """Get the raw KeyCloak role names from execution context.

    Does NOT include the EVERYONE wildcard. Use `get_user_roles_or_default()`
    for ACL-filter queries where you want EVERYONE-tagged rows visible
    regardless of the user's explicit role list.
    """
    return list(_user_roles_var.get())


def get_user_roles_or_default() -> List[str]:
    """Get user roles from the execution context (informational only after ACL removal).

    After role-based ACL removal, all documents are visible to all authenticated
    users. This function is kept for API compatibility; callers that used it to
    build ACL-filtered queries should now drop those filters.
    """
    return list(_user_roles_var.get() or [])


def get_is_admin() -> bool:
    """Get whether the current user is an admin.

    Admin is ORTHOGONAL to roles. An admin still has their own
    user_roles list; the `is_admin=True` flag is an additional bit that
    tools can use to bypass ACL checks entirely.
    """
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
        or None if no document_id is available.
    """
    context_doc_id = _document_id_var.get()

    if context_doc_id:
        if llm_provided and llm_provided != context_doc_id:
            logger.debug(
                "🔒 document_id resolved: LLM passed '%s', using context '%s'",
                llm_provided, context_doc_id,
            )
        return context_doc_id

    if llm_provided:
        placeholders = ['contract_', 'doc_', 'document_', '12345', '67890', 'example', 'test']
        is_placeholder = any(p in llm_provided.lower() for p in placeholders)
        if is_placeholder:
            logger.warning(
                "⚠️ LLM provided placeholder-like document_id: %s, ignoring",
                llm_provided,
            )
            return None
        return llm_provided

    return None


def get_extra_context() -> Dict[str, Any]:
    """Get additional context values."""
    try:
        return _extra_context_var.get()
    except LookupError:
        return {}
