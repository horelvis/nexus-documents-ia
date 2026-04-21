"""
API endpoints for user management
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, func, select
from datetime import datetime, timedelta
import logging

from app.api.async_dependencies import get_async_db, get_current_user_async
from app.core.auth.base import UserProfile
from app.core.auth.acl import require_role
from app.db.models import User, Document
from app.schemas.user import (
    UserResponse,
    UserInvite,
    UserRoleUpdate,
    UserWithStats
)
from app.core.config import settings
from app.services.email_service import email_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/list", response_model=List[UserWithStats])
async def list_users(
    current_user: UserProfile = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_async_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None
):
    """
    List all users (admin only)
    """
    try:
        query = select(User)

        # Apply search filter if provided
        if search:
            search_filter = f"%{search}%"
            query = query.filter(
                or_(
                    User.email.ilike(search_filter),
                    User.full_name.ilike(search_filter)
                )
            )

        # Execute query
        result = await db.execute(query.offset(skip).limit(limit))
        users = result.scalars().all()

        # Get additional stats for each user
        users_with_stats = []
        for user in users:
            # Count documents
            doc_count_result = await db.execute(
                select(func.count(Document.id)).filter(Document.created_by == user.id)
            )
            doc_count = doc_count_result.scalar() or 0

            # Calculate storage used (sum of file sizes)
            storage_result = await db.execute(
                select(func.sum(Document.file_size)).filter(Document.created_by == user.id)
            )
            storage_used = storage_result.scalar() or 0

            # Determine user status
            if not user.is_active:
                status_str = "inactive"
            elif user.last_login_at is None:
                status_str = "pending"
            else:
                status_str = "active"

            # Determine role - check if user is superuser
            if user.is_superuser:
                role = "admin"
            else:
                role = "user"

            users_with_stats.append({
                "id": str(user.id),
                "email": user.email,
                "name": user.full_name,
                "role": role,
                "status": status_str,
                "createdAt": user.created_at.isoformat(),
                "lastLogin": user.last_login_at.isoformat() if user.last_login_at else None,
                "avatar": None,
                "documentsCount": doc_count,
                "storageUsed": storage_used
            })

        return users_with_stats

    except Exception as e:
        logger.error(f"Error listing users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list users"
        )


@router.post("/invite")
async def invite_user(
    invite_data: UserInvite,
    current_user: UserProfile = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Send invitation to a new user (admin only)
    """
    try:
        # Check if user already exists
        result = await db.execute(select(User).filter(User.email == invite_data.email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )

        organization_name = "NouxCube"

        # Generate invitation link
        invitation_link = f"{settings.FRONTEND_URL}/auth/sign-up?role={invite_data.role}"

        # Send invitation email
        inviter_name = current_user.name or current_user.email or current_user.sub
        email_sent = await email_service.send_user_invitation(
            email=invite_data.email,
            inviter_name=inviter_name,
            tenant_name=organization_name,
            invitation_link=invitation_link,
            role=invite_data.role
        )

        if not email_sent:
            logger.warning(f"Failed to send invitation email to {invite_data.email}")

        logger.info(f"Invitation sent to {invite_data.email} by {current_user.email or current_user.sub}")

        return {
            "message": f"Invitation sent to {invite_data.email}",
            "email": invite_data.email,
            "role": invite_data.role,
            "email_sent": email_sent
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inviting user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send invitation"
        )


@router.put("/{user_id}/role")
async def update_user_role(
    user_id: str,
    role_update: UserRoleUpdate,
    current_user: UserProfile = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update user role (admin only)
    """
    try:
        # Get the user
        result = await db.execute(
            select(User).filter(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Prevent self-demotion
        if str(user.id) == current_user.sub and role_update.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change your own admin role"
            )

        # Update role - set is_superuser based on role
        if role_update.role == "admin":
            user.is_superuser = True
        else:
            user.is_superuser = False

        await db.commit()

        logger.info(f"User {user.email} role updated to {role_update.role} by {current_user.email or current_user.sub}")

        return {
            "message": "Role updated successfully",
            "user_id": user_id,
            "new_role": role_update.role
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user role: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user role"
        )


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: UserProfile = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Delete a user (admin only)
    """
    try:
        # Get the user
        result = await db.execute(
            select(User).filter(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Prevent self-deletion
        if str(user.id) == current_user.sub:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account"
            )

        # Check if this is the last admin
        if user.is_superuser:
            admin_count_result = await db.execute(
                select(func.count(User.id)).filter(
                    and_(
                        User.is_superuser == True,
                        User.is_active == True
                    )
                )
            )
            admin_count = admin_count_result.scalar()

            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete the last admin user"
                )

        # Soft delete the user
        user.is_active = False
        await db.commit()

        logger.info(f"User {user.email} deleted by {current_user.email or current_user.sub}")

        return {
            "message": "User deleted successfully",
            "user_id": user_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user"
        )


@router.get("/{user_id}/activity")
async def get_user_activity(
    user_id: str,
    current_user: UserProfile = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_async_db),
    days: int = Query(30, ge=1, le=365)
):
    """
    Get user activity history (admin only)
    """
    try:
        # Verify user exists
        result = await db.execute(
            select(User).filter(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Get document activity
        doc_activity_result = await db.execute(
            select(
                func.date(Document.created_at).label('date'),
                func.count(Document.id).label('count')
            ).filter(
                and_(
                    Document.created_by == user_id,
                    Document.created_at >= start_date
                )
            ).group_by(func.date(Document.created_at))
        )
        doc_activity = doc_activity_result.all()

        activity_data = {
            "user_id": user_id,
            "email": user.email,
            "name": user.full_name,
            "period_days": days,
            "document_uploads": [
                {
                    "date": row.date.isoformat(),
                    "count": row.count
                }
                for row in doc_activity
            ],
            "last_login": user.last_login_at.isoformat() if user.last_login_at else None,
            "account_created": user.created_at.isoformat()
        }

        return activity_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user activity: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user activity"
        )
