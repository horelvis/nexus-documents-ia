"""Pydantic schemas for Public Knowledge Base operations"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class PublicDocumentCategory(str, Enum):
    """Categories for public specialized documents"""
    LEGISLATION = "legislation"  # Leyes, decretos, códigos
    REGULATION = "regulation"  # Normativas, reglamentos
    JURISPRUDENCE = "jurisprudence"  # Sentencias, jurisprudencia
    TEMPLATE = "template"  # Plantillas de documentos legales
    GUIDELINE = "guideline"  # Guías, manuales, procedimientos
    REFERENCE = "reference"  # Material de referencia general
    FORM = "form"  # Formularios oficiales
    TREATY = "treaty"  # Tratados, convenios internacionales


class Jurisdiction(str, Enum):
    """Jurisdictions for legal documents"""
    SPAIN = "es"
    EUROPEAN_UNION = "eu"
    INTERNATIONAL = "int"
    REGIONAL = "regional"  # Comunidades autónomas, etc.


class PublicDocumentCreate(BaseModel):
    """Schema for creating public knowledge documents"""
    id: Optional[str] = None
    title: str = Field(..., description="Document title")
    content: str = Field(..., description="Full document content")
    summary: Optional[str] = Field(None, description="Document summary")

    # Classification
    category: PublicDocumentCategory = Field(..., description="Document category")
    subcategory: Optional[str] = Field(None, description="Specific subcategory")
    jurisdiction: Jurisdiction = Field(default=Jurisdiction.SPAIN, description="Legal jurisdiction")

    # Legal metadata
    legal_reference: Optional[str] = Field(None, description="Official legal reference (BOE, DOUE, etc.)")
    publication_date: Optional[datetime] = Field(None, description="Official publication date")
    effective_date: Optional[datetime] = Field(None, description="Date when document becomes effective")
    expiration_date: Optional[datetime] = Field(None, description="Expiration date if applicable")

    # Search optimization
    keywords: List[str] = Field(default_factory=list, description="Search keywords")
    topics: List[str] = Field(default_factory=list, description="Related topics")
    related_documents: List[str] = Field(default_factory=list, description="IDs of related documents")

    # Source information
    source_url: Optional[str] = Field(None, description="Original source URL")
    source_name: Optional[str] = Field(None, description="Source name (BOE, EUR-Lex, etc.)")

    # Quality metadata
    verified: bool = Field(default=False, description="Whether document has been verified")
    version: str = Field(default="1.0", description="Document version")

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Ley Orgánica 3/2018, de Protección de Datos Personales",
                "content": "Artículo 1. Objeto de la ley...",
                "summary": "Ley que regula la protección de datos personales en España",
                "category": "legislation",
                "subcategory": "proteccion_datos",
                "jurisdiction": "es",
                "legal_reference": "BOE-A-2018-16673",
                "publication_date": "2018-12-06T00:00:00Z",
                "effective_date": "2018-12-07T00:00:00Z",
                "keywords": ["LOPD", "RGPD", "protección datos", "privacidad"],
                "topics": ["proteccion_datos", "derechos_digitales"],
                "source_url": "https://www.boe.es/eli/es/lo/2018/12/05/3",
                "source_name": "BOE",
                "verified": True,
                "version": "1.0"
            }
        }


class PublicDocumentResponse(BaseModel):
    """Schema for public knowledge document response"""
    id: str
    title: str
    content: str
    summary: Optional[str] = None

    # Classification
    category: str
    subcategory: Optional[str] = None
    jurisdiction: str

    # Legal metadata
    legal_reference: Optional[str] = None
    publication_date: Optional[datetime] = None
    effective_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None

    # Search optimization
    keywords: List[str] = []
    topics: List[str] = []
    related_documents: List[str] = []

    # Source information
    source_url: Optional[str] = None
    source_name: Optional[str] = None

    # Quality metadata
    verified: bool = False
    version: str = "1.0"

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Search results metadata
    similarity_score: Optional[float] = None
    relevance_explanation: Optional[str] = None


class PublicSearchRequest(BaseModel):
    """Schema for searching public knowledge base"""
    query: str = Field(..., description="Search query")
    limit: int = Field(default=10, ge=1, le=100, description="Max results")

    # Filters
    categories: Optional[List[PublicDocumentCategory]] = Field(None, description="Filter by categories")
    jurisdictions: Optional[List[Jurisdiction]] = Field(None, description="Filter by jurisdictions")
    topics: Optional[List[str]] = Field(None, description="Filter by topics")
    date_from: Optional[datetime] = Field(None, description="Filter by publication date from")
    date_to: Optional[datetime] = Field(None, description="Filter by publication date to")
    verified_only: bool = Field(default=False, description="Only return verified documents")

    # Search configuration
    search_type: str = Field(default="hybrid", pattern="^(vector|keyword|hybrid)$")
    include_expired: bool = Field(default=False, description="Include expired documents")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "protección de datos personales empleados",
                "limit": 10,
                "categories": ["legislation", "regulation"],
                "jurisdictions": ["es", "eu"],
                "topics": ["proteccion_datos", "laboral"],
                "verified_only": True,
                "search_type": "hybrid"
            }
        }


class PublicSearchResponse(BaseModel):
    """Schema for public search response"""
    query: str
    results: List[PublicDocumentResponse]
    total_results: int
    search_time_ms: int
    search_type: str
    filters_applied: Dict[str, Any] = {}


class CombinedSearchRequest(BaseModel):
    """Schema for searching both tenant and public knowledge bases"""
    query: str = Field(..., description="Search query")
    tenant_id: str = Field(..., description="Tenant ID for private documents")
    limit: int = Field(default=10, ge=1, le=100, description="Max results per source")

    # Source selection
    include_tenant_docs: bool = Field(default=True, description="Include tenant documents")
    include_public_docs: bool = Field(default=True, description="Include public knowledge")

    # Public knowledge filters
    public_categories: Optional[List[PublicDocumentCategory]] = None
    public_jurisdictions: Optional[List[Jurisdiction]] = None

    # Search configuration
    search_type: str = Field(default="hybrid", pattern="^(vector|keyword|hybrid)$")
    merge_strategy: str = Field(default="interleaved", pattern="^(interleaved|separate|ranked)$")


class CombinedSearchResponse(BaseModel):
    """Schema for combined search response"""
    query: str
    tenant_results: List[Dict[str, Any]] = []
    public_results: List[PublicDocumentResponse] = []
    total_tenant_results: int = 0
    total_public_results: int = 0
    search_time_ms: int
    merge_strategy: str


class PublicKnowledgeStats(BaseModel):
    """Statistics for public knowledge base"""
    total_documents: int
    documents_by_category: Dict[str, int]
    documents_by_jurisdiction: Dict[str, int]
    verified_count: int
    last_updated: datetime
    topics_index: List[str]
