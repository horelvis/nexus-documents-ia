"""
Team management endpoints
"""
import secrets
import qrcode
import io
import base64
from datetime import datetime, timedelta
from typing import List, Optional, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.api.dependencies import get_db, get_current_active_user
from app.db.models import User, TeamInvitation, Tenant
from app.schemas.team import (
    TeamInvitationCreate,
    TeamInvitationResponse,
    TeamMemberResponse,
    TeamInvitationAccept
)
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/invitations", response_model=TeamInvitationResponse)
async def create_team_invitation(
    invitation: TeamInvitationCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Create a new team invitation.
    Only tenant admins (non-team members) can create invitations.
    """
    # Check if user is admin (not a team member themselves)
    if current_user.is_team_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team members cannot create invitations"
        )
    
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
    db.commit()
    db.refresh(db_invitation)
    
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
    
    return {
        "id": db_invitation.id,
        "invitation_code": invitation_code,
        "invitation_url": invitation_url,
        "qr_code": f"data:image/png;base64,{qr_code_base64}",
        "email": db_invitation.email,
        "expires_at": db_invitation.expires_at,
        "created_at": db_invitation.created_at,
        "tenant_name": db_invitation.tenant.name
    }


@router.get("/invitations", response_model=List[TeamInvitationResponse])
async def get_team_invitations(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get all invitations for the current tenant.
    Only admins can see invitations.
    """
    if current_user.is_team_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team members cannot view invitations"
        )
    
    invitations = db.query(TeamInvitation).filter(
        TeamInvitation.tenant_id == current_user.tenant_id
    ).order_by(TeamInvitation.created_at.desc()).all()
    
    return invitations


@router.post("/invitations/{invitation_code}/accept")
async def accept_team_invitation(
    invitation_code: str,
    accept_data: TeamInvitationAccept,
    db: Session = Depends(get_db)
) -> Any:
    """
    Accept a team invitation.
    This creates a new user account as a team member.
    """
    # Find invitation
    invitation = db.query(TeamInvitation).filter(
        TeamInvitation.invitation_code == invitation_code
    ).first()
    
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
    existing_user = db.query(User).filter(
        User.email == accept_data.email
    ).first()
    
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
    
    db.commit()
    
    logger.info(f"Team invitation {invitation_code} accepted by {accept_data.email}")
    
    return {
        "message": "Invitation accepted. Please complete registration.",
        "tenant_id": invitation.tenant_id,
        "tenant_name": invitation.tenant.name,
        "redirect_url": f"{settings.FRONTEND_URL}/auth/sign-up?invitation={invitation_code}"
    }


@router.get("/members", response_model=List[TeamMemberResponse])
async def get_team_members(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get all team members for the current tenant.
    """
    members = db.query(User).filter(
        User.tenant_id == current_user.tenant_id,
        User.is_active == True
    ).order_by(User.created_at.desc()).all()
    
    # Get tenant's subscription plan
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    
    # The subscription plan of the admin user (first non-team member)
    admin_user = next((u for u in members if not u.is_team_member), None)
    tenant_plan = admin_user.subscription_plan if admin_user else 'free'
    
    return [{
        "id": member.id,
        "email": member.email,
        "full_name": member.full_name,
        "is_team_member": member.is_team_member,
        "is_active": member.is_active,
        "created_at": member.created_at,
        "role": "Team Member" if member.is_team_member else "Admin",
        "subscription_plan": tenant_plan if member.is_team_member else member.subscription_plan
    } for member in members]


@router.delete("/members/{member_id}")
async def remove_team_member(
    member_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Remove a team member.
    Only admins can remove team members.
    """
    if current_user.is_team_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team members cannot remove other members"
        )
    
    # Find member
    member = db.query(User).filter(
        User.id == member_id,
        User.tenant_id == current_user.tenant_id
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )
    
    if not member.is_team_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove admin users"
        )
    
    # Deactivate user
    member.is_active = False
    db.commit()
    
    logger.info(f"Team member {member_id} removed from tenant {current_user.tenant_id}")
    
    return {"message": "Team member removed successfully"}