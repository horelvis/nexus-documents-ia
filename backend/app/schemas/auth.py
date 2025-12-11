# backend/app/schemas/auth.py
"""
Auth schemas.

Schemas for Clerk + Stripe authentication flow.
"""
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class TokenPayload(BaseModel):
    """JWT token payload structure (from Clerk)."""
    sub: str = Field(..., description="User ID (clerk_user_id)")
    iss: str = Field(..., description="Issuer (Clerk URL)")
    exp: int = Field(..., description="Expiration timestamp")


class SubscriptionInfo(BaseModel):
    """Subscription information from Stripe."""
    plan: str = Field(..., description="Plan type: trial, basic, pro, enterprise")
    status: str = Field(..., description="Status: active, trialing, past_due, canceled")
    can_use_agents: bool = Field(default=False, description="Whether user can use AI agents")
    can_use_advanced_features: bool = Field(default=False, description="Whether user can use advanced features")
    limits: Dict[str, int] = Field(default_factory=dict, description="Plan limits (documents, storage_mb, etc)")
    needs_upgrade: bool = Field(default=False, description="True if trial expired without paid plan")
    trial_days_remaining: Optional[int] = Field(None, description="Days remaining in trial")
    current_period_end: Optional[str] = Field(None, description="ISO8601 end of current billing period")
    subscription_id: Optional[str] = Field(None, description="Stripe subscription ID")
    cancel_at_period_end: bool = Field(default=False, description="Whether subscription cancels at period end")


class UserPermissions(BaseModel):
    """User permissions based on subscription and roles."""
    is_admin: bool = Field(default=False, description="Whether user is tenant admin")
    is_team_member: bool = Field(default=False, description="Whether user is a team member (not owner)")
    can_upload_documents: bool = Field(default=True, description="Whether user can upload documents")
    can_use_agents: bool = Field(default=False, description="Whether user can use AI agents")
    can_invite_members: bool = Field(default=False, description="Whether user can invite team members")
    can_access_api: bool = Field(default=False, description="Whether user has API access")
    can_export: bool = Field(default=False, description="Whether user can export documents")


class LoginResponse(BaseModel):
    """Response from POST /auth/login."""
    user: Dict[str, Any] = Field(..., description="User data")
    subscription: SubscriptionInfo = Field(..., description="Subscription details from Stripe")
    permissions: UserPermissions = Field(..., description="User permissions based on plan")
    tenant_id: str = Field(..., description="User's tenant ID")


class LogoutResponse(BaseModel):
    """Response from POST /auth/logout."""
    success: bool = Field(..., description="Whether logout was successful")
    message: str = Field(..., description="Logout message")
