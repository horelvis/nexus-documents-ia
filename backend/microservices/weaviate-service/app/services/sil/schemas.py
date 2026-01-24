"""
Schemas for Structural Intelligence Layer (SIL)

These schemas define the data models for structural reasoning,
focusing on STRUCTURE rather than CONTENT of documents.
"""

from enum import Enum
from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, Field
from datetime import datetime


# =============================================================================
# INTENT TYPES
# =============================================================================


class TargetEntity(str, Enum):
    """What type of entity the query is about."""

    DOCUMENT = "document"  # Query about documents
    FOLDER = "folder"  # Query about folders/expedientes/cases
    BOTH = "both"  # Query about both (e.g., "documents in folder X")


class IntentType(str, Enum):
    """Type of query intent for routing."""

    # Structural queries - can be answered from graph alone
    STRUCTURAL = "structural"  # "How many contracts does ACME have?"
    STRUCTURAL_COUNT = "structural_count"  # "Count documents in folder X"
    STRUCTURAL_LIST = "structural_list"  # "List all contracts for client Y"
    STRUCTURAL_EXISTS = "structural_exists"  # "Is there a contract with ACME?"
    STRUCTURAL_LOCATION = "structural_location"  # "Where is the ACME contract?"

    # Folder/structure queries - about folders, cases, expedientes
    FOLDER_COUNT = "folder_count"  # "How many expedientes/cases do we have?"
    FOLDER_LIST = "folder_list"  # "List all expedientes for client X"
    FOLDER_EXISTS = "folder_exists"  # "Is there an expediente for ACME?"
    FOLDER_CONTENTS = "folder_contents"  # "What's in expediente X?"
    FOLDER_BROWSE = "folder_browse"  # "Show me the folder structure"

    # Temporal queries - require temporal graph traversal
    TEMPORAL_POINT = "temporal_point"  # "What was the state on Jan 1?"
    TEMPORAL_RANGE = "temporal_range"  # "What changed this week?"
    TEMPORAL_EVOLUTION = "temporal_evolution"  # "How has folder X evolved?"
    TEMPORAL_COMPARISON = "temporal_comparison"  # "Compare state A to state B"

    # Multi-hop queries - require graph traversal
    MULTIHOP_SIMPLE = "multihop_simple"  # 2 hops: "Contracts of clients with tickets"
    MULTIHOP_COMPLEX = "multihop_complex"  # 3+ hops: "Docs created by Juan's dept"

    # Content-required queries - need RAG but can be focused
    CONTENT_SPECIFIC = "content_specific"  # "What are the penalties in ACME contract?"
    CONTENT_SUMMARY = "content_summary"  # "Summarize the ACME contracts"
    CONTENT_EXTRACTION = "content_extraction"  # "Extract amounts from contract"

    # Full RAG queries - need full corpus search
    CONTENT_GENERAL = "content_general"  # "What contracts mention penalties?"
    CONTENT_COMPLEX = "content_complex"  # Complex analysis requiring many docs

    # Legal queries - leverage Legal Knowledge Graph
    LEGAL_APPLICABILITY = "legal_applicability"  # "What laws apply to this contract?"
    LEGAL_COMPLIANCE = "legal_compliance"  # "Does this comply with RGPD?"
    LEGAL_REFERENCE = "legal_reference"  # "What does Art. 34 ET say about..."
    LEGAL_DOCUMENT_LAWS = "legal_document_laws"  # "What laws govern this document?"

    # Unknown/fallback
    UNKNOWN = "unknown"


