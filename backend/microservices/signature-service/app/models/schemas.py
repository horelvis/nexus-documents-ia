"""
Pydantic schemas for Signature Service
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from enum import Enum

class ProviderType(str, Enum):
    DOCUSIGN = "docusign"
    YOUSIGN = "yousign"
    SIGNATURIT = "signaturit"

class SignerRole(str, Enum):
    SIGNER = "signer"
    VIEWER = "viewer"
    APPROVER = "approver"

class SignatureStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    SENT = "sent"
    VIEWED = "viewed"
    SIGNED = "signed"
    COMPLETED = "completed"
    DECLINED = "declined"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

class Environment(str, Enum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"

# Provider Credentials Schemas
class DocuSignCredentials(BaseModel):
    integration_key: str
    secret_key: str
    account_id: str
    base_url: str

class YouSignCredentials(BaseModel):
    api_key: str
    environment: Environment

class SignaturitCredentials(BaseModel):
    access_token: str
    environment: Environment

# Request/Response Schemas
class SignerRequest(BaseModel):
    email: EmailStr
    name: str
    role: SignerRole = SignerRole.SIGNER
    phone: Optional[str] = None
    order: int = 1

class SignerResponse(BaseModel):
    email: str
    name: str
    role: SignerRole
    external_id: Optional[str] = None
    signing_url: Optional[str] = None
    status: SignatureStatus = SignatureStatus.PENDING
    signed_at: Optional[datetime] = None

class CreateSignatureRequest(BaseModel):
    provider_type: ProviderType
    provider_credentials: Dict[str, Any]
    title: str
    message: Optional[str] = None
    document_content: str  # Base64 encoded
    document_name: str
    signers: List[SignerRequest]
    expires_in_days: int = 30
    webhook_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class SignatureRequestResponse(BaseModel):
    external_id: str
    status: SignatureStatus
    signers: List[SignerResponse]
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    provider_type: ProviderType

class GetStatusRequest(BaseModel):
    provider_type: ProviderType
    provider_credentials: Dict[str, Any]
    external_id: str

class StatusResponse(BaseModel):
    external_id: str
    status: SignatureStatus
    completion_percentage: int
    signers: List[SignerResponse]
    completed_at: Optional[datetime] = None

class CancelRequest(BaseModel):
    provider_type: ProviderType
    provider_credentials: Dict[str, Any]
    external_id: str
    reason: str = "Cancelled by user"

class DownloadRequest(BaseModel):
    provider_type: ProviderType
    provider_credentials: Dict[str, Any]
    external_id: str

class TestConnectionRequest(BaseModel):
    provider_type: ProviderType
    provider_credentials: Dict[str, Any]

class TestConnectionResponse(BaseModel):
    success: bool
    message: str

class WebhookEvent(BaseModel):
    provider: ProviderType
    event_type: str
    data: Dict[str, Any]
    received_at: datetime = Field(default_factory=datetime.now)

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: datetime