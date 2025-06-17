"""
Team management schemas
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID
import uuid

from pydantic import BaseModel, EmailStr, Field


class TeamBase(BaseModel):
    """Base schema for teams"""
    name: str = Field(..., min_length=1, max_length=255, example="Engineering Team")
    description: Optional[str] = Field(None, max_length=1000, example="Team responsible for product development")


class TeamCreate(TeamBase):
    """Schema for creating a team"""
    pass


class TeamUpdate(BaseModel):
    """Schema for updating a team"""
    name: Optional[str] = Field(None, min_length=1, max_length=255, example="Updated Team Name")
    description: Optional[str] = Field(None, max_length=1000, example="Updated description")


class Team(TeamBase):
    """Complete team schema"""
    id: UUID = Field(..., example=uuid.uuid4())
    tenant_id: UUID = Field(..., example=uuid.uuid4())
    created_by: UUID = Field(..., example=uuid.uuid4())
    created_at: datetime = Field(..., example=datetime.now())
    updated_at: datetime = Field(..., example=datetime.now())
    members_count: int = Field(0, example=5)
    
    class Config:
        from_attributes = True


class TeamWithMembers(Team):
    """Team with members list"""
    members: List['TeamMemberResponse'] = []


class TeamListResponse(BaseModel):
    """Response for team list endpoint"""
    teams: List[Team]
    total: int
    skip: int
    limit: int


class TeamMemberAdd(BaseModel):
    """Schema for adding a member to a team"""
    user_id: UUID = Field(..., example=uuid.uuid4())
    role: str = Field(default="member", pattern="^(leader|member)$", example="member")


class TeamMemberRoleUpdate(BaseModel):
    """Schema for updating team member role"""
    role: str = Field(..., pattern="^(leader|member)$", example="leader")


class TeamInvitationCreate(BaseModel):
    """Schema for creating a team invitation"""
    email: Optional[EmailStr] = Field(None, description="Optional email to restrict invitation to specific user")
    expires_in_days: Optional[int] = Field(7, ge=1, le=30, description="Days until invitation expires (1-30)")


class TeamInvitationResponse(BaseModel):
    """Schema for team invitation response"""
    id: UUID
    invitation_code: str
    invitation_url: str
    qr_code: str = Field(..., description="Base64 encoded QR code image")
    email: Optional[str]
    expires_at: datetime
    created_at: datetime
    tenant_name: str
    used: bool = False
    used_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class TeamInvitationAccept(BaseModel):
    """Schema for accepting a team invitation"""
    email: EmailStr = Field(..., description="Email address of the user accepting the invitation")
    full_name: str = Field(..., min_length=1, max_length=255, description="Full name of the user")


class TeamMemberResponse(BaseModel):
    """Schema for team member response"""
    id: UUID
    email: str
    full_name: Optional[str]
    is_team_member: bool
    is_active: bool
    created_at: datetime
    role: str = Field(..., description="Either 'Admin' or 'Team Member'")
    subscription_plan: str = Field(..., description="The subscription plan (inherited from admin for team members)")
    invited_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class TeamMemberRemove(BaseModel):
    """Schema for removing a team member"""
    reason: Optional[str] = Field(None, max_length=500, description="Optional reason for removal")


class TeamInvitationListResponse(BaseModel):
    """Schema for listing team invitations"""
    invitations: List[TeamInvitationResponse]
    total: int
    pending: int
    expired: int