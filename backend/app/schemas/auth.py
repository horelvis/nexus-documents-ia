from typing import Optional
from pydantic import BaseModel, EmailStr
from app.schemas.user import UserRead # Import the refined UserRead schema
from pydantic import Field # Import Field for adding examples

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
    sub: str = Field(..., example="clerk_2aBcDeFgHiJkLmNoPqRsTuVwXyZ")  # Subject (User ID)
    tid: str  # Tenant ID
    exp: int  # Expiration time (timestamp)
    # iat: int # Issued at time (timestamp) - can be added if needed
    # Add any other custom claims you need