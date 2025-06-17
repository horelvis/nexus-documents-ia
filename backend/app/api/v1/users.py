"""
API endpoints for user management
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta
import logging

from app.api.dependencies import get_db, get_current_admin_user
from app.db.models import User, Document, Tenant
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
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None
):
    """
    List all users in the current tenant (admin only)
    """
    try:
        # Base query for users in the same tenant
        query = select(User).where(User.tenant_id == current_user.tenant_id)
        
        # Apply search filter if provided
        if search:
            search_filter = f"%{search}%"
            query = query.where(
                User.email.ilike(search_filter) | 
                User.name.ilike(search_filter)
            )
        
        # Execute query
        result = await db.execute(query.offset(skip).limit(limit))
        users = result.scalars().all()
        
        # Get additional stats for each user
        users_with_stats = []
        for user in users:
            # Count documents
            doc_count_result = await db.execute(
                select(func.count(Document.id)).where(
                    Document.user_id == user.id
                )
            )
            doc_count = doc_count_result.scalar() or 0
            
            # Calculate storage used (sum of file sizes)
            storage_result = await db.execute(
                select(func.sum(Document.file_size)).where(
                    Document.user_id == user.id
                )
            )
            storage_used = storage_result.scalar() or 0
            
            # Determine user status
            if not user.is_active:
                status = "inactive"
            elif user.last_login_at is None:
                status = "pending"
            else:
                status = "active"
            
            users_with_stats.append({
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "status": status,
                "createdAt": user.created_at.isoformat(),
                "lastLogin": user.last_login_at.isoformat() if user.last_login_at else None,
                "avatar": user.avatar_url,
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
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Send invitation to a new user (admin only)
    """
    try:
        # Check if user already exists
        existing_user = await db.execute(
            select(User).where(User.email == invite_data.email)
        )
        if existing_user.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # TODO: In a real implementation, this would:
        # 1. Create a pending invitation in the database
        # 2. Send an invitation email with a signup link
        # 3. The link would include a token to associate the new user with this tenant
        
        # For now, we'll just return success
        logger.info(f"Invitation sent to {invite_data.email} by {current_user.email}")
        
        # Send invitation email (mock for now)
        if email_service:
            await email_service.send_invitation_email(
                to_email=invite_data.email,
                inviter_name=current_user.name or current_user.email,
                tenant_name=current_user.tenant.name if hasattr(current_user, 'tenant') else "Organization",
                role=invite_data.role
            )
        
        return {
            "message": f"Invitation sent to {invite_data.email}",
            "email": invite_data.email,
            "role": invite_data.role
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
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update user role (admin only)
    """
    try:
        # Get the user
        result = await db.execute(
            select(User).where(
                and_(
                    User.id == user_id,
                    User.tenant_id == current_user.tenant_id
                )
            )
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent self-demotion
        if str(user.id) == str(current_user.id) and role_update.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change your own admin role"
            )
        
        # Update role
        user.role = role_update.role
        await db.commit()
        
        logger.info(f"User {user.email} role updated to {role_update.role} by {current_user.email}")
        
        return {
            "message": "Role updated successfully",
            "user_id": user_id,
            "new_role": role_update.role
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user role: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user role"
        )

@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a user (admin only)
    """
    try:
        # Get the user
        result = await db.execute(
            select(User).where(
                and_(
                    User.id == user_id,
                    User.tenant_id == current_user.tenant_id
                )
            )
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent self-deletion
        if str(user.id) == str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account"
            )
        
        # Check if this is the last admin
        if user.role == "admin":
            admin_count = await db.execute(
                select(func.count(User.id)).where(
                    and_(
                        User.tenant_id == current_user.tenant_id,
                        User.role == "admin",
                        User.is_active == True
                    )
                )
            )
            if admin_count.scalar() <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete the last admin user"
                )
        
        # Soft delete the user
        user.is_active = False
        user.deleted_at = datetime.utcnow()
        await db.commit()
        
        logger.info(f"User {user.email} deleted by {current_user.email}")
        
        return {
            "message": "User deleted successfully",
            "user_id": user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user"
        )

@router.get("/{user_id}/activity")
async def get_user_activity(
    user_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365)
):
    """
    Get user activity history (admin only)
    """
    try:
        # Verify user exists and belongs to same tenant
        result = await db.execute(
            select(User).where(
                and_(
                    User.id == user_id,
                    User.tenant_id == current_user.tenant_id
                )
            )
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
        doc_activity = await db.execute(
            select(
                func.date(Document.created_at).label('date'),
                func.count(Document.id).label('count')
            ).where(
                and_(
                    Document.user_id == user_id,
                    Document.created_at >= start_date
                )
            ).group_by(func.date(Document.created_at))
        )
        
        activity_data = {
            "user_id": user_id,
            "email": user.email,
            "name": user.name,
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