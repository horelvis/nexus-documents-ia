from typing import Optional, List
from datetime import datetime
import uuid  # Corrected import for UUID
from pydantic import BaseModel, EmailStr, Field
from .rbac import Role  # Forward reference for Role
from .billing import Subscription  # Forward reference for Subscription


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
        from_orm = True


# Base schema for User, reflecting database model fields
class UserBase(BaseModel):
    email: EmailStr = Field(..., example="user@example.com")
    full_name: Optional[str] = Field(None, example="John Doe") # Renamed from fullName to full_name
    clerk_user_id: Optional[str] = Field(None, example="user_2aBcDeFgHiJkLmNoPqRsTuVwXyZ")


# Schema for creating a user (request model) - now aligning with SQLAlchemy model
class UserCreate(UserBase): # Renamed from UserCreateInput
    password: str = Field(..., min_length=8, example="securepassword123")
    tenant_id: uuid.UUID = Field(..., example=uuid.uuid4()) # Changed from tenantId (string) to tenant_id (UUID)
    is_superuser: bool = Field(False, example=False) # Renamed from isSuperuser
    is_active: bool = Field(True, example=True) # Renamed from isActive

# Schema for reading/returning user data (response model) - now aligning with SQLAlchemy model
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
        orm_mode = True

# Schema for updating a user (request model) - now aligning with SQLAlchemy model
class UserUpdate(BaseModel): # Renamed from UserUpdateInput and using BaseModel for flexibility
    email: Optional[EmailStr] = Field(None, example="user_updated@example.com")
    full_name: Optional[str] = Field(None, example="Johnathan Doe") # Renamed from fullName
    is_active: Optional[bool] = Field(None, example=True) # Renamed from isActive
    is_superuser: Optional[bool] = Field(None, example=False) # Renamed from isSuperuser
    clerk_user_id: Optional[str] = Field(None, example="user_2aBcDeFgHiJkLmNoPqRsTuVwXyZ_updated")
    # tenant_id is typically not changed this way, or handled separately
    # password updates should also be a separate, secure endpoint/process


# Schema for reading/returning user data (response model) - now aligning with SQLAlchemy model
class User(UserBase): # Renamed from UserRead
    id: uuid.UUID = Field(..., example=uuid.uuid4()) # Changed from string to UUID
    is_active: bool = Field(..., example=True) # Renamed from isActive
    is_superuser: bool = Field(..., example=False) # Renamed from isSuperuser
    tenant_id: uuid.UUID = Field(..., example=uuid.uuid4()) # Changed from tenantId (string) to tenant_id (UUID)
    created_at: datetime = Field(..., example=datetime.now()) # Renamed from createdAt
    updated_at: datetime = Field(..., example=datetime.now()) # Renamed from updatedAt
    image: Optional[UserImage] = None
    roles: List[Role] = []
    subscription: Optional[Subscription] = None

    class Config:
        from_orm = True # Renamed from orm_mode to from_orm for Pydantic v2
        # For FastAPI response_model, from_orm allows direct return of ORM objects.

# Update forward refs for models that might not be defined yet when User is defined
# This is important if Role or Subscription schemas are defined after User schema in different files
# and imported at the top.
User.update_forward_refs()
UserImage.update_forward_refs()