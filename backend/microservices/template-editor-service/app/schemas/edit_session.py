"""
Pydantic schemas for Edit Sessions API
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID


class EditSessionCreate(BaseModel):
    """Schema for creating new edit session"""
    template_id: str = Field(..., description="ID of the template to edit")
    template_name: str = Field(..., description="Name of the template")
    template_content: str = Field(..., description="Current template content (HTML)")
    user_id: str = Field(..., description="ID of the user who will edit")
    user_email: str = Field(..., description="Email of the user (for Google Docs permissions)")
    tenant_id: str = Field(..., description="Tenant ID for multi-tenant isolation")
    
    @validator('user_email')
    def validate_email(cls, v):
        """Basic email validation"""
        if '@' not in v:
            raise ValueError('Invalid email format')
        return v.lower()


class EditSessionResponse(BaseModel):
    """Schema for edit session response"""
    id: UUID = Field(..., description="Session ID")
    template_id: UUID = Field(..., description="Template ID")
    template_name: str = Field(..., description="Template name")
    user_id: str = Field(..., description="User ID")
    user_email: str = Field(..., description="User email")
    tenant_id: str = Field(..., description="Tenant ID")
    
    # Google Docs info
    google_doc_id: str = Field(..., description="Google Document ID")
    google_doc_url: str = Field(..., description="Google Doc view URL")
    google_doc_edit_url: str = Field(..., description="Google Doc edit URL")
    
    # Session timing
    created_at: datetime = Field(..., description="Session creation time")
    expires_at: datetime = Field(..., description="Session expiration time")
    last_activity: datetime = Field(..., description="Last activity timestamp")
    completed_at: Optional[datetime] = Field(None, description="Session completion time")
    
    # Status
    status: str = Field(..., description="Session status")
    changes_detected: Optional[bool] = Field(None, description="Whether changes were detected")
    
    # Content tracking
    original_content_hash: Optional[str] = Field(None, description="Original content hash")
    final_content_hash: Optional[str] = Field(None, description="Final content hash")
    
    # Error info
    error_message: Optional[str] = Field(None, description="Error message if failed")
    
    # Cleanup status
    cleanup_completed: Optional[bool] = Field(None, description="Whether cleanup completed successfully")
    
    class Config:
        from_attributes = True  # For SQLAlchemy ORM compatibility
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            UUID: lambda v: str(v) if v else None
        }


class EditSessionFinish(BaseModel):
    """Schema for finishing edit session"""
    user_id: str = Field(..., description="User ID (for authorization)")
    force_sync: bool = Field(False, description="Force sync even if no changes detected")


class EditSessionExtend(BaseModel):
    """Schema for extending edit session"""
    user_id: str = Field(..., description="User ID (for authorization)")
    hours: int = Field(1, ge=1, le=24, description="Hours to extend (1-24)")


class EditSessionStats(BaseModel):
    """Schema for edit session statistics"""
    total_sessions: int = Field(0, description="Total number of sessions")
    active_sessions: int = Field(0, description="Number of active sessions")
    completed_sessions: int = Field(0, description="Number of completed sessions")
    expired_sessions: int = Field(0, description="Number of expired sessions")
    cleanup_errors: int = Field(0, description="Number of cleanup errors")
    
    # Optional detailed stats
    sessions_by_status: Optional[Dict[str, int]] = Field(None, description="Sessions grouped by status")
    avg_session_duration_minutes: Optional[float] = Field(None, description="Average session duration")
    google_docs_deleted: Optional[int] = Field(None, description="Number of Google Docs deleted")
    successfully_cleaned: Optional[int] = Field(None, description="Number of successfully cleaned sessions")


class EditSessionListResponse(BaseModel):
    """Schema for listing edit sessions"""
    sessions: list[EditSessionResponse] = Field(..., description="List of edit sessions")
    total_count: int = Field(..., description="Total number of sessions")
    active_count: int = Field(..., description="Number of active sessions")


class EditSessionError(BaseModel):
    """Schema for edit session errors"""
    session_id: Optional[str] = Field(None, description="Session ID if available")
    error_type: str = Field(..., description="Type of error")
    error_message: str = Field(..., description="Error message")
    occurred_at: datetime = Field(default_factory=datetime.utcnow, description="When error occurred")
    user_id: Optional[str] = Field(None, description="User ID if available")
    template_id: Optional[str] = Field(None, description="Template ID if available")


class EditSessionActivity(BaseModel):
    """Schema for tracking edit session activity"""
    session_id: str = Field(..., description="Session ID")
    activity_type: str = Field(..., description="Type of activity")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Activity timestamp")
    user_id: str = Field(..., description="User ID")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional activity details")


class TemplateEditRequest(BaseModel):
    """Schema for requesting template edit (from main API)"""
    template_id: str = Field(..., description="Template ID to edit")
    user_id: str = Field(..., description="User requesting edit")
    user_email: str = Field(..., description="User email")
    tenant_id: str = Field(..., description="Tenant ID")
    
    # Optional context
    edit_reason: Optional[str] = Field(None, description="Reason for editing")
    expected_duration_hours: Optional[int] = Field(2, ge=1, le=24, description="Expected editing duration")


class TemplateEditResponse(BaseModel):
    """Schema for template edit response (to main API)"""
    edit_session: EditSessionResponse = Field(..., description="Created edit session")
    instructions: str = Field(..., description="Instructions for user")
    edit_url: str = Field(..., description="URL to open for editing")
    expires_in_hours: float = Field(..., description="Hours until session expires")