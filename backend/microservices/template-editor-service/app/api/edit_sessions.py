"""
Edit Sessions API - RESTful endpoints for temporary Google Docs editing
Following Alfresco ECM pattern
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.security import require_api_key
from app.schemas.edit_session import (
    EditSessionCreate,
    EditSessionResponse,
    EditSessionFinish,
    EditSessionExtend,
    EditSessionStats,
)
from app.services.edit_session_service import edit_session_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/edit-sessions", tags=["Edit Sessions"])


async def verify_api_key_header(authorization: str = Header(...)) -> str:
    """Verify API key from Authorization header"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )
    api_key = authorization.split(" ")[1]
    require_api_key(api_key)
    return api_key


@router.post("/", response_model=EditSessionResponse)
async def create_edit_session(
    session_data: EditSessionCreate,
    api_key: str = Depends(verify_api_key_header),
):
    """Create new editing session with temporary Google Doc"""
    try:
        session = await edit_session_service.create_edit_session(
            template_id=session_data.template_id,
            template_name=session_data.template_name,
            template_file_base64=session_data.template_file_base64,
            template_content=session_data.template_content,
            template_file_name=session_data.template_file_name,
            template_file_mime=session_data.template_file_mime,
            user_id=session_data.user_id,
            user_email=session_data.user_email,
            tenant_id=session_data.tenant_id,
        )
        return EditSessionResponse(**session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("❌ Failed to create edit session: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create edit session") from exc


@router.get("/{session_id}", response_model=EditSessionResponse)
async def get_edit_session(
    session_id: str,
    user_id: Optional[str] = None,
    api_key: str = Depends(verify_api_key_header),
):
    """Get edit session details"""
    try:
        session = await edit_session_service.get_edit_session(
            session_id=session_id, user_id=user_id
        )
        return EditSessionResponse(**session)
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("❌ Failed to get edit session %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail="Failed to get edit session") from exc


@router.post("/{session_id}/finish")
async def finish_edit_session(
    session_id: str,
    finish_data: EditSessionFinish,
    api_key: str = Depends(verify_api_key_header),
):
    """Finish editing session - sync changes and cleanup"""
    try:
        return await edit_session_service.finish_edit_session(
            session_id=session_id,
            user_id=finish_data.user_id,
            force_sync=finish_data.force_sync,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("❌ Failed to finish edit session %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail="Failed to finish edit session") from exc


@router.post("/{session_id}/extend", response_model=EditSessionResponse)
async def extend_edit_session(
    session_id: str,
    extend_data: EditSessionExtend,
    api_key: str = Depends(verify_api_key_header),
):
    """Extend session expiration time"""
    try:
        session = await edit_session_service.extend_session(
            session_id=session_id,
            user_id=extend_data.user_id,
            hours=extend_data.hours,
        )
        return EditSessionResponse(**session)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("❌ Failed to extend edit session %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail="Failed to extend edit session") from exc


@router.delete("/{session_id}")
async def cancel_edit_session(
    session_id: str,
    user_id: str,
    api_key: str = Depends(verify_api_key_header),
):
    """Cancel editing session and cleanup Google Doc"""
    try:
        return await edit_session_service.cancel_edit_session(
            session_id=session_id,
            user_id=user_id,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("❌ Failed to cancel edit session %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail="Failed to cancel edit session") from exc


@router.get("/user/{user_id}", response_model=List[EditSessionResponse])
async def get_user_sessions(
    user_id: str,
    tenant_id: str,
    include_completed: bool = False,
    api_key: str = Depends(verify_api_key_header),
):
    """Get all sessions for a user"""
    try:
        sessions = await edit_session_service.get_user_sessions(
            user_id=user_id,
            tenant_id=tenant_id,
            include_completed=include_completed,
        )
        return [EditSessionResponse(**session) for session in sessions.get("sessions", [])]
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("❌ Failed to get user sessions for %s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Failed to get user sessions") from exc


@router.post("/cleanup", response_model=EditSessionStats)
async def cleanup_expired_sessions(api_key: str = Depends(verify_api_key_header)):
    """Manual cleanup of expired sessions"""
    try:
        stats = await edit_session_service._cleanup_expired_sessions()  # pylint: disable=protected-access
        return EditSessionStats(
            total_sessions=stats.get("total", 0),
            active_sessions=stats.get("success", 0),
            completed_sessions=0,
            expired_sessions=stats.get("expired", 0),
            cleanup_errors=stats.get("errors", 0),
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("❌ Failed to cleanup sessions: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to cleanup sessions") from exc
