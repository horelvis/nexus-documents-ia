"""
API endpoints for team management (tenant-based)
Each tenant represents one team
"""
import secrets
import qrcode
import io
import base64
from datetime import datetime, timedelta
from typing import List, Optional, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, func, select
from sqlalchemy.orm import selectinload

from app.api.async_dependencies import get_async_db, get_current_active_user_async, get_current_active_superuser_async, get_current_tenant_admin_async
from app.db.models import User, Document, Tenant, TeamInvitation
from app.schemas.team import (
    TeamUpdate,
    TeamResponse,
    TeamWithMembers,
    TeamMemberAdd,
    TeamMemberResponse,
    TeamInvitationCreate,
    TeamInvitationResponse,
    TeamInvitationAccept
)
from app.core.config import settings
from app.services.email_service import email_service

import logging
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()

# ===========================
# TEAM (TENANT) ENDPOINTS
# ===========================

@router.get("/", response_model=TeamResponse)
async def get_team_info(
    current_user: User = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current team (tenant) information
    """
    try:
        # Get tenant info
        result = await db.execute(select(Tenant).filter(Tenant.id == current_user.tenant_id))
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )
        
        # Count team members
        result = await db.execute(
            select(func.count(User.id)).filter(
                and_(
                    User.tenant_id == tenant.id,
                    User.is_active == True
                )
            )
        )
        members_count = result.scalar() or 0
        
        # Convert storage from MB to GB for display
        storage_quota_gb = (tenant.max_storage_mb or 5120) // 1024  # Default 5GB if not set
        
        return TeamResponse(
            id=tenant.id,
            name=tenant.name,
            description=tenant.description,
            created_at=tenant.created_at,
            updated_at=tenant.updated_at,
            members_count=members_count,
            storage_quota=storage_quota_gb,
            is_active=tenant.is_active
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting team info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get team information"
        )

@router.put("/", response_model=TeamResponse)
async def update_team_info(
    team_update: TeamUpdate,
    current_user: User = Depends(get_current_tenant_admin_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update team (tenant) information (admin only)
    """
    try:
        # Get tenant
        result = await db.execute(select(Tenant).filter(Tenant.id == current_user.tenant_id))
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )
        
        # Update fields
        if team_update.name is not None:
            tenant.name = team_update.name
        if team_update.description is not None:
            tenant.description = team_update.description
        
        tenant.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(tenant)
        
        # Count team members
        result = await db.execute(
            select(func.count(User.id)).filter(
                and_(
                    User.tenant_id == tenant.id,
                    User.is_active == True
                )
            )
        )
        members_count = result.scalar() or 0
        
        logger.info(f"Team {tenant.name} updated by {current_user.email}")
        
        # Convert storage from MB to GB for display
        storage_quota_gb = (tenant.max_storage_mb or 5120) // 1024  # Default 5GB if not set
        
        return TeamResponse(
            id=tenant.id,
            name=tenant.name,
            description=tenant.description,
            created_at=tenant.created_at,
            updated_at=tenant.updated_at,
            members_count=members_count,
            storage_quota=storage_quota_gb,
            is_active=tenant.is_active
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating team: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update team"
        )

@router.get("/members", response_model=List[TeamMemberResponse])
async def get_team_members(
    current_user: User = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None
):
    """
    Get all team members (users in the tenant)
    """
    try:
        # Base query for users in the same tenant
        query = select(User).filter(
            and_(
                User.tenant_id == current_user.tenant_id,
                User.is_active == True
            )
        )
        
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
        result = await db.execute(
            query.offset(skip).limit(limit).order_by(User.created_at.desc())
        )
        members = result.scalars().all()
        
        # Get the admin user to inherit subscription plan
        admin_user = next((u for u in members if not u.is_team_member), None)
        tenant_plan = admin_user.subscription_plan if admin_user else 'free'
        
        return [TeamMemberResponse(
            id=member.id,
            email=member.email,
            full_name=member.full_name,
            is_team_member=member.is_team_member,
            is_active=member.is_active,
            created_at=member.created_at,
            role="Team Member" if member.is_team_member else "Admin",
            subscription_plan=tenant_plan if member.is_team_member else member.subscription_plan,
            invited_at=member.invited_at
        ) for member in members]
        
    except Exception as e:
        logger.error(f"Error listing team members: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list team members"
        )

