from datetime import datetime
from typing import List, Optional, Any, Dict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field
from app.core.config import settings
from .enums import IndexingStatus

# Esquemas Base
class TagBase(BaseModel):
    name: str

class DocumentBase(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: str
    description: Optional[str] = None


# Esquemas para DocumentMetrics
class DocumentMetricsBase(BaseModel):
    document_id: UUID
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
    created_by: UUID
    indexed: int
    created_at: datetime
    updated_at: datetime
    tags: List[TagBase] = []
    
    @computed_field
    @property
    def status(self) -> str:
        """
        Campo computado que devuelve un estado user-friendly
        en lugar del estado técnico de indexado
        """
        return self._get_user_friendly_status()
    
    @computed_field
    @property
    def ready_for_search(self) -> bool:
        """
        Campo computado que indica si el documento está disponible para búsqueda
        """
        return self.indexed == IndexingStatus.INDEXED
        
    def _get_user_friendly_status(self) -> str:
        """
        Convierte estados técnicos en estados user-friendly
        """
        status_map = {
            IndexingStatus.INDEXED: "available",      # Disponible - neutral y positivo
            IndexingStatus.PROCESSING: "processing",  # Procesando - temporal
            IndexingStatus.INDEXING_ERROR: "needs_attention", # Requiere atención - menos alarmante
            IndexingStatus.NOT_INDEXED: "pending"     # Pendiente - neutral
        }
        return status_map.get(self.indexed, "pending")
    
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
    model_config = ConfigDict(extra='forbid')

    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None

# Esquemas para respuestas
class Tag(TagBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class Document(DocumentBase):
    id: UUID
    filename: str
    file_type: str
    file_size: int
    mime_type: Optional[str] = None
    category: Optional[str] = None
    created_by: UUID
    indexed: int
    created_at: datetime
    updated_at: datetime
    tags: List[Tag] = []
    extracted_entities: Optional[List[Dict[str, Any]]] = []
    document_metadata: Optional[Dict[str, Any]] = None
    
    @computed_field
    @property
    def status(self) -> str:
        """
        Campo computado que devuelve un estado user-friendly
        en lugar del estado técnico de indexado
        """
        return self._get_user_friendly_status()
    
    @computed_field
    @property
    def ready_for_search(self) -> bool:
        """
        Campo computado que indica si el documento está disponible para búsqueda
        """
        return self.indexed == IndexingStatus.INDEXED
    
    @computed_field  
    @property
    def status_message(self) -> str:
        """
        Campo computado que devuelve un mensaje descriptivo del estado
        """
        message_map = {
            IndexingStatus.INDEXED: "Documento listo para búsqueda y análisis",
            IndexingStatus.PROCESSING: "Analizando contenido del documento...",
            IndexingStatus.INDEXING_ERROR: "El documento necesita ser reprocesado",
            IndexingStatus.NOT_INDEXED: "Documento en cola de procesamiento"
        }
        return message_map.get(self.indexed, "Estado desconocido")
        
    def _get_user_friendly_status(self) -> str:
        """
        Convierte estados técnicos en estados user-friendly
        """
        status_map = {
            IndexingStatus.INDEXED: "available",      # Disponible - neutral y positivo
            IndexingStatus.PROCESSING: "processing",  # Procesando - temporal
            IndexingStatus.INDEXING_ERROR: "needs_attention", # Requiere atención - menos alarmante
            IndexingStatus.NOT_INDEXED: "pending"     # Pendiente - neutral
        }
        return status_map.get(self.indexed, "pending")
    
    class Config:
        from_attributes = True

class DocumentDetail(Document):
    # DocumentDetail is now same as Document since chunks are handled by vector store
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