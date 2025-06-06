# app/schemas/signature.py

from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

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
    id: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}

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
    id: str
    signature_request_id: str
    status: str
    signed_at: Optional[datetime] = None
    created_at: datetime
    
    model_config = {"from_attributes": True}

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
    metadata: Dict[str, Any] = Field(default_factory=dict)

class SignatureRequestCreate(SignatureRequestBase):
    """Schema for creating signature requests"""
    document_id: str
    signers: List[SignerCreate]
    provider_id: Optional[str] = None

class SignatureRequestUpdate(BaseModel):
    """Schema for updating signature requests"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    message: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class SignatureRequest(SignatureRequestBase):
    """Schema for signature request responses"""
    id: str
    document_id: str
    provider_id: str
    tenant_id: str
    created_by: str
    external_id: Optional[str] = None
    status: str
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    signers: List[Signer] = []
    
    model_config = {"from_attributes": True}