class ReasoningType(str, Enum):
    """Type of reasoning applied to the query."""

    # Purely structural - no RAG needed
    STRUCTURAL = "structural"  # Answered via Cypher query alone

    # Temporal - answered from temporal graph
    TEMPORAL = "temporal"  # Time-based structural query

    # Multi-hop - graph traversal
    MULTIHOP = "multihop"  # Multiple relationship hops

    # Focused RAG - need content but from specific docs
    FOCUSED_RAG = "focused_rag"  # RAG limited to identified documents

    # Full RAG - need full corpus search
    FULL_RAG = "full_rag"  # Standard RAG pipeline

    # Hybrid - structural context + focused RAG
    HYBRID = "hybrid"  # Combine structural + content

    # Legal - queries about laws and legal applicability
    LEGAL = "legal"  # Answered from Legal Knowledge Graph
    LEGAL_ENRICHED = "legal_enriched"  # Structural + legal context


# =============================================================================
# STRUCTURAL METADATA
# =============================================================================


class SemanticType(str, Enum):
    """Semantic type of a document (what it IS, not what it contains)."""

    # Legal documents
    CONTRACT = "contract"
    AGREEMENT = "agreement"
    AMENDMENT = "amendment"
    ANNEX = "annex"
    LEGAL_BRIEF = "legal_brief"
    COURT_FILING = "court_filing"
    RESOLUTION = "resolution"

    # Corporate documents
    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"
    QUOTE = "quote"
    REPORT = "report"
    MEMO = "memo"
    POLICY = "policy"
    PROCEDURE = "procedure"

    # HR documents
    EMPLOYEE_FILE = "employee_file"
    PERFORMANCE_REVIEW = "performance_review"
    OFFER_LETTER = "offer_letter"
    TERMINATION = "termination"

    # Financial documents
    FINANCIAL_STATEMENT = "financial_statement"
    AUDIT_REPORT = "audit_report"
    TAX_RETURN = "tax_return"
    BUDGET = "budget"

    # Technical documents
    TECHNICAL_SPEC = "technical_spec"
    USER_MANUAL = "user_manual"
    API_DOC = "api_doc"
    ARCHITECTURE = "architecture"

    # General
    GENERAL = "general"
    UNKNOWN = "unknown"


class FolderType(str, Enum):
    """Semantic type of a folder (what kind of grouping it represents)."""

    # Case/matter folders (expedientes)
    CASE = "case"  # Legal case, project case
    CLIENT_FOLDER = "client_folder"  # All docs for a client
    PROJECT = "project"  # Project folder
    MATTER = "matter"  # Legal matter

    # Organizational folders
    DEPARTMENT = "department"  # Department folder
    YEAR = "year"  # Year-based folder
    ARCHIVE = "archive"  # Archived items

    # Document type containers
    CONTRACTS_FOLDER = "contracts_folder"
    INVOICES_FOLDER = "invoices_folder"
    REPORTS_FOLDER = "reports_folder"

    # General
    GENERAL = "general"
    UNKNOWN = "unknown"


class DomainType(str, Enum):
    """Domain/area of a document or folder."""

    LEGAL = "legal"
    FISCAL = "fiscal"
    HR = "hr"
    FINANCE = "finance"
    SALES = "sales"
    MARKETING = "marketing"
    OPERATIONS = "operations"
    IT = "it"
    ENGINEERING = "engineering"
    COMPLIANCE = "compliance"
    GENERAL = "general"


class RelationshipEdgeType(str, Enum):
    """Types of structural relationships between documents."""

    # Containment relationships
    CONTAINS = "contains"  # Folder contains document
    CHILD_OF = "child_of"  # Subfolder of parent folder

    # Version relationships
    VERSION_OF = "version_of"  # Newer version of document
    SUPERSEDES = "supersedes"  # Replaces previous document
    AMENDS = "amends"  # Amendment to original

    # Association relationships
    RELATES_TO = "relates_to"  # General relation
    REFERENCES = "references"  # References another document
    DEPENDS_ON = "depends_on"  # Depends on another document
    SIBLING_OF = "sibling_of"  # Same parent/context

    # Temporal relationships
    FOLLOWS = "follows"  # Temporal sequence
    PRECEDES = "precedes"  # Temporal sequence


