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


class LegalStatus(str, Enum):
    """Legal status of a document"""
    VIGENTE = "vigente"
    DEROGADA = "derogada"
    PARCIALMENTE_DEROGADA = "parcialmente_derogada"
    PENDIENTE = "pendiente"  # Pendiente de entrada en vigor


class ModificationType(str, Enum):
    """Type of modification for versioned documents"""
    ORIGINAL = "original"  # Texto original publicado
    MODIFICACION = "modificacion"  # Modificación de artículos
    CORRECCION = "correccion"  # Corrección de errores
    DEROGACION_PARCIAL = "derogacion_parcial"  # Derogación de artículos
    REFUNDIDO = "refundido"  # Texto refundido


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

    # Versioning metadata
    version_number: int = Field(default=1, description="Numeric version (1, 2, 3...)")
    is_current_version: bool = Field(default=True, description="Whether this is the current/active version")
    consolidation_date: Optional[datetime] = Field(None, description="Date of last text consolidation")
    superseded_by: Optional[str] = Field(None, description="ID of the version that supersedes this one")
    supersedes: Optional[str] = Field(None, description="ID of the version this one supersedes")

    # Modification tracking
    modification_type: str = Field(default="original", description="Type: original, modificacion, correccion, derogacion_parcial, refundido")
    modifying_laws: List[str] = Field(default_factory=list, description="Laws that have modified this document")
    modified_articles: List[str] = Field(default_factory=list, description="Articles modified in this version")

    # Legal status
    legal_status: str = Field(default="vigente", description="Status: vigente, derogada, parcialmente_derogada, pendiente")
    derogated_by: Optional[str] = Field(None, description="Reference of the law that derogates this one")
    partial_derogations: List[str] = Field(default_factory=list, description="List of derogated articles/sections")

    # Identifiers
    boe_id: Optional[str] = Field(None, description="BOE identifier (e.g., BOE-A-2018-16673)")
    eli_uri: Optional[str] = Field(None, description="European Legislation Identifier URI")

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

    # Versioning metadata
    version_number: int = 1
    is_current_version: bool = True
    consolidation_date: Optional[datetime] = None
    superseded_by: Optional[str] = None
    supersedes: Optional[str] = None

    # Modification tracking
    modification_type: str = "original"
    modifying_laws: List[str] = []
    modified_articles: List[str] = []

    # Legal status
    legal_status: str = "vigente"
    derogated_by: Optional[str] = None
    partial_derogations: List[str] = []

    # Identifiers
    boe_id: Optional[str] = None
    eli_uri: Optional[str] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Search results metadata
    similarity_score: Optional[float] = None
    relevance_explanation: Optional[str] = None


class PublicSearchRequest(BaseModel):
    """Schema for searching public knowledge base"""
    query: str = Field(..., description="Search query")
    limit: int = Field(default=10, ge=1, le=1000, description="Max results")

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

    # Version filtering
    current_version_only: bool = Field(default=True, description="Only return current/active versions")
    legal_status: Optional[List[str]] = Field(None, description="Filter by legal status: vigente, derogada, etc.")
    as_of_date: Optional[datetime] = Field(None, description="Get version that was effective at this date")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "protección de datos personales empleados",
                "limit": 10,
                "categories": ["legislation", "regulation"],
                "jurisdictions": ["es", "eu"],
                "topics": ["proteccion_datos", "laboral"],
                "verified_only": True,
                "search_type": "hybrid",
                "current_version_only": True,
                "legal_status": ["vigente"]
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
