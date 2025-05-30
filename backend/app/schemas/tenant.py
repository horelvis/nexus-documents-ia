from typing import Dict, List, Optional, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

from app.schemas.user import UserResponse


class TenantBase(BaseModel):
    name: str
    description: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class TenantCreate(TenantBase):
    pass


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    settings: Optional[Dict[str, Any]] = None


class TenantResponse(TenantBase):
    id: UUID
    bucket_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


class TenantWithUsers(TenantResponse):
    users: List[UserResponse] = []
    
    class Config:
        orm_mode = True