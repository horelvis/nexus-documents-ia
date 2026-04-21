"""
Execution Context for Agent Framework Tools.

This module provides thread-safe context variables that are automatically
available to all @ai_function tools during execution, eliminating the need
for LLMs to extract and pass user identity correctly.

ARCHITECTURE:
┌─────────────────────────────────────────────────────────────┐
│                    EmmaCoordinator.execute()                 │
│                                                             │
│  1. set_execution_context(                                  │
│         user_id="yyy",                                      │
│         user_roles=["LEGAL", "SALES"],                      │
│     )                                                       │
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              ChatAgent.run() → SearchAgent              ││
│  │                          │                               ││
│  │                          ▼                               ││
│  │  ┌───────────────────────────────────────────────────┐  ││
│  │  │         @ai_function semantic_search()            │  ││
│  │  │                                                   │  ││
│  │  │  # Get the authenticated roles from context        │  ││
│  │  │  user_roles = get_user_roles_or_default()          │  ││
│  │  │  # → ["LEGAL", "SALES", "EVERYONE"]                │  ││
│  │  │                                                   │  ││
│  │  └───────────────────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  2. clear_execution_context()                               │
└─────────────────────────────────────────────────────────────┘

Usage in @ai_function tools:
    from app.core.execution_context import get_user_id, get_user_roles_or_default

    @ai_function
    async def semantic_search(query: str, ...) -> str:
        user_id = get_user_id()
        user_roles = get_user_roles_or_default()
        ...

Usage in EmmaCoordinator:
    from app.core.execution_context import set_execution_context, clear_execution_context

    async def execute(self, query, user_id, user_roles, ...):
        set_execution_context(user_id=user_id, user_roles=user_roles)
        try:
            result = await self._emma.run(...)
        finally:
            clear_execution_context()
"""

import logging
from contextvars import ContextVar
from typing import Optional, Any, Dict, List

from app.core.auth_headers import EVERYONE_ROLE, allowed_roles

logger = logging.getLogger(__name__)

# Context variables for execution
_user_id_var: ContextVar[Optional[str]] = ContextVar('user_id', default=None)
_user_roles_var: ContextVar[Optional[List[str]]] = ContextVar('user_roles', default=None)
_is_admin_var: ContextVar[bool] = ContextVar('is_admin', default=False)
_session_id_var: ContextVar[Optional[str]] = ContextVar('session_id', default=None)
_document_id_var: ContextVar[Optional[str]] = ContextVar('document_id', default=None)
_extra_context_var: ContextVar[Dict[str, Any]] = ContextVar('extra_context', default={})


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

    This context is automatically available to all @ai_function tools
    called during this execution, regardless of how deeply nested.

    Args:
        user_id: Authenticated user identifier
        user_roles: List of KeyCloak role names the user belongs to (ACL)
        is_admin: Whether the user is an admin (bypasses ACL checks)
        session_id: Optional session identifier
        document_id: Optional focus document ID (for document-specific queries)
        **extra: Additional context values
    """
    if user_id:
        _user_id_var.set(user_id)

    if user_roles is not None:
        _user_roles_var.set(list(user_roles))

    _is_admin_var.set(is_admin)

    if session_id:
        _session_id_var.set(session_id)

    if document_id:
        _document_id_var.set(document_id)

    if extra:
        _extra_context_var.set(extra)

    logger.debug(
        f"🔐 Execution context set: user={user_id}, doc={document_id}, "
        f"roles={len(user_roles or [])}, admin={is_admin}"
    )


def clear_execution_context() -> None:
    """
    Clear all execution context variables.

    Call this in a finally block after execution completes.
    """
    _user_id_var.set(None)
    _user_roles_var.set(None)
    _is_admin_var.set(False)
    _session_id_var.set(None)
    _document_id_var.set(None)
    _extra_context_var.set({})

    logger.debug("🔓 Execution context cleared")


def get_user_id() -> Optional[str]:
    """Get the current user_id from execution context (may be None)."""
    return _user_id_var.get()


def get_user_id_or_raise() -> str:
    """Get the current user_id or raise if not set."""
    user_id = _user_id_var.get()
    if not user_id:
        raise RuntimeError(
            "user_id not found in execution context. "
            "Ensure set_execution_context() was called before executing tools."
        )
    return user_id


def get_user_roles() -> Optional[List[str]]:
    """Return the raw user roles list (or None if not set)."""
    return _user_roles_var.get()


def get_user_roles_or_default() -> List[str]:
    """Return the user roles folded with the EVERYONE wildcard.

    If no roles are set in the execution context, returns a list
    containing only the EVERYONE sentinel so that public documents
    are still reachable.
    """
    roles = _user_roles_var.get()
    if roles is None:
        return [EVERYONE_ROLE]
    return allowed_roles(roles)


def get_is_admin() -> bool:
    """Whether the current user is an admin (bypasses ACL checks)."""
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

    Ensures the context-provided document_id takes precedence over
    whatever the LLM might have passed.
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
