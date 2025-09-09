"""
Edit Sessions API - RESTful endpoints for temporary Google Docs editing
Following Alfresco ECM pattern
"""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging

from app.core.security import require_api_key
from app.services.edit_session_service import edit_session_service
from app.schemas.edit_session import (
    EditSessionCreate,
    EditSessionResponse,
    EditSessionFinish,
    EditSessionExtend,
    EditSessionStats
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/edit-sessions", tags=["Edit Sessions"])


# Import database dependency
from app.core.database import get_async_db


# Dependency for API key authentication
async def verify_api_key_header(authorization: str = Header(...)):
    """Verify API key from Authorization header"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format"
        )
    
    api_key = authorization.split(" ")[1]
    require_api_key(api_key)
    return api_key


@router.post("/", response_model=EditSessionResponse)
async def create_edit_session(
    session_data: EditSessionCreate,
    db: AsyncSession = Depends(get_async_db),
    api_key: str = Depends(verify_api_key_header)
):
    """
    Create new editing session with temporary Google Doc
    
    This endpoint follows the Alfresco ECM pattern:
    1. Creates temporary Google Doc
    2. Sets appropriate permissions
    3. Returns edit URLs and session info
    """
    try:
        logger.info(f"📝 Creating edit session for template {session_data.template_id}")
        
        session = await edit_session_service.create_edit_session(
            db=db,
            template_id=session_data.template_id,
            template_name=session_data.template_name,
            template_content=session_data.template_content,
            user_id=session_data.user_id,
            user_email=session_data.user_email,
            tenant_id=session_data.tenant_id
        )
        
        return EditSessionResponse.from_orm(session)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"❌ Failed to create edit session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create edit session"
        )


@router.get("/{session_id}", response_model=EditSessionResponse)
async def get_edit_session(
    session_id: str,
    user_id: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db),
    api_key: str = Depends(verify_api_key_header)
):
    """Get edit session details"""
    try:
        session = await edit_session_service.get_edit_session(
            db=db,
            session_id=session_id,
            user_id=user_id
        )
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Edit session not found"
            )
        
        return EditSessionResponse.from_orm(session)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get edit session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get edit session"
        )


@router.post("/{session_id}/finish")
async def finish_edit_session(
    session_id: str,
    finish_data: EditSessionFinish,
    db: AsyncSession = Depends(get_async_db),
    api_key: str = Depends(verify_api_key_header)
):
    """
    Finish editing session - sync changes and cleanup
    
    Following Alfresco pattern:
    1. Get updated content from Google Doc
    2. Sync changes back to main template system
    3. Delete temporary Google Doc
    4. Mark session as completed
    """
    try:
        logger.info(f"✅ Finishing edit session {session_id}")
        
        result = await edit_session_service.finish_edit_session(
            db=db,
            session_id=session_id,
            user_id=finish_data.user_id
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"❌ Failed to finish edit session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to finish edit session"
        )


@router.post("/{session_id}/extend", response_model=EditSessionResponse)
async def extend_edit_session(
    session_id: str,
    extend_data: EditSessionExtend,
    db: AsyncSession = Depends(get_async_db),
    api_key: str = Depends(verify_api_key_header)
):
    """Extend session expiration time"""
    try:
        session = await edit_session_service.extend_session(
            db=db,
            session_id=session_id,
            user_id=extend_data.user_id,
            hours=extend_data.hours
        )
        
        return EditSessionResponse.from_orm(session)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"❌ Failed to extend edit session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to extend edit session"
        )


@router.delete("/{session_id}")
async def cancel_edit_session(
    session_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_async_db),
    api_key: str = Depends(verify_api_key_header)
):
    """Cancel editing session and cleanup Google Doc"""
    try:
        result = await edit_session_service.cancel_edit_session(
            db=db,
            session_id=session_id,
            user_id=user_id
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"❌ Failed to cancel edit session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel edit session"
        )


@router.get("/user/{user_id}", response_model=List[EditSessionResponse])
async def get_user_sessions(
    user_id: str,
    tenant_id: str,
    include_completed: bool = False,
    db: AsyncSession = Depends(get_async_db),
    api_key: str = Depends(verify_api_key_header)
):
    """Get all sessions for a user"""
    try:
        sessions = await edit_session_service.get_user_sessions(
            db=db,
            user_id=user_id,
            tenant_id=tenant_id,
            include_completed=include_completed
        )
        
        return [EditSessionResponse.from_orm(session) for session in sessions]
        
    except Exception as e:
        logger.error(f"❌ Failed to get user sessions for {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user sessions"
        )


@router.post("/cleanup", response_model=EditSessionStats)
async def cleanup_expired_sessions(
    db: AsyncSession = Depends(get_async_db),
    api_key: str = Depends(verify_api_key_header)
):
    """
    Manual cleanup of expired sessions
    
    This endpoint allows manual trigger of the cleanup process
    that normally runs as a background task
    """
    try:
        logger.info("🧹 Manual cleanup triggered")
        
        stats = await edit_session_service.cleanup_expired_sessions(db)
        
        return EditSessionStats(**stats)
        
    except Exception as e:
        logger.error(f"❌ Failed to cleanup expired sessions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cleanup expired sessions"
        )


@router.get("/stats", response_model=EditSessionStats)
async def get_edit_session_stats(
    tenant_id: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db),
    api_key: str = Depends(verify_api_key_header)
):
    """Get statistics about edit sessions"""
    try:
        # This would be implemented to gather statistics
        # For now, return placeholder data
        stats = {
            "total_sessions": 0,
            "active_sessions": 0,
            "completed_sessions": 0,
            "expired_sessions": 0,
            "cleanup_errors": 0
        }
        
        return EditSessionStats(**stats)
        
    except Exception as e:
        logger.error(f"❌ Failed to get edit session stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get edit session statistics"
        )