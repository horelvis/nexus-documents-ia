# app/schemas/signature_contact.py

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, EmailStr


class SignatureContactBase(BaseModel):
    """Base schema for signature contacts"""
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    role: Optional[str] = Field(None, max_length=100)
    company: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None
    contact_metadata: Dict[str, Any] = Field(default_factory=dict)


class SignatureContactCreate(SignatureContactBase):
    """Schema for creating signature contacts"""
    is_favorite: bool = False


class SignatureContactUpdate(BaseModel):
    """Schema for updating signature contacts"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    role: Optional[str] = Field(None, max_length=100) 
    company: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None
    is_favorite: Optional[bool] = None
    contact_metadata: Optional[Dict[str, Any]] = None


class SignatureContact(SignatureContactBase):
    """Schema for signature contact responses"""
    id: UUID
    tenant_id: UUID
    created_by: UUID
    is_favorite: bool
    usage_count: int
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True, json_encoders={UUID: str})


class SignatureContactList(BaseModel):
    """Schema for listing signature contacts"""
    contacts: list[SignatureContact]
    total: int
    favorites_count: int
    
    model_config = ConfigDict(from_attributes=True)