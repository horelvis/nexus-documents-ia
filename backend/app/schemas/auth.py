from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from app.schemas.user import UserRead # Import the refined UserRead schema

# Schema for login request
class LoginRequest(BaseModel):
    email: EmailStr = Field(..., example="user@example.com")
    password: str = Field(..., example="securepassword123")

# Schema for the token response
class TokenResponse(BaseModel):
    access_token: str = Field(..., example="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...")
    token_type: str = Field("bearer", example="bearer")
    user: Optional[UserRead] = None # UserRead already has examples

# Schema for the internal structure of the JWT payload
class TokenPayload(BaseModel):
    sub: str = Field(..., example="user_2aBcDeFgHiJkLmNoPqRsTuVwXyZ")  # Subject (User ID)
    tid: str  # Tenant ID
    exp: int  # Expiration time (timestamp)

# Schema for user authentication (general user info for auth purposes)
class UserAuth(BaseModel):
    id: str = Field(..., example="user_2aBcDeFgHiJkLmNoPqRsTuVwXyZ")
    email: EmailStr = Field(..., example="user@example.com")
    full_name: Optional[str] = Field(None, example="John Doe")
    is_active: bool = Field(True, example=True)
    is_superuser: bool = Field(False, example=False)
    tenant_id: str = Field(..., example="tenant-uuid")

# Schema for password reset request
class PasswordResetRequest(BaseModel):
    email: EmailStr = Field(..., example="user@example.com")

# Schema for password reset confirmation
class PasswordResetConfirm(BaseModel):
    token: str = Field(..., example="reset-token-here")
    new_password: str = Field(..., min_length=8, example="newpassword123")