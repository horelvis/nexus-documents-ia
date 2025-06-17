"""
API endpoints for user management
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import datetime, timedelta
import logging

from app.api.dependencies import get_db, get_current_active_superuser
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
def list_users(
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None
):
    """
    List all users in the current tenant (admin only)
    """
    try:
        # Base query for users in the same tenant
        query = db.query(User).filter(User.tenant_id == current_user.tenant_id)
        
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
        users = query.offset(skip).limit(limit).all()
        
        # Get additional stats for each user
        users_with_stats = []
        for user in users:
            # Count documents
            doc_count = db.query(func.count(Document.id)).filter(
                Document.created_by == user.id
            ).scalar() or 0
            
            # Calculate storage used (sum of file sizes)
            storage_used = db.query(func.sum(Document.file_size)).filter(
                Document.created_by == user.id
            ).scalar() or 0
            
            # Determine user status
            if not user.is_active:
                status = "inactive"
            elif user.last_login_at is None:
                status = "pending"
            else:
                status = "active"
            
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
                "status": status,
                "createdAt": user.created_at.isoformat(),
                "lastLogin": user.last_login_at.isoformat() if user.last_login_at else None,
                "avatar": None,  # Add avatar URL if available
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
def invite_user(
    invite_data: UserInvite,
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db)
):
    """
    Send invitation to a new user (admin only)
    """
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == invite_data.email).first()
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # Get tenant info
        tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
        tenant_name = tenant.name if tenant else "Organization"
        
        # Generate invitation link (in a real implementation, you'd create a token)
        invitation_link = f"{settings.FRONTEND_URL}/auth/sign-up?tenant={current_user.tenant_id}&role={invite_data.role}"
        
        # Send invitation email
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        email_sent = loop.run_until_complete(
            email_service.send_user_invitation(
                email=invite_data.email,
                inviter_name=current_user.full_name or current_user.email,
                tenant_name=tenant_name,
                invitation_link=invitation_link,
                role=invite_data.role
            )
        )
        
        if not email_sent:
            logger.warning(f"Failed to send invitation email to {invite_data.email}")
        
        logger.info(f"Invitation sent to {invite_data.email} by {current_user.email}")
        
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
def update_user_role(
    user_id: str,
    role_update: UserRoleUpdate,
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db)
):
    """
    Update user role (admin only)
    """
    try:
        # Get the user
        user = db.query(User).filter(
            and_(
                User.id == user_id,
                User.tenant_id == current_user.tenant_id
            )
        ).first()
        
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
        
        # Update role - set is_superuser based on role
        if role_update.role == "admin":
            user.is_superuser = True
        else:
            user.is_superuser = False
            
        db.commit()
        
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
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user role"
        )

@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db)
):
    """
    Delete a user (admin only)
    """
    try:
        # Get the user
        user = db.query(User).filter(
            and_(
                User.id == user_id,
                User.tenant_id == current_user.tenant_id
            )
        ).first()
        
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
        if user.is_superuser:
            admin_count = db.query(func.count(User.id)).filter(
                and_(
                    User.tenant_id == current_user.tenant_id,
                    User.is_superuser == True,
                    User.is_active == True
                )
            ).scalar()
            
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete the last admin user"
                )
        
        # Soft delete the user
        user.is_active = False
        db.commit()
        
        logger.info(f"User {user.email} deleted by {current_user.email}")
        
        return {
            "message": "User deleted successfully",
            "user_id": user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user"
        )

@router.get("/{user_id}/activity")
def get_user_activity(
    user_id: str,
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365)
):
    """
    Get user activity history (admin only)
    """
    try:
        # Verify user exists and belongs to same tenant
        user = db.query(User).filter(
            and_(
                User.id == user_id,
                User.tenant_id == current_user.tenant_id
            )
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get document activity
        doc_activity = db.query(
            func.date(Document.created_at).label('date'),
            func.count(Document.id).label('count')
        ).filter(
            and_(
                Document.created_by == user_id,
                Document.created_at >= start_date
            )
        ).group_by(func.date(Document.created_at)).all()
        
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