from datetime import datetime
from typing import List, Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field


# Esquemas Base
class TagBase(BaseModel):
    name: str


class DocumentBase(BaseModel):
    title: str
    description: Optional[str] = None


# Esquemas para creación
class TagCreate(TagBase):
    pass


class DocumentCreate(DocumentBase):
    tags: Optional[List[str]] = []


# Esquemas para actualización
class TagUpdate(TagBase):
    pass


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None


# Esquemas para respuestas
class Tag(TagBase):
    id: int
    tenant_id: UUID
    created_at: datetime
    
    class Config:
        orm_mode = True


class DocumentChunk(BaseModel):
    id: int
    document_id: UUID
    chunk_index: int
    content: str
    
    class Config:
        orm_mode = True


class Document(DocumentBase):
    id: UUID
    filename: str
    file_type: str
    file_size: int
    tenant_id: UUID
    created_by: UUID
    indexed: int
    created_at: datetime
    updated_at: datetime
    tags: List[Tag] = []
    
    class Config:
        orm_mode = True


class DocumentDetail(Document):
    preview_chunks: Optional[List[DocumentChunk]] = []
    
    class Config:
        orm_mode = True


# Esquemas para búsqueda
class SearchQuery(BaseModel):
    query: str
    limit: Optional[int] = 10
    tags: Optional[List[str]] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class SearchResultMatch(BaseModel):
    chunk_text: str
    score: float


class SearchResult(BaseModel):
    document: Document
    score: float
    matches: List[SearchResultMatch]


class ChatMessage(BaseModel):
    question: str
    doc_ids: List[UUID] = []


# Esquemas para URLs firmadas
class SignedUrlResponse(BaseModel):
    url: str
    expires_at: datetime


class UploadRequest(BaseModel):
    filename: str
    content_type: str
    size: int