class FolderSemantics(BaseModel):
    """Semantic meaning of a folder based on its name and context."""

    folder_name: str
    folder_path: str

    # Inferred semantics
    department: Optional[str] = None  # HR, Legal, Finance, etc.
    year: Optional[int] = None  # Year if folder represents a year
    client: Optional[str] = None  # Client name if client folder
    project: Optional[str] = None  # Project name if project folder
    document_type_hint: Optional[str] = None  # Type of docs expected

    # Confidence
    confidence: float = 0.0

    class Config:
        use_enum_values = True


class DocumentRelationship(BaseModel):
    """A relationship between this document and another."""

    target_document_id: str
    relationship_type: RelationshipEdgeType
    strength: float = Field(default=0.5, ge=0.0, le=1.0)

    # Optional context
    context: Optional[str] = None
    inferred_from: Optional[str] = None  # How was this relationship detected?

    class Config:
        use_enum_values = True


class StructuralMetadata(BaseModel):
    """
    Structural metadata about a document.

    This captures WHERE, WHAT TYPE, and HOW RELATED - NOT the content.
    """

    # Identity
    document_id: str
    weaviate_document_id: Optional[str] = None

    # Semantic classification
    semantic_type: SemanticType = SemanticType.UNKNOWN
    domain: DomainType = DomainType.GENERAL

    # Location in hierarchy
    folder_path: str = ""
    folder_hierarchy: List[str] = Field(default_factory=list)  # e.g., ["/", "/Contracts", "/Contracts/ACME"]
    folder_semantics: Optional[FolderSemantics] = None
    site_id: Optional[str] = None
    site_name: Optional[str] = None
    connector_id: Optional[str] = None

    # Key properties (extracted from metadata, NOT content)
    key_properties: Dict[str, Any] = Field(default_factory=dict)
    # Examples: client_name, contract_date, author, document_number

    # Relationships with other documents
    relationships: List[DocumentRelationship] = Field(default_factory=list)

    # Temporal information
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None  # For temporal graph
    valid_to: Optional[datetime] = None  # NULL = currently valid

    # Structural description (for embedding)
    structural_description: str = ""

    # Importance/relevance score
    importance: float = Field(default=0.5, ge=0.0, le=1.0)

    # Tenant isolation
    tenant_id: str = ""

    class Config:
        use_enum_values = True

    def to_graph_properties(self) -> Dict[str, Any]:
        """Convert to properties dict for Apache AGE vertex."""
        return {
            "document_id": self.document_id,
            "weaviate_id": self.weaviate_document_id,
            "semantic_type": self.semantic_type,
            "domain": self.domain,
            "folder_path": self.folder_path,
            "tenant_id": self.tenant_id,
            "importance": self.importance,
            "structural_description": self.structural_description[:500],  # Limit
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            # Flatten key properties
            **{f"prop_{k}": str(v)[:200] for k, v in list(self.key_properties.items())[:10]},
        }


# =============================================================================
# INTENT AND REASONING MODELS
# =============================================================================


class StructuralEntities(BaseModel):
    """Entities extracted from a query for structural reasoning."""

    # Named entities
    client_names: List[str] = Field(default_factory=list)
    folder_names: List[str] = Field(default_factory=list)
    document_types: List[SemanticType] = Field(default_factory=list)
    folder_types: List[FolderType] = Field(default_factory=list)
    domains: List[DomainType] = Field(default_factory=list)

    # Target entity type (what is the query about?)
    target_entity: TargetEntity = TargetEntity.DOCUMENT

    # Temporal markers
    years: List[int] = Field(default_factory=list)
    date_references: List[str] = Field(default_factory=list)  # "last week", "this month"

    # Quantifiers
    count_requested: bool = False
    list_requested: bool = False
    exists_check: bool = False
    contents_requested: bool = False  # "what's in folder X"
    browse_requested: bool = False  # "show me the structure"

    # Relationship hints
    relationship_hints: List[str] = Field(default_factory=list)  # "related to", "version of"

    class Config:
        use_enum_values = True


