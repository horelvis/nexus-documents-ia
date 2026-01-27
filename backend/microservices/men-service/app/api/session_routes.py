"""
Session management routes for MEN service.

Endpoints for managing conversational memory:
- GET /men/sessions/{session_id}/history
- POST /men/sessions/{session_id}/clear
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from ..core.security import verify_api_key
from ..services import get_men_system

from .schemas import (
    SessionHistoryResponse,
    SessionMessage,
    ClearSessionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/men/sessions", tags=["MEN Sessions"])


@router.get("/{session_id}/history", response_model=SessionHistoryResponse)
async def get_session_history(
    session_id: str,
    tenant_id: str = Query(..., description="Tenant ID"),
    _: bool = Depends(verify_api_key)
):
    """
    Get conversation history for a session.

    Returns all messages (user + assistant) stored in the
    session's conversational memory.

    The history is limited to the last N turns as configured
    in MEN_MODELER_HISTORY_TURNS (default: 5 turns).
    """
    try:
        men_system = get_men_system()

        history = men_system.get_session_history(tenant_id, session_id)

        return SessionHistoryResponse(
            session_id=session_id,
            tenant_id=tenant_id,
            history=[SessionMessage(**msg) for msg in history],
            message_count=len(history)
        )

    except Exception as e:
        logger.error(f"Failed to get session history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get session history: {str(e)}"
        )


@router.post("/{session_id}/clear", response_model=ClearSessionResponse)
async def clear_session(
    session_id: str,
    tenant_id: str = Query(..., description="Tenant ID"),
    _: bool = Depends(verify_api_key)
):
    """
    Clear conversational memory for a session.

    Use this to:
    - Start a fresh conversation
    - Clear context after topic change
    - Free memory for inactive sessions

    Note: This does not delete any persisted data, only
    the in-memory conversation history.
    """
    try:
        men_system = get_men_system()

        cleared = men_system.clear_session(tenant_id, session_id)

        return ClearSessionResponse(
            message=f"Session '{session_id}' cleared" if cleared else f"Session '{session_id}' not found",
            session_id=session_id,
            cleared=cleared
        )

    except Exception as e:
        logger.error(f"Failed to clear session: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear session: {str(e)}"
        )


@router.get("/active")
async def list_active_sessions(
    tenant_id: str = Query(None, description="Filter by tenant ID"),
    _: bool = Depends(verify_api_key)
):
    """
    List active sessions with conversation history.

    Optionally filter by tenant_id.
    """
    try:
        men_system = get_men_system()

        if not men_system.llm_modeler:
            return {"sessions": [], "count": 0}

        all_sessions = men_system.llm_modeler.get_all_sessions()

        # Filter by tenant if specified
        if tenant_id:
            prefix = f"{tenant_id}:"
            sessions = [s for s in all_sessions if s.startswith(prefix)]
        else:
            sessions = all_sessions

        return {
            "sessions": sessions,
            "count": len(sessions),
            "filtered_by_tenant": tenant_id
        }

    except Exception as e:
        logger.error(f"Failed to list sessions: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list sessions: {str(e)}"
        )
