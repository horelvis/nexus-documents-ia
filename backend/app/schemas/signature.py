# app/schemas/signature.py

from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

# =====================================
# SIGNATURE PROVIDER SCHEMAS
# =====================================

class SignatureProviderBase(BaseModel):
    """Base schema for signature providers"""
    provider_name: str = Field(..., pattern="^(docusign|yousign|signaturit)$")
    display_name: str = Field(..., min_length=1, max_length=100)
    credentials: Dict[str, Any] = Field(default_factory=dict)
    configuration: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    is_default: bool = False

class SignatureProviderCreate(SignatureProviderBase):
    """Schema for creating signature providers"""
    pass

class SignatureProviderUpdate(BaseModel):
    """Schema for updating signature providers"""
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    credentials: Optional[Dict[str, Any]] = None
    configuration: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None

class SignatureProvider(SignatureProviderBase):
    """Schema for signature provider responses"""
    id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True, json_encoders={UUID: str})

# =====================================
# SIGNER SCHEMAS  
# =====================================

class SignerBase(BaseModel):
    """Base schema for signers"""
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., pattern=r'^[^@]+@[^@]+\.[^@]+$')
    phone: Optional[str] = Field(None, max_length=20)
    order: int = Field(default=1, ge=1)
    authentication_method: str = Field(default='email', pattern='^(email|sms|code)$')
    success_url: Optional[str] = None
    error_url: Optional[str] = None

class SignerCreate(SignerBase):
    """Schema for creating signers"""
    pass

class Signer(SignerBase):
    """Schema for signer responses"""
    id: UUID
    request_id: UUID  # Changed from signature_request_id to match DB model
    status: str
    signed_at: Optional[datetime] = None
    external_id: Optional[str] = None
    signing_url: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True, json_encoders={UUID: str})

# =====================================
# SIGNATURE REQUEST SCHEMAS
# =====================================

class SignatureRequestBase(BaseModel):
    """Base schema for signature requests"""
    title: str = Field(..., min_length=1, max_length=200)
    message: Optional[str] = None
    document_name: str = Field(..., min_length=1, max_length=255)
    document_content: Optional[str] = None
    document_url: Optional[str] = None
    signature_type: str = Field(default='sequential', pattern='^(sequential|parallel)$')
    callback_url: Optional[str] = None
    success_url: Optional[str] = None
    error_url: Optional[str] = None
    request_metadata: Dict[str, Any] = Field(default_factory=dict)

class SignatureRequestCreate(SignatureRequestBase):
    """Schema for creating signature requests"""
    document_id: UUID
    signers: List[SignerCreate]
    provider_id: Optional[UUID] = None

class SignatureRequestUpdate(BaseModel):
    """Schema for updating signature requests"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    message: Optional[str] = None
    status: Optional[str] = None
    request_metadata: Optional[Dict[str, Any]] = Field(None, alias="metadata")

class SignatureRequest(SignatureRequestBase):
    """Schema for signature request responses"""
    id: UUID
    provider_id: UUID
    tenant_id: UUID
    created_by: UUID
    external_id: Optional[str] = None
    status: str
    sent_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    signers: List[Signer] = []
    
    # Override document_content to exclude from response
    document_content: None = Field(default=None, exclude=True)
    
    model_config = ConfigDict(from_attributes=True, json_encoders={UUID: str})