"""
API endpoints for team management
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
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_

from app.api.deps import get_db, get_current_active_user, get_current_admin_user
from app.db.models import User, Team, TeamMember, Document, Tenant, TeamInvitation
from app.schemas.team import (
    TeamCreate,
    TeamUpdate,
    Team as TeamSchema,
    TeamWithMembers,
    TeamListResponse,
    TeamMemberAdd,
    TeamMemberRoleUpdate,
    TeamMemberResponse,
    TeamInvitationCreate,
    TeamInvitationResponse,
    TeamInvitationAccept
)
from app.core.config import settings

import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# ===========================
# TEAM MANAGEMENT ENDPOINTS
# ===========================

@router.get("/", response_model=TeamListResponse)
async def list_teams(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None
):
    """
    List all teams in the current tenant
    """
    try:
        # Base query for teams in the same tenant
        query = select(Team).where(Team.tenant_id == current_user.tenant_id)
        
        # Apply search filter if provided
        if search:
            search_filter = f"%{search}%"
            query = query.where(
                or_(
                    Team.name.ilike(search_filter),
                    Team.description.ilike(search_filter)
                )
            )
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # Execute query with pagination
        result = await db.execute(query.offset(skip).limit(limit).order_by(Team.created_at.desc()))
        teams = result.scalars().all()
        
        # Get member count for each team
        teams_with_count = []
        for team in teams:
            member_count = await db.execute(
                select(func.count(TeamMember.id)).where(TeamMember.team_id == team.id)
            )
            team_dict = {
                "id": team.id,
                "name": team.name,
                "description": team.description,
                "tenant_id": team.tenant_id,
                "created_by": team.created_by,
                "created_at": team.created_at,
                "updated_at": team.updated_at,
                "members_count": member_count.scalar() or 0
            }
            teams_with_count.append(team_dict)
        
        return TeamListResponse(
            teams=teams_with_count,
            total=total,
            skip=skip,
            limit=limit
        )
        
    except Exception as e:
        logger.error(f"Error listing teams: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list teams"
        )

@router.post("/", response_model=TeamSchema)
async def create_team(
    team_data: TeamCreate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new team (admin only)
    """
    try:
        # Check if team name already exists in tenant
        existing_team = await db.execute(
            select(Team).where(
                and_(
                    Team.name == team_data.name,
                    Team.tenant_id == current_user.tenant_id
                )
            )
        )
        if existing_team.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Team with this name already exists"
            )
        
        # Create team
        team = Team(
            name=team_data.name,
            description=team_data.description,
            tenant_id=current_user.tenant_id,
            created_by=current_user.id
        )
        db.add(team)
        await db.commit()
        await db.refresh(team)
        
        # Add creator as team leader
        team_member = TeamMember(
            team_id=team.id,
            user_id=current_user.id,
            role="leader"
        )
        db.add(team_member)
        await db.commit()
        
        logger.info(f"Team {team.name} created by {current_user.email}")
        
        return TeamSchema(
            id=team.id,
            name=team.name,
            description=team.description,
            tenant_id=team.tenant_id,
            created_by=team.created_by,
            created_at=team.created_at,
            updated_at=team.updated_at,
            members_count=1
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating team: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create team"
        )

