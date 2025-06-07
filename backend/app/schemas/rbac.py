from typing import Optional, List
from datetime import datetime
import uuid
from pydantic import BaseModel, Field

# --- Permission Schemas ---
class PermissionBase(BaseModel):
    entity: str = Field(..., example="document")
    action: str = Field(..., example="read")
    access: str = Field(..., example="own")
    description: Optional[str] = Field("", example="Allows reading own documents")

class PermissionCreate(PermissionBase):
    pass

class PermissionUpdate(PermissionBase):
    pass

class Permission(PermissionBase):
    id: uuid.UUID = Field(..., example=uuid.uuid4())
    created_at: datetime = Field(..., example=datetime.now())
    updated_at: datetime = Field(..., example=datetime.now())

    class Config:
        from_attributes = True

# --- Role Schemas ---
class RoleBase(BaseModel):
    name: str = Field(..., example="Editor")
    description: Optional[str] = Field("", example="Role with document editing capabilities")

class RoleCreate(RoleBase):
    permissions: List[uuid.UUID] = Field([], example=[uuid.uuid4(), uuid.uuid4()])

class RoleUpdate(RoleBase):
    permissions: Optional[List[uuid.UUID]] = Field(None, example=[uuid.uuid4()])

class Role(RoleBase):
    id: uuid.UUID = Field(..., example=uuid.uuid4())
    permissions: List[Permission] = []
    created_at: datetime = Field(..., example=datetime.now())
    updated_at: datetime = Field(..., example=datetime.now())

    class Config:
        from_attributes = True

# Update forward references if necessary, though for self-contained file it might not be
# However, if other schemas depend on these, it's good practice.
Permission.update_forward_refs()
Role.update_forward_refs()
