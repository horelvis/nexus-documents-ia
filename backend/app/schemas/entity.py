from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class Entity(BaseModel):
    id: str
    name: str
    email: str
    type: str  # 'user', 'contact', 'organization', 'agent'
    role: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class EntitySearchResponse(BaseModel):
    entities: List[Entity]
    total: int