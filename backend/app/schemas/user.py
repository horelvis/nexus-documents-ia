from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool = True


class UserCreate(UserBase):
    password: str
    tenant_id: UUID
    is_superuser: bool = False


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    tenant_id: Optional[UUID] = None


class UserResponse(UserBase):
    id: UUID
    tenant_id: UUID
    is_superuser: bool
    created_at: datetime
    
    class Config:
        orm_mode = True


class User(UserResponse):
    pass