@router.post("/members/invite")
async def invite_team_member(
    member_data: TeamMemberAdd,
    current_user: User = Depends(get_current_tenant_admin_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Invite a new team member (admin only)
    """
    try:
        # Check if user already exists
        result = await db.execute(
            select(User).filter(
                and_(
                    User.email == member_data.email,
                    User.tenant_id == current_user.tenant_id
                )
            )
        )
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of this team"
            )
        
        # Check if any user with this email exists
        result = await db.execute(select(User).filter(User.email == member_data.email))
        any_user = result.scalar_one_or_none()
        if any_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists in another team"
            )
        
        # Get tenant info
        result = await db.execute(select(Tenant).filter(Tenant.id == current_user.tenant_id))
        tenant = result.scalar_one_or_none()
        tenant_name = tenant.name if tenant else "Organization"
        
        # Generate invitation link
        invitation_link = f"{settings.FRONTEND_URL}/auth/sign-up?tenant={current_user.tenant_id}&role={member_data.role}"
        
        # Send invitation email
        logger.info(f"Sending invitation email to: {member_data.email}")
        logger.info(f"Inviter: {current_user.full_name or current_user.email}")
        email_sent = await email_service.send_user_invitation(
            email=member_data.email,
            inviter_name=current_user.full_name or current_user.email,
            tenant_name=tenant_name,
            invitation_link=invitation_link,
            role="admin" if member_data.role == "admin" else "team member"
        )
        
        if not email_sent:
            logger.warning(f"Failed to send invitation email to {member_data.email}")
        
        logger.info(f"Team member invitation sent to {member_data.email} by {current_user.email}")
        
        return {
            "message": f"Invitation sent to {member_data.email}",
            "email": member_data.email,
            "role": member_data.role,
            "email_sent": email_sent
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inviting team member: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send invitation"
        )

@router.delete("/members/{member_id}")
async def remove_team_member(
    member_id: UUID,
    current_user: User = Depends(get_current_tenant_admin_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Remove a team member (admin only)
    """
    try:
        # Find member
        result = await db.execute(
            select(User).filter(
                and_(
                    User.id == member_id,
                    User.tenant_id == current_user.tenant_id
                )
            )
        )
        member = result.scalar_one_or_none()
        
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found"
            )
        
        # Prevent self-removal
        if member.id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove yourself from the team"
            )
        
        # Check if this is the last admin
        if not member.is_team_member:  # If member is an admin
            result = await db.execute(
                select(func.count(User.id)).filter(
                    and_(
                        User.tenant_id == current_user.tenant_id,
                        User.is_team_member == False,
                        User.is_active == True
                    )
                )
            )
            admin_count = result.scalar() or 0
            
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot remove the last admin"
                )
        
        # Deactivate user
        member.is_active = False
        await db.commit()
        
        logger.info(f"Team member {member.email} removed by {current_user.email}")
        
        return {"message": "Team member removed successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing team member: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove team member"
        )

# ================================
# TEAM INVITATION ENDPOINTS
# ================================

