from typing import Optional, List
from datetime import datetime
import uuid
from pydantic import BaseModel, EmailStr, Field
from .rbac import Role
# from .billing import Subscription  # Removed - subscriptions handled by Stripe

# Base schema for UserImage
class UserImageBase(BaseModel):
    alt_text: Optional[str] = Field(None, example="User profile picture")
    content_type: str = Field(..., example="image/png")

# Schema for creating a UserImage
class UserImageCreate(UserImageBase):
    pass

# Schema for updating a UserImage
class UserImageUpdate(UserImageBase):
    pass

# Schema for reading/returning UserImage data
class UserImage(UserImageBase):
    id: uuid.UUID = Field(..., example=uuid.uuid4())
    user_id: uuid.UUID = Field(..., example=uuid.uuid4())
    created_at: datetime = Field(..., example=datetime.now())
    updated_at: datetime = Field(..., example=datetime.now())

    class Config:
        from_attributes = True

# Base schema for User, reflecting database model fields
class UserBase(BaseModel):
    email: EmailStr = Field(..., example="user@example.com")
    full_name: Optional[str] = Field(None, example="John Doe")
    clerk_user_id: Optional[str] = Field(None, example="user_2aBcDeFgHiJkLmNoPqRsTuVwXyZ")

# Schema for creating a user (request model)
class UserCreate(UserBase):
    password: str = Field(..., min_length=8, example="securepassword123")
    tenant_id: uuid.UUID = Field(..., example=uuid.uuid4())
    is_superuser: bool = Field(False, example=False)
    is_active: bool = Field(True, example=True)


# Schema for syncing user from Clerk (with optional Stripe data)
class UserSync(BaseModel):
    clerk_user_id: str = Field(..., example="user_2aBcDeFgHiJkLmNoPqRsTuVwXyZ")
    email: EmailStr = Field(..., example="user@example.com")
    full_name: str = Field(..., example="John Doe")
    # Stripe integration fields (optional)
    stripe_customer_id: Optional[str] = Field(None, example="cus_1234567890")
    stripe_session_id: Optional[str] = Field(None, example="cs_1234567890")

# Schema for completing onboarding with simplified data
class OnboardingComplete(BaseModel):
    first_name: Optional[str] = Field(None, example="John")
    last_name: Optional[str] = Field(None, example="Doe")
    company_name: Optional[str] = Field(None, example="Mi Empresa SL")
    cif: Optional[str] = Field(None, example="B12345678")
    industry: Optional[str] = Field(None, example="Technology")
    selected_plan: Optional[str] = Field(None, example="pro")
    payment_interval: Optional[str] = Field(None, example="month")
    onboarding_step: Optional[str] = Field(None, example="completed")

# Schema for reading/returning user data (response model)
class UserRead(UserBase):
    id: uuid.UUID
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool
    is_superuser: bool
    tenant_id: uuid.UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Schema for updating a user (request model)
class UserUpdate(BaseModel):
    email: Optional[EmailStr] = Field(None, example="user_updated@example.com")
    full_name: Optional[str] = Field(None, example="Johnathan Doe")
    is_active: Optional[bool] = Field(None, example=True)
    is_superuser: Optional[bool] = Field(None, example=False)
    clerk_user_id: Optional[str] = Field(None, example="user_2aBcDeFgHiJkLmNoPqRsTuVwXyZ_updated")
    password: Optional[str] = Field(None, min_length=8, example="newpassword123")
    tenant_id: Optional[uuid.UUID] = Field(None, example=uuid.uuid4())

# Schema for complete user response with relationships
class User(UserBase):
    id: uuid.UUID = Field(..., example=uuid.uuid4())
    is_active: bool = Field(..., example=True)
    is_superuser: bool = Field(..., example=False)
    onboarding_completed: bool = Field(False, example=False)
    stripe_customer_id: Optional[str] = Field(None, example="cus_1234567890")
    tenant_id: uuid.UUID = Field(..., example=uuid.uuid4())
    created_at: datetime = Field(..., example=datetime.now())
    updated_at: datetime = Field(..., example=datetime.now())
    image: Optional[UserImage] = None
    roles: List[Role] = []
    # subscription: Optional[Subscription] = None  # Removed - subscriptions handled by Stripe
    
    # Subscription info from Stripe (populated dynamically)
    subscription_plan: Optional[str] = Field(None, example="pro")
    subscription_status: Optional[str] = Field(None, example="active")

    class Config:
        from_attributes = True

# Alias for UserResponse (commonly used in APIs)
UserResponse = User

# Update forward refs for models that might not be defined yet when User is defined
User.update_forward_refs()
UserImage.update_forward_refs()

# Additional schemas for user management

class UserWithStats(BaseModel):
    """User with usage statistics for admin panel"""
    id: str
    email: str
    name: Optional[str] = None
    role: str
    status: str  # active, inactive, pending
    createdAt: str
    lastLogin: Optional[str] = None
    avatar: Optional[str] = None
    documentsCount: int = 0
    storageUsed: int = 0

class UserInvite(BaseModel):
    """Schema for inviting new users"""
    email: EmailStr
    role: str = Field(default="user", pattern="^(admin|user|viewer)$")
    name: Optional[str] = None

class UserRoleUpdate(BaseModel):
    """Schema for updating user role"""
    role: str = Field(..., pattern="^(admin|user|viewer)$")

class UserActivity(BaseModel):
    """User activity information"""
    user_id: str
    email: str
    name: Optional[str] = None
    period_days: int
    document_uploads: List[dict]
    last_login: Optional[str] = None
    account_created: str

class UserListResponse(BaseModel):
    """Response for user list endpoint"""
    users: List[UserWithStats]
    total: int
    skip: int
    limit: int