class TemporalMarkers(BaseModel):
    """Temporal markers detected in a query."""

    # Point in time
    point_in_time: Optional[datetime] = None  # "on January 1st"

    # Time range
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    # Relative references
    relative_reference: Optional[str] = None  # "last week", "this month", "yesterday"

    # Comparison
    compare_times: List[datetime] = Field(default_factory=list)

    # Evolution/trend
    evolution_requested: bool = False
    granularity: str = "day"  # day, week, month, year


class MultiHopQuery(BaseModel):
    """Parsed multi-hop query with traversal plan."""

    # Starting point
    start_entity_type: str = ""
    start_entity_value: Optional[str] = None
    start_entity_filters: Dict[str, Any] = Field(default_factory=dict)

    # Hops to traverse
    hops: List[Dict[str, Any]] = Field(default_factory=list)
    # Each hop: {relationship_type, target_type, filters}

    # End result
    return_type: str = ""  # What to return: count, list, properties
    return_fields: List[str] = Field(default_factory=list)

    # Estimated complexity
    estimated_hops: int = 0


class Intent(BaseModel):
    """Detected intent of a query."""

    type: IntentType = IntentType.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # Target entity type (document, folder, or both)
    target_entity: TargetEntity = TargetEntity.DOCUMENT

    # Extracted structural entities
    entities: StructuralEntities = Field(default_factory=StructuralEntities)

    # Temporal markers (if any)
    temporal_markers: Optional[TemporalMarkers] = None

    # Multi-hop query plan (if applicable)
    multihop_query: Optional[MultiHopQuery] = None

    # Planning flags
    requires_content: bool = False
    requires_planning: bool = False
    estimated_complexity: int = 1  # 1-5 scale

    # Raw analysis
    reasoning: str = ""  # Explanation of why this intent was detected

    class Config:
        use_enum_values = True


# =============================================================================
# REASONING RESULTS
# =============================================================================


class CypherQueryResult(BaseModel):
    """Result of a Cypher query execution."""

    query: str
    success: bool = True
    error: Optional[str] = None

    # Raw results
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0

    # Aggregated results
    count: Optional[int] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)

    # Performance
    execution_time_ms: float = 0.0