@router.post("/invitations", response_model=TeamInvitationResponse)
async def create_team_invitation(
    invitation: TeamInvitationCreate,
    current_user: User = Depends(get_current_tenant_admin_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Create a new team invitation with QR code (admin only)
    """
    try:
        # Generate unique invitation code
        invitation_code = secrets.token_urlsafe(32)
        
        # Create invitation
        db_invitation = TeamInvitation(
            tenant_id=current_user.tenant_id,
            invited_by=current_user.id,
            invitation_code=invitation_code,
            email=invitation.email,
            expires_at=datetime.utcnow() + timedelta(days=invitation.expires_in_days or 7)
        )
        
        db.add(db_invitation)
        await db.commit()
        await db.refresh(db_invitation)
        
        # Generate invitation URL
        invitation_url = f"{settings.FRONTEND_URL}/join-team/{invitation_code}"
        
        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(invitation_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        logger.info(f"Created team invitation for tenant {current_user.tenant_id}")
        
        # Get tenant name
        result = await db.execute(select(Tenant).filter(Tenant.id == current_user.tenant_id))
        tenant = result.scalar_one_or_none()
        
        # Send email if specified
        if invitation.email:
            await email_service.send_team_invitation(
                email=invitation.email,
                team_name=tenant.name if tenant else "Team",
                inviter_name=current_user.full_name or current_user.email,
                invitation_link=invitation_url,
                expires_at=db_invitation.expires_at
            )
        
        return TeamInvitationResponse(
            id=db_invitation.id,
            invitation_code=invitation_code,
            invitation_url=invitation_url,
            qr_code=f"data:image/png;base64,{qr_code_base64}",
            email=db_invitation.email,
            expires_at=db_invitation.expires_at,
            created_at=db_invitation.created_at,
            tenant_name=tenant.name if tenant else "Organization",
            used=db_invitation.used,
            used_at=db_invitation.used_at
        )
        
    except Exception as e:
        logger.error(f"Error creating team invitation: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create invitation"
        )

@router.get("/invitations", response_model=List[TeamInvitationResponse])
async def get_team_invitations(
    current_user: User = Depends(get_current_tenant_admin_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get all invitations for the current team (admin only)
    """
    try:
        result = await db.execute(
            select(TeamInvitation).filter(
                TeamInvitation.tenant_id == current_user.tenant_id
            ).order_by(TeamInvitation.created_at.desc())
        )
        invitations = result.scalars().all()
        
        # Get tenant name
        result = await db.execute(select(Tenant).filter(Tenant.id == current_user.tenant_id))
        tenant = result.scalar_one_or_none()
        tenant_name = tenant.name if tenant else "Organization"
        
        result = []
        for invitation in invitations:
            # Regenerate QR code for display
            invitation_url = f"{settings.FRONTEND_URL}/join-team/{invitation.invitation_code}"
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(invitation_url)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            result.append(TeamInvitationResponse(
                id=invitation.id,
                invitation_code=invitation.invitation_code,
                invitation_url=invitation_url,
                qr_code=f"data:image/png;base64,{qr_code_base64}",
                email=invitation.email,
                expires_at=invitation.expires_at,
                created_at=invitation.created_at,
                tenant_name=tenant_name,
                used=invitation.used,
                used_at=invitation.used_at
            ))
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting team invitations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get invitations"
        )

@router.get("/invitations/{invitation_code}/info")
async def get_invitation_info(
    invitation_code: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get invitation information (public endpoint)
    """
    try:
        # Find invitation
        result = await db.execute(
            select(TeamInvitation).filter(
                TeamInvitation.invitation_code == invitation_code
            )
        )
        invitation = result.scalar_one_or_none()
        
        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid invitation code"
            )
        
        # Get tenant info
        result = await db.execute(select(Tenant).filter(Tenant.id == invitation.tenant_id))
        tenant = result.scalar_one_or_none()
        
        return {
            "tenant_id": invitation.tenant_id,
            "tenant_name": tenant.name if tenant else "Organization",
            "expires_at": invitation.expires_at.isoformat(),
            "used": invitation.used,
            "email": invitation.email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting invitation info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get invitation info"
        )

@router.post("/invitations/{invitation_code}/accept")
async def accept_team_invitation(
    invitation_code: str,
    accept_data: TeamInvitationAccept,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Accept a team invitation (public endpoint)
    """
    try:
        # Find invitation
        result = await db.execute(
            select(TeamInvitation).filter(
                TeamInvitation.invitation_code == invitation_code
            )
        )
        invitation = result.scalar_one_or_none()
        
        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid invitation code"
            )
        
        # Check if invitation is expired
        if invitation.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation has expired"
            )
        
        # Check if invitation is already used
        if invitation.used:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation has already been used"
            )
        
        # Check if email matches (if specified)
        if invitation.email and invitation.email != accept_data.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This invitation is for a different email address"
            )
        
        # Check if user already exists
        result = await db.execute(select(User).filter(User.email == accept_data.email))
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # Note: In a real implementation, you would integrate with Clerk here
        # to create the user account. For now, we'll create a placeholder.
        
        # Mark invitation as used
        invitation.used = True
        invitation.used_at = datetime.utcnow()
        
        await db.commit()
        
        # Get tenant name
        result = await db.execute(select(Tenant).filter(Tenant.id == invitation.tenant_id))
        tenant = result.scalar_one_or_none()
        
        logger.info(f"Team invitation {invitation_code} accepted by {accept_data.email}")
        
        return {
            "message": "Invitation accepted. Please complete registration.",
            "tenant_id": invitation.tenant_id,
            "tenant_name": tenant.name if tenant else "Organization",
            "redirect_url": f"{settings.FRONTEND_URL}/auth/sign-up?invitation={invitation_code}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting team invitation: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to accept invitation"
        )