@router.get("/{team_id}", response_model=TeamWithMembers)
async def get_team(
    team_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get team details with members
    """
    try:
        # Get team
        result = await db.execute(
            select(Team).where(
                and_(
                    Team.id == team_id,
                    Team.tenant_id == current_user.tenant_id
                )
            )
        )
        team = result.scalar_one_or_none()
        
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )
        
        # Get team members
        members_result = await db.execute(
            select(TeamMember, User).join(User).where(TeamMember.team_id == team_id)
        )
        members_data = members_result.all()
        
        members = []
        for member, user in members_data:
            members.append({
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "name": user.full_name,
                    "avatar": None  # Add avatar URL if available
                },
                "role": member.role,
                "joined_at": member.joined_at
            })
        
        return TeamWithMembers(
            id=team.id,
            name=team.name,
            description=team.description,
            tenant_id=team.tenant_id,
            created_by=team.created_by,
            created_at=team.created_at,
            updated_at=team.updated_at,
            members_count=len(members),
            members=members
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting team: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get team details"
        )

@router.put("/{team_id}", response_model=TeamSchema)
async def update_team(
    team_id: str,
    team_update: TeamUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update team details (admin only)
    """
    try:
        # Get team
        result = await db.execute(
            select(Team).where(
                and_(
                    Team.id == team_id,
                    Team.tenant_id == current_user.tenant_id
                )
            )
        )
        team = result.scalar_one_or_none()
        
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )
        
        # Check if new name already exists
        if team_update.name and team_update.name != team.name:
            existing_team = await db.execute(
                select(Team).where(
                    and_(
                        Team.name == team_update.name,
                        Team.tenant_id == current_user.tenant_id,
                        Team.id != team_id
                    )
                )
            )
            if existing_team.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Team with this name already exists"
                )
        
        # Update fields
        if team_update.name is not None:
            team.name = team_update.name
        if team_update.description is not None:
            team.description = team_update.description
        
        await db.commit()
        await db.refresh(team)
        
        # Get member count
        member_count = await db.execute(
            select(func.count(TeamMember.id)).where(TeamMember.team_id == team.id)
        )
        
        logger.info(f"Team {team.name} updated by {current_user.email}")
        
        return TeamSchema(
            id=team.id,
            name=team.name,
            description=team.description,
            tenant_id=team.tenant_id,
            created_by=team.created_by,
            created_at=team.created_at,
            updated_at=team.updated_at,
            members_count=member_count.scalar() or 0
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

@router.delete("/{team_id}")
async def delete_team(
    team_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a team (admin only)
    """
    try:
        # Get team
        result = await db.execute(
            select(Team).where(
                and_(
                    Team.id == team_id,
                    Team.tenant_id == current_user.tenant_id
                )
            )
        )
        team = result.scalar_one_or_none()
        
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )
        
        # Delete team (cascade will delete members)
        await db.delete(team)
        await db.commit()
        
        logger.info(f"Team {team.name} deleted by {current_user.email}")
        
        return {"message": "Team deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting team: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete team"
        )

@router.post("/{team_id}/members", response_model=dict)
async def add_team_member(
    team_id: str,
    member_data: TeamMemberAdd,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Add a member to a team (admin only)
    """
    try:
        # Verify team exists and belongs to tenant
        team_result = await db.execute(
            select(Team).where(
                and_(
                    Team.id == team_id,
                    Team.tenant_id == current_user.tenant_id
                )
            )
        )
        team = team_result.scalar_one_or_none()
        
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )
        
        # Verify user exists and belongs to same tenant
        user_result = await db.execute(
            select(User).where(
                and_(
                    User.id == member_data.user_id,
                    User.tenant_id == current_user.tenant_id
                )
            )
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check if user is already a member
        existing_member = await db.execute(
            select(TeamMember).where(
                and_(
                    TeamMember.team_id == team_id,
                    TeamMember.user_id == member_data.user_id
                )
            )
        )
        if existing_member.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of this team"
            )
        
        # Add member
        team_member = TeamMember(
            team_id=team_id,
            user_id=member_data.user_id,
            role=member_data.role
        )
        db.add(team_member)
        await db.commit()
        
        logger.info(f"User {user.email} added to team {team.name} by {current_user.email}")
        
        return {
            "message": "Member added successfully",
            "user_id": str(member_data.user_id),
            "team_id": team_id,
            "role": member_data.role
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding team member: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add team member"
        )

@router.put("/{team_id}/members/{user_id}/role", response_model=dict)
async def update_member_role(
    team_id: str,
    user_id: str,
    role_update: TeamMemberRoleUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update team member role (admin only)
    """
    try:
        # Get team member
        result = await db.execute(
            select(TeamMember).where(
                and_(
                    TeamMember.team_id == team_id,
                    TeamMember.user_id == user_id
                )
            )
        )
        member = result.scalar_one_or_none()
        
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team member not found"
            )
        
        # Verify team belongs to tenant
        team_result = await db.execute(
            select(Team).where(
                and_(
                    Team.id == team_id,
                    Team.tenant_id == current_user.tenant_id
                )
            )
        )
        if not team_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )
        
        # Update role
        member.role = role_update.role
        await db.commit()
        
        logger.info(f"Team member role updated for user {user_id} in team {team_id}")
        
        return {
            "message": "Member role updated successfully",
            "user_id": user_id,
            "team_id": team_id,
            "new_role": role_update.role
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating member role: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update member role"
        )

@router.delete("/{team_id}/members/{user_id}")
async def remove_team_member(
    team_id: str,
    user_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Remove a member from a team (admin only)
    """
    try:
        # Get team member
        result = await db.execute(
            select(TeamMember).where(
                and_(
                    TeamMember.team_id == team_id,
                    TeamMember.user_id == user_id
                )
            )
        )
        member = result.scalar_one_or_none()
        
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team member not found"
            )
        
        # Verify team belongs to tenant
        team_result = await db.execute(
            select(Team).where(
                and_(
                    Team.id == team_id,
                    Team.tenant_id == current_user.tenant_id
                )
            )
        )
        team = team_result.scalar_one_or_none()
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )
        
        # Don't allow removing the last leader
        if member.role == "leader":
            leader_count = await db.execute(
                select(func.count(TeamMember.id)).where(
                    and_(
                        TeamMember.team_id == team_id,
                        TeamMember.role == "leader"
                    )
                )
            )
            if leader_count.scalar() <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot remove the last team leader"
                )
        
        # Remove member
        await db.delete(member)
        await db.commit()
        
        logger.info(f"User {user_id} removed from team {team.name} by {current_user.email}")
        
        return {"message": "Member removed successfully"}
        
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
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Create a new team invitation with QR code.
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
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    
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

