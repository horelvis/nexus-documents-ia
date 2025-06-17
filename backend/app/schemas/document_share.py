from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field, validator
from uuid import UUID


class DocumentShareBase(BaseModel):
    share_type: str = Field(default="view", description="Type of share: view, download, edit")
    expires_at: Optional[datetime] = Field(None, description="Expiration date for the share link")
    max_access_count: Optional[int] = Field(None, description="Maximum number of times the link can be accessed")
    password: Optional[str] = Field(None, description="Optional password for accessing the share")
    recipient_email: Optional[EmailStr] = Field(None, description="Email of the recipient")
    recipient_name: Optional[str] = Field(None, description="Name of the recipient")
    share_message: Optional[str] = Field(None, description="Message to include with the share")
    permissions: Optional[Dict[str, Any]] = Field(None, description="Additional permissions")
    
    @validator('share_type')
    def validate_share_type(cls, v):
        allowed_types = ['view', 'download', 'edit']
        if v not in allowed_types:
            raise ValueError(f'Share type must be one of {allowed_types}')
        return v
    
    @validator('max_access_count')
    def validate_max_access_count(cls, v):
        if v is not None and v < 1:
            raise ValueError('Max access count must be at least 1')
        return v


class DocumentShareCreate(DocumentShareBase):
    document_id: UUID = Field(..., description="ID of the document to share")
    recipients: Optional[List[EmailStr]] = Field(None, description="List of recipient emails for bulk sharing")


class DocumentShareUpdate(BaseModel):
    expires_at: Optional[datetime] = None
    max_access_count: Optional[int] = None
    is_active: Optional[bool] = None
    permissions: Optional[Dict[str, Any]] = None


class DocumentShareResponse(DocumentShareBase):
    id: UUID
    document_id: UUID
    tenant_id: UUID
    created_by: UUID
    share_token: str
    share_url: str
    current_access_count: int = 0
    is_active: bool = True
    first_accessed_at: Optional[datetime] = None
    last_accessed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[UUID] = None
    
    # Document info
    document_title: Optional[str] = None
    document_filename: Optional[str] = None
    
    class Config:
        from_attributes = True


class DocumentShareListResponse(BaseModel):
    shares: List[DocumentShareResponse]
    total: int
    page: int
    per_page: int


class DocumentShareAccessRequest(BaseModel):
    password: Optional[str] = Field(None, description="Password if the share is password protected")


class DocumentShareAccessResponse(BaseModel):
    success: bool
    document_url: Optional[str] = None
    error: Optional[str] = None
    requires_password: bool = False
    document_info: Optional[Dict[str, Any]] = None


class ShareAccessLogResponse(BaseModel):
    id: UUID
    share_id: UUID
    document_id: UUID
    accessed_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    action: str = "view"
    success: bool = True
    error_message: Optional[str] = None
    country_code: Optional[str] = None
    city: Optional[str] = None
    device_type: Optional[str] = None
    browser: Optional[str] = None
    os: Optional[str] = None
    user_id: Optional[UUID] = None
    
    class Config:
        from_attributes = True


class ShareAccessLogListResponse(BaseModel):
    logs: List[ShareAccessLogResponse]
    total: int
    page: int
    per_page: int


class DocumentShareRecipientResponse(BaseModel):
    id: UUID
    share_id: UUID
    email: EmailStr
    name: Optional[str] = None
    verified_at: Optional[datetime] = None
    notified_at: Optional[datetime] = None
    first_accessed_at: Optional[datetime] = None
    last_accessed_at: Optional[datetime] = None
    access_count: int = 0
    
    class Config:
        from_attributes = True


class BulkShareResult(BaseModel):
    successful: List[DocumentShareResponse] = []
    failed: List[Dict[str, str]] = []
    total_requested: int
    total_successful: int
    total_failed: int


class ShareStatistics(BaseModel):
    total_shares: int
    active_shares: int
    expired_shares: int
    revoked_shares: int
    total_access_count: int
    unique_recipients: int
    most_accessed_documents: List[Dict[str, Any]]
    recent_shares: List[DocumentShareResponse]
    access_by_date: Dict[str, int]
    access_by_hour: Dict[int, int]