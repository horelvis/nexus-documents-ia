from typing import Optional
from datetime import datetime
# UUID might still be used for request validation before it becomes string in Prisma
from uuid import UUID 
from pydantic import BaseModel, EmailStr, Field

# Base schema for User, reflecting Prisma model fields
class UserBase(BaseModel):
    email: EmailStr = Field(..., example="user@example.com")
    fullName: Optional[str] = Field(None, example="John Doe") # Matches Prisma schema

# Schema for creating a user (request model)
class UserCreateInput(UserBase):
    password: str = Field(..., min_length=8, example="securepassword123")
    tenantId: str = Field(..., example="clerk_2aBcDeFgHiJkLmNoPqRsTuVwXyZ") # In Prisma, this is a String
    clerkUserId: Optional[str] = Field(None, example="user_2aBcDeFgHiJkLmNoPqRsTuVwXyZ")
    isSuperuser: bool = Field(False, example=False) # Matches Prisma schema
    isActive: bool = Field(True, example=True) # Matches Prisma schema

# Schema for updating a user (request model)
# Defining it for completeness, though not strictly required by current task list
class UserUpdateInput(BaseModel):
    email: Optional[EmailStr] = Field(None, example="user_updated@example.com")
    fullName: Optional[str] = Field(None, example="Johnathan Doe")
    isActive: Optional[bool] = Field(None, example=True)
    isSuperuser: Optional[bool] = Field(None, example=False)
    clerkUserId: Optional[str] = Field(None, example="user_2aBcDeFgHiJkLmNoPqRsTuVwXyZ_updated")
    # tenantId is typically not changed this way, or handled separately
    # password updates should also be a separate, secure endpoint/process

# Schema for reading/returning user data (response model)
class UserRead(UserBase):
    id: str = Field(..., example="clerk_2aBcDeFgHiJkLmNoPqRsTuVwXyZ") # Prisma IDs are typically strings
    isActive: bool = Field(..., example=True)
    isSuperuser: bool = Field(..., example=False)
    tenantId: str = Field(..., example="org_2aBcDeFgHiJkLmNoPqRsTuVwXyZ")
    clerkUserId: Optional[str] = Field(None, example="user_2aBcDeFgHiJkLmNoPqRsTuVwXyZ_clerk_id")
    createdAt: datetime = Field(..., example=datetime.now())
    updatedAt: datetime = Field(..., example=datetime.now())

    class Config:
        orm_mode = True # For compatibility with ORM models (Prisma Client Python)
        # If using Prisma's auto_register=True, this helps Pydantic understand Prisma models
        # For FastAPI response_model, orm_mode allows direct return of ORM objects.