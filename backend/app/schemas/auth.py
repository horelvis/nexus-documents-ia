from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr

from app.schemas.user import UserBase


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    sub: str  # Usuario ID
    tid: str  # Tenant ID
    exp: int  # Fecha de expiración (timestamp)


class UserCreate(UserBase):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class User(UserBase):
    id: str
    tenant_id: str
    
    class Config:
        orm_mode = True