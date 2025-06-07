from datetime import datetime
from typing import List, Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field
from app.core.config import settings
from .enums import IndexingStatus

# Esquemas Base
class TagBase(BaseModel):
    name: str

class DocumentBase(BaseModel):
    title: str
    description: Optional[str] = None

# Esquemas para DocumentChunk
class DocumentChunkBase(BaseModel):
    document_id: UUID
    chunk_index: int
    content: str

class DocumentChunkCreate(DocumentChunkBase):
    pass

class DocumentChunk(DocumentChunkBase):
    id: int
    embedding_id: Optional[str] = None
    
    class Config:
        from_attributes = True

# Esquemas para DocumentMetrics
class DocumentMetricsBase(BaseModel):
    document_id: UUID
    tenant_id: UUID
    view_count: int = 0
    download_count: int = 0
    share_count: int = 0
    query_count: int = 0
    relevance_score: float = 0.0

class DocumentMetricsCreate(DocumentMetricsBase):
    pass

class DocumentMetrics(DocumentMetricsBase):
    id: UUID
    last_viewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# Esquemas para DocumentTag (relación)
class DocumentTagBase(BaseModel):
    document_id: UUID
    tag_id: int

class DocumentTagCreate(DocumentTagBase):
    pass

class DocumentTag(DocumentTagBase):
    pass

# Esquemas para DocumentView (relación)
class DocumentViewBase(BaseModel):
    user_id: UUID
    document_id: UUID
    tenant_id: UUID
    view_duration_seconds: Optional[int] = None
    is_complete_view: bool = False

class DocumentViewCreate(DocumentViewBase):
    pass

class DocumentView(DocumentViewBase):
    id: UUID
    viewed_at: datetime
    
    class Config:
        from_attributes = True

# Esquemas básicos y con métricas
class DocumentBasic(DocumentBase):
    id: UUID
    filename: str
    file_type: str
    file_size: int
    tenant_id: UUID
    created_by: UUID
    indexed: int
    created_at: datetime
    updated_at: datetime
    tags: List[TagBase] = []
    
    class Config:
        from_attributes = True

class DocumentWithMetrics(DocumentBasic):
    metrics: Optional[DocumentMetrics] = None
    
    class Config:
        from_attributes = True

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
        from_attributes = True

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
        from_attributes = True

class DocumentDetail(Document):
    preview_chunks: Optional[List[DocumentChunk]] = []
    
    class Config:
        from_attributes = True

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
    size: int = Field(..., gt=0, lt=settings.MAX_UPLOAD_SIZE)
    
    class Config:
        json_schema_extra = {
            "example": {
                "filename": "example.pdf",
                "content_type": "application/pdf",
                "size": 1024000
            }
        }