class StructuralContext(BaseModel):
    """Structural context to pass to the LLM (instead of full documents)."""

    # Query result summary
    query_type: str = ""  # count, list, location, exists
    query_result: Dict[str, Any] = Field(default_factory=dict)

    # Entity type: what is this context about?
    # "document" = about documents/files
    # "folder" = about folders/expedientes/cases
    # "both" = about both (e.g., "documents in folder X")
    entity_type: str = "document"

    # Document/Item information (without content)
    # Note: These fields are named document_* for backwards compatibility
    # but when entity_type="folder", they contain folder information
    document_count: int = 0
    document_ids: List[str] = Field(default_factory=list)
    document_titles: List[str] = Field(default_factory=list)
    document_types: List[str] = Field(default_factory=list)

    # Location context
    folder_path: Optional[str] = None
    folder_hierarchy: List[str] = Field(default_factory=list)

    # Semantic context
    semantic_domain: Optional[str] = None
    semantic_types: List[str] = Field(default_factory=list)

    # Relationships
    related_documents: List[Dict[str, Any]] = Field(default_factory=list)

    # Additional metadata
    details: Dict[str, Any] = Field(default_factory=dict)

    def _get_entity_terminology(self) -> Dict[str, str]:
        """
        Get terminology based on entity type for dynamic labeling.

        Uses tenant-specific terminology if available in details,
        otherwise falls back to generic terms.

        This is domain-agnostic:
        - Law firm: expedientes, casos
        - Consulting: proyectos
        - Commercial: clientes
        - Construction: obras
        - Healthcare: pacientes
        """
        # Check details for more specific entity type (set by _build_folder_context)
        entity = self.details.get("entity_type", self.entity_type)

        # Check for tenant-specific terminology in details
        # This allows the tenant to define their own terms
        custom_singular = self.details.get("container_term_singular")
        custom_plural = self.details.get("container_term_plural")

        if entity == "folder":
            # Use custom terms if provided, otherwise generic "carpeta"
            singular = custom_singular or "carpeta"
            plural = custom_plural or "carpetas"
            return {
                "singular": singular,
                "plural": plural,
                "found": f"{plural.capitalize()} encontrados",
                "related": f"{plural.capitalize()} relacionados",
                "type_label": "tipo",
            }
        elif entity == "both":
            return {
                "singular": "elemento",
                "plural": "elementos",
                "found": "Elementos encontrados",
                "related": "Elementos relacionados",
                "type_label": "tipo",
            }
        else:  # document (default)
            return {
                "singular": "documento",
                "plural": "documentos",
                "found": "Documentos encontrados",
                "related": "Documentos relacionados",
                "type_label": "tipo",
            }

    def to_context_string(self) -> str:
        """Format as string for LLM context."""
        parts = ["## Contexto Estructural\n"]

        # Get dynamic terminology based on entity type
        terms = self._get_entity_terminology()

        if self.query_result:
            parts.append(f"**Resultado de consulta ({self.query_type}):**")
            for key, value in self.query_result.items():
                parts.append(f"  - {key}: {value}")

        if self.document_count > 0:
            parts.append(f"\n**{terms['found']}:** {self.document_count}")
            if self.document_titles:
                for i, title in enumerate(self.document_titles[:10], 1):
                    doc_type = self.document_types[i - 1] if i - 1 < len(self.document_types) else ""
                    parts.append(f"  {i}. {title} ({doc_type})" if doc_type else f"  {i}. {title}")
                if len(self.document_titles) > 10:
                    parts.append(f"  ... y {len(self.document_titles) - 10} más")

        if self.folder_path:
            parts.append(f"\n**Ubicación:** {self.folder_path}")

        if self.semantic_domain:
            parts.append(f"**Dominio:** {self.semantic_domain}")

        if self.related_documents:
            parts.append(f"\n**{terms['related']}:** {len(self.related_documents)}")

        return "\n".join(parts)


class LegalContext(BaseModel):
    """
    Legal context from the Legal Knowledge Graph.

    Provides information about applicable laws, articles, and legal domain
    without requiring RAG access to legal documents.
    """

    # Query type
    query_type: str = ""  # applicability, compliance, reference, document_laws

    # Applicable laws
    applicable_laws: List[Dict[str, Any]] = Field(default_factory=list)
    # Each: {boe_id, title, short_name, domain, status}

    # Relevant articles
    relevant_articles: List[Dict[str, Any]] = Field(default_factory=list)
    # Each: {article_id, law_boe_id, article_number, title, summary, key_concepts}

    # Legal domain detected
    legal_domain: Optional[str] = None  # labor, fiscal, privacy, etc.

    # Specific law being referenced (if any)
    referenced_law: Optional[Dict[str, Any]] = None
    referenced_article: Optional[Dict[str, Any]] = None

    # Compliance hints
    compliance_requirements: List[str] = Field(default_factory=list)
    potential_issues: List[str] = Field(default_factory=list)

    # Confidence in legal context
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    def to_context_string(self) -> str:
        """Format as string for LLM context."""
        parts = ["## Contexto Legal\n"]

        if self.legal_domain:
            parts.append(f"**Dominio legal:** {self.legal_domain}")

        if self.applicable_laws:
            parts.append(f"\n**Legislación aplicable:**")
            for law in self.applicable_laws[:5]:
                parts.append(
                    f"  - {law.get('short_name', 'N/A')}: {law.get('title', 'Sin título')}"
                )
                if law.get('boe_id'):
                    parts.append(f"    BOE: {law['boe_id']}")
            if len(self.applicable_laws) > 5:
                parts.append(f"  ... y {len(self.applicable_laws) - 5} más")

        if self.relevant_articles:
            parts.append(f"\n**Artículos relevantes:**")
            for art in self.relevant_articles[:5]:
                law_name = art.get('law_short_name', art.get('law_boe_id', ''))
                parts.append(f"  - Art. {art.get('article_number', 'N/A')} {law_name}")
                if art.get('summary'):
                    parts.append(f"    {art['summary'][:100]}...")
            if len(self.relevant_articles) > 5:
                parts.append(f"  ... y {len(self.relevant_articles) - 5} más")

        if self.referenced_law:
            parts.append(f"\n**Ley referenciada:**")
            parts.append(f"  {self.referenced_law.get('short_name')}: {self.referenced_law.get('title')}")

        if self.compliance_requirements:
            parts.append(f"\n**Requisitos de cumplimiento:**")
            for req in self.compliance_requirements[:5]:
                parts.append(f"  • {req}")

        if self.potential_issues:
            parts.append(f"\n**⚠️ Posibles problemas:**")
            for issue in self.potential_issues[:3]:
                parts.append(f"  • {issue}")

        return "\n".join(parts)


class TemporalResult(BaseModel):
    """Result of temporal reasoning."""

    query_type: str = ""  # point_in_time, range, evolution, diff

    # Point in time query
    state_at_time: Optional[Dict[str, Any]] = None

    # Range query
    changes: List[Dict[str, Any]] = Field(default_factory=list)
    added_count: int = 0
    modified_count: int = 0
    deleted_count: int = 0

    # Evolution timeline
    timeline: List[Dict[str, Any]] = Field(default_factory=list)

    # Structure diff
    diff: Optional[Dict[str, Any]] = None

    # Performance
    execution_time_ms: float = 0.0


class MultiHopResult(BaseModel):
    """Result of multi-hop query execution."""

    # Query info
    hops_traversed: int = 0
    path_explanation: str = ""

    # Results
    results: List[Dict[str, Any]] = Field(default_factory=list)
    result_count: int = 0

    # Performance
    execution_time_ms: float = 0.0


class ReasoningResult(BaseModel):
    """Complete result of pre-LLM reasoning."""

    # Reasoning type applied
    type: ReasoningType = ReasoningType.FULL_RAG

    # Structural context (always populated)
    structural_context: Optional[StructuralContext] = None

    # For STRUCTURAL reasoning
    cypher_result: Optional[CypherQueryResult] = None

    # For TEMPORAL reasoning
    temporal_result: Optional[TemporalResult] = None

    # For MULTIHOP reasoning
    multihop_result: Optional[MultiHopResult] = None

    # For LEGAL reasoning
    legal_context: Optional[LegalContext] = None

    # For FOCUSED_RAG reasoning
    target_document_ids: List[str] = Field(default_factory=list)
    rag_scope: str = "full_corpus"  # full_corpus, focused, single_document

    # Flags
    requires_rag: bool = True
    requires_llm_interpretation: bool = True

    # Debug/explanation
    reasoning_explanation: str = ""
    processing_time_ms: float = 0.0

    class Config:
        use_enum_values = True


class QueryPlan(BaseModel):
    """Plan for executing a multi-hop query."""

    # Original query
    original_query: str

    # Decomposed hops
    hops: List[Dict[str, Any]] = Field(default_factory=list)

    # Generated Cypher
    cypher: str = ""

    # Complexity estimation
    estimated_complexity: int = 1
    estimated_time_ms: int = 500

    # Optimization notes
    optimization_notes: List[str] = Field(default_factory=list)


class StructuralQueryResult(BaseModel):
    """Complete result of a structural query (combines all components)."""

    # Query info
    original_query: str
    detected_intent: Intent

    # Reasoning result
    reasoning_result: ReasoningResult

    # Final answer (if fully answered structurally)
    answer: Optional[str] = None
    answer_confidence: float = 0.0

    # For LLM processing
    context_for_llm: Optional[str] = None
    tokens_saved: int = 0  # Estimated tokens saved vs full RAG

    # Performance
    total_processing_time_ms: float = 0.0
    breakdown: Dict[str, float] = Field(default_factory=dict)

    # Status
    success: bool = True
    error: Optional[str] = None