@router.get("/invitations", response_model=List[TeamInvitationResponse])
async def get_team_invitations(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
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
    
    result = await db.execute(
        select(TeamInvitation, Tenant)
        .join(Tenant)
        .where(TeamInvitation.tenant_id == current_user.tenant_id)
        .order_by(TeamInvitation.created_at.desc())
    )
    
    invitations_data = result.all()
    
    invitations = []
    for invitation, tenant in invitations_data:
        # Regenerate QR code for display
        invitation_url = f"{settings.FRONTEND_URL}/join-team/{invitation.invitation_code}"
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(invitation_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        invitations.append(TeamInvitationResponse(
            id=invitation.id,
            invitation_code=invitation.invitation_code,
            invitation_url=invitation_url,
            qr_code=f"data:image/png;base64,{qr_code_base64}",
            email=invitation.email,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
            tenant_name=tenant.name,
            used=invitation.used,
            used_at=invitation.used_at
        ))
    
    return invitations

@router.post("/invitations/{invitation_code}/accept")
async def accept_team_invitation(
    invitation_code: str,
    accept_data: TeamInvitationAccept,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Accept a team invitation.
    This creates a new user account as a team member.
    """
    # Find invitation
    result = await db.execute(
        select(TeamInvitation).where(
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
    existing_user_result = await db.execute(
        select(User).where(User.email == accept_data.email)
    )
    existing_user = existing_user_result.scalar_one_or_none()
    
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
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == invitation.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    
    logger.info(f"Team invitation {invitation_code} accepted by {accept_data.email}")
    
    return {
        "message": "Invitation accepted. Please complete registration.",
        "tenant_id": invitation.tenant_id,
        "tenant_name": tenant.name if tenant else "Organization",
        "redirect_url": f"{settings.FRONTEND_URL}/auth/sign-up?invitation={invitation_code}"
    }

# =====================================
# LEGACY TEAM MEMBERS ENDPOINTS
# =====================================

@router.get("/members", response_model=List[TeamMemberResponse])
async def get_all_tenant_members(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Get all members for the current tenant (legacy endpoint).
    This shows all users in the tenant, not specific to a team.
    """
    result = await db.execute(
        select(User).where(
            and_(
                User.tenant_id == current_user.tenant_id,
                User.is_active == True
            )
        ).order_by(User.created_at.desc())
    )
    members = result.scalars().all()
    
    # Get tenant's subscription plan
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    
    # The subscription plan of the admin user (first non-team member)
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

@router.delete("/members/{member_id}")
async def remove_tenant_member(
    member_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Remove a tenant member (legacy endpoint).
    Only admins can remove team members.
    """
    if current_user.is_team_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team members cannot remove other members"
        )
    
    # Find member
    result = await db.execute(
        select(User).where(
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
    
    if not member.is_team_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove admin users"
        )
    
    # Deactivate user
    member.is_active = False
    await db.commit()
    
    logger.info(f"Team member {member_id} removed from tenant {current_user.tenant_id}")
    
    return {"message": "Team member removed successfully"}