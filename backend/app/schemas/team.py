"""
Schemas for team management (tenant-based teams)
"""
from typing import List, Optional, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

from app.core.enums import TeamRole

# Team schemas (Tenant-based - one team per tenant)
class TeamBase(BaseModel):
    """Base schema for team (tenant)"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)

class TeamUpdate(BaseModel):
    """Schema for updating team (tenant) info"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)

class TeamResponse(BaseModel):
    """Response schema for team (tenant) info"""
    id: UUID
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    members_count: int = 0
    storage_quota: int
    is_active: bool
    
    class Config:
        from_attributes = True

class TeamWithMembers(TeamResponse):
    """Team (tenant) response with member list"""
    members: List['TeamMemberResponse']
    skip: int
    limit: int


# Team Member schemas (Users in a tenant)
class TeamMemberAdd(BaseModel):
    """Schema for inviting a new team member"""
    email: EmailStr = Field(..., description="Email address to invite")
    role: TeamRole = Field(default=TeamRole.MEMBER, description="Role: admin or member")


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