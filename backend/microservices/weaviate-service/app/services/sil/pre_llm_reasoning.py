"""
Pre-LLM Reasoning Engine

The core of the Structural Intelligence Layer.
Processes queries BEFORE they reach the LLM to determine:
1. Can this be answered structurally (without reading documents)?
2. If content is needed, which specific documents?
3. What structural context should accompany the LLM prompt?

This engine significantly reduces token usage by:
- Answering structural questions directly via Cypher
- Focusing RAG on specific documents when content IS needed
- Providing rich structural context to the LLM

Typical Flow:
┌──────────────────────────────────────────────────────────────────┐
│  User Query                                                       │
│       │                                                           │
│       ▼                                                           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐        │
│  │   Intent     │ →  │   Cypher     │ →  │   Execute    │        │
│  │   Detector   │    │   Builder    │    │   Query      │        │
│  └──────────────┘    └──────────────┘    └──────────────┘        │
│       │                                         │                 │
│       ▼                                         ▼                 │
│  ┌──────────────┐                      ┌──────────────┐          │
│  │  Structural? │  YES →               │  Graph       │          │
│  │              │ ─────────────────────│  Result      │──→ Done  │
│  └──────────────┘                      └──────────────┘          │
│       │ NO (Content needed)                                       │
│       ▼                                                           │
│  ┌──────────────┐    ┌──────────────┐                            │
│  │  Locate Docs │ →  │  Focused     │ → RAG (specific docs only) │
│  │  (Cypher)    │    │  RAG         │                            │
│  └──────────────┘    └──────────────┘                            │
└──────────────────────────────────────────────────────────────────┘
"""

import logging
import time
from typing import Optional, List, Dict, Any, Union, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from app.services.tenant_knowledge_service import TenantKnowledgeService

from .schemas import (
    Intent,
    IntentType,
    ReasoningType,
    ReasoningResult,
    StructuralContext,
    CypherQueryResult,
    StructuralEntities,
    LegalContext,
    FolderType,
    TargetEntity,
)
from .intent_detector import IntentDetector, intent_detector
from .cypher_builder import CypherBuilder, cypher_builder


class CypherQueryError(Exception):
    """Exception raised when a Cypher query fails."""

    def __init__(self, message: str, query: str = "", original_error: str = ""):
        super().__init__(message)
        self.query = query
        self.original_error = original_error
from .legal_graph_service import LegalGraphService, legal_graph, LegalDomain
from ...services.knowledge.age_graph_service import AGEKnowledgeGraphService, age_knowledge_graph
from ...core.config import settings

logger = logging.getLogger(__name__)


def _get_enum_value(obj: Union[Enum, str, None]) -> str:
    """Safely get the value from an enum or return the string directly.

    This handles the case where Pydantic's use_enum_values=True has already
    converted an enum to its string value.

    IMPORTANT: Check Enum BEFORE str because string enums (class X(str, Enum))
    satisfy both isinstance(obj, str) and isinstance(obj, Enum), but we need
    to use .value for correct extraction.
    """
    if obj is None:
        return ""
    # Check Enum FIRST - string enums (str, Enum) satisfy both str and Enum checks
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, str):
        return obj
    if hasattr(obj, 'value'):
        return obj.value
    return str(obj)


class PreLLMReasoningEngine:
    """
    Pre-LLM Reasoning Engine.

    Processes queries before the LLM to:
    1. Detect if the query is structural (can be answered from graph)
    2. Execute structural queries via Cypher
    3. Build structural context for the LLM
    4. Identify target documents for focused RAG
    """

    def __init__(
        self,
        detector: Optional[IntentDetector] = None,
        builder: Optional[CypherBuilder] = None,
        graph_service: Optional[AGEKnowledgeGraphService] = None,
        legal_graph_service: Optional[LegalGraphService] = None,
    ):
        self._detector = detector or intent_detector
        self._builder = builder or cypher_builder
        self._graph = graph_service or age_knowledge_graph
        self._legal_graph = legal_graph_service or legal_graph
        self._initialized = False

        # Legal domain detection keywords
        self._legal_keywords = {
            "labor": ["laboral", "trabajo", "trabajador", "despido", "nómina", "contrato de trabajo",
                      "estatuto", "convenio", "horario", "jornada", "vacaciones", "horas extra"],
            "fiscal": ["fiscal", "impuesto", "iva", "irpf", "tributario", "hacienda", "factura",
                       "declaración", "tributo", "retención"],
            "privacy": ["rgpd", "gdpr", "lopd", "datos personales", "privacidad", "consentimiento",
                        "protección de datos", "derecho al olvido"],
            "civil": ["civil", "responsabilidad", "daños", "contrato civil", "obligaciones"],
            "mercantile": ["mercantil", "sociedad", "empresa", "comercio", "societario"],
            "compliance": ["cumplimiento", "compliance", "auditoria", "normativa"],
            "real_estate": ["arrendamiento", "alquiler", "hipoteca", "inmueble", "vivienda", "lau"],
        }

    async def initialize(self) -> None:
        """Initialize the reasoning engine."""
        if self._initialized:
            return

        await self._detector.initialize()
        await self._builder.initialize()
        await self._graph.initialize()
        await self._legal_graph.initialize()

        self._initialized = True
        logger.info("✅ PreLLMReasoningEngine initialized (with Legal Knowledge Graph)")

    async def process_query(
        self,
        query: str,
        tenant_id: str,
        knowledge_service: Optional["TenantKnowledgeService"] = None,
    ) -> ReasoningResult:
        """
        Process a query with structural intelligence.

        Args:
            query: The user's query
            tenant_id: Tenant identifier
            knowledge_service: Optional service to query SIL for terminology

        Returns:
            ReasoningResult with structural context and/or target documents
        """
        start_time = time.time()

        await self.initialize()

        # Step 1: Detect intent (queries SIL directly for terminology)
        intent = await self._detector.detect_intent(
            query=query,
            tenant_id=tenant_id,
            knowledge_service=knowledge_service,
        )

        logger.info(
            f"🧠 Intent detected: {_get_enum_value(intent.type)} "
            f"(confidence: {intent.confidence:.2f})"
        )

        # Step 2: Route based on intent type
        if self._is_folder_query(intent):
            # Query about folders/expedientes - use folder graph
            result = await self._answer_folder_query(intent, tenant_id)
        elif self._is_purely_structural(intent):
            # Can answer from graph alone (documents)
            result = await self._answer_structurally(intent, tenant_id)
        elif self._is_legal(intent):
            # Legal query - use Legal Knowledge Graph
            result = await self._answer_legally(intent, query, tenant_id)
        elif self._is_temporal(intent):
            # Temporal query
            result = await self._answer_temporally(intent, tenant_id)
        elif self._is_multihop(intent):
            # Multi-hop traversal
            result = await self._answer_multihop(intent, tenant_id)
        elif self._is_focused_content(intent):
            # Need content, but from specific documents
            result = await self._prepare_focused_rag(intent, tenant_id)
        else:
            # Full RAG needed
            result = self._prepare_full_rag(intent, tenant_id)

        # Step 3: Enrich with legal context if applicable
        if not self._is_legal(intent) and self._query_mentions_law(query):
            result = await self._enrich_with_legal_context(result, query, tenant_id)

        result.processing_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"  Reasoning type: {_get_enum_value(result.type)}, "
            f"requires_rag: {result.requires_rag}, "
            f"time: {result.processing_time_ms:.0f}ms"
        )

        return result

    def _is_purely_structural(self, intent: Intent) -> bool:
        """Check if query can be answered from structure alone."""
        structural_intents = {
            IntentType.STRUCTURAL,
            IntentType.STRUCTURAL_COUNT,
            IntentType.STRUCTURAL_LIST,
            IntentType.STRUCTURAL_EXISTS,
            IntentType.STRUCTURAL_LOCATION,
        }
        return intent.type in structural_intents and not intent.requires_content

    def _is_temporal(self, intent: Intent) -> bool:
        """Check if query involves temporal reasoning."""
        temporal_intents = {
            IntentType.TEMPORAL_POINT,
            IntentType.TEMPORAL_RANGE,
            IntentType.TEMPORAL_EVOLUTION,
            IntentType.TEMPORAL_COMPARISON,
        }
        return intent.type in temporal_intents

    def _is_multihop(self, intent: Intent) -> bool:
        """Check if query requires multi-hop traversal."""
        return intent.type in {IntentType.MULTIHOP_SIMPLE, IntentType.MULTIHOP_COMPLEX}

    def _is_focused_content(self, intent: Intent) -> bool:
        """Check if we need content but from specific documents."""
        return intent.type == IntentType.CONTENT_SPECIFIC

    def _is_folder_query(self, intent: Intent) -> bool:
        """Check if query is about folders/expedientes (not documents)."""
        folder_intents = {
            IntentType.FOLDER_COUNT,
            IntentType.FOLDER_LIST,
            IntentType.FOLDER_EXISTS,
            IntentType.FOLDER_CONTENTS,
            IntentType.FOLDER_BROWSE,
        }
        return intent.type in folder_intents or intent.target_entity in (TargetEntity.FOLDER, TargetEntity.BOTH)

    def _is_legal(self, intent: Intent) -> bool:
        """Check if query is about legal applicability or compliance."""
        legal_intents = {
            IntentType.LEGAL_APPLICABILITY,
            IntentType.LEGAL_COMPLIANCE,
            IntentType.LEGAL_REFERENCE,
            IntentType.LEGAL_DOCUMENT_LAWS,
        }
        return intent.type in legal_intents

    def _detect_legal_domain(self, query: str) -> Optional[str]:
        """
        Detect legal domain from query text.

        Returns the detected legal domain or None if no specific domain.
        """
        query_lower = query.lower()

        for domain, keywords in self._legal_keywords.items():
            if any(kw in query_lower for kw in keywords):
                return domain

        return None

    def _query_mentions_law(self, query: str) -> bool:
        """Check if query mentions specific laws or legal concepts."""
        query_lower = query.lower()

        # Check for BOE references
        if "boe" in query_lower:
            return True

        # Check for law names
        law_patterns = [
            "estatuto de los trabajadores", "et ",
            "rgpd", "gdpr", "lopd",
            "ley de", "real decreto",
            "código civil", "código penal",
            "artículo", "art.",
            "ley orgánica",
            "cumplir", "cumplimiento",
            "legal", "legislación",
            "normativa", "regulación",
        ]

        return any(pattern in query_lower for pattern in law_patterns)

    async def _answer_structurally(
        self,
        intent: Intent,
        tenant_id: str,
    ) -> ReasoningResult:
        """
        Answer a purely structural query from the graph.

        No RAG needed - the graph contains all the information.
        """
        # Build and execute Cypher query
        cypher_query = self._builder.build_query(intent, tenant_id)
        cypher_result = await self._execute_cypher(cypher_query, tenant_id)

        # Build structural context
        structural_context = self._build_structural_context(
            intent=intent,
            cypher_result=cypher_result,
        )

        return ReasoningResult(
            type=ReasoningType.STRUCTURAL,
            structural_context=structural_context,
            cypher_result=cypher_result,
            requires_rag=False,
            requires_llm_interpretation=True,  # LLM still formats the answer
            reasoning_explanation=(
                f"Query answered structurally via Cypher. "
                f"Found {cypher_result.row_count} results."
            ),
        )

    async def _answer_folder_query(
        self,
        intent: Intent,
        tenant_id: str,
    ) -> ReasoningResult:
        """
        Answer a query about folders/expedientes from the structural graph.

        Handles:
        - FOLDER_COUNT: "How many expedientes do we have?"
        - FOLDER_LIST: "List all expedientes for client X"
        - FOLDER_EXISTS: "Is there an expediente for ACME?"
        - FOLDER_CONTENTS: "What's in expediente X?"
        - FOLDER_BROWSE: "Show me the folder structure"
        """
        # Get tenant-specific container terminology (learned from data)
        from app.services.tenant_knowledge_service import tenant_knowledge_service
        try:
            singular, plural = await tenant_knowledge_service.get_primary_container_terminology(tenant_id)
        except Exception:
            singular, plural = "carpeta", "carpetas"

        # Build and execute Cypher query for folders
        cypher_query = self._builder.build_query(intent, tenant_id)
        cypher_result = await self._execute_cypher(cypher_query, tenant_id)

        # Build folder-specific context with learned terminology
        structural_context = self._build_folder_context(
            intent=intent,
            cypher_result=cypher_result,
            container_singular=singular,
            container_plural=plural,
        )

        # For FOLDER_CONTENTS, we might need to include document info
        requires_content = intent.type == IntentType.FOLDER_CONTENTS and intent.requires_content

        return ReasoningResult(
            type=ReasoningType.STRUCTURAL,  # Folder queries are still structural
            structural_context=structural_context,
            cypher_result=cypher_result,
            target_document_ids=[
                row.get("document_id") for row in cypher_result.rows
                if row.get("document_id")
            ] if requires_content else [],
            requires_rag=requires_content,
            requires_llm_interpretation=True,
            reasoning_explanation=(
                f"Folder query answered from structural graph. "
                f"Intent: {_get_enum_value(intent.type)}, "
                f"Found {cypher_result.row_count} results."
            ),
        )

    def _build_folder_context(
        self,
        intent: Intent,
        cypher_result: CypherQueryResult,
        container_singular: str = "carpeta",
        container_plural: str = "carpetas",
    ) -> StructuralContext:
        """Build context specifically for folder queries."""
        context = StructuralContext()
        # Set entity_type for dynamic terminology in to_context_string()
        context.entity_type = "folder"

        # Store learned terminology for downstream use
        context.details = {
            "entity_type": "folder",
            "container_term_singular": container_singular,
            "container_term_plural": container_plural,
        }

        # Determine query type based on intent
        intent_type = _get_enum_value(intent.type)

        if intent.type == IntentType.FOLDER_COUNT:
            context.query_type = "folder_count"
            if cypher_result.count is not None:
                context.query_result = {"count": cypher_result.count, "entity": container_plural}
            elif cypher_result.rows and "total" in cypher_result.rows[0]:
                context.query_result = {"count": cypher_result.rows[0]["total"], "entity": container_plural}
            else:
                context.query_result = {"count": cypher_result.row_count, "entity": container_plural}

        elif intent.type == IntentType.FOLDER_LIST:
            context.query_type = "folder_list"
            context.query_result = {
                "count": cypher_result.row_count,
                "entity": container_plural,
                "items": cypher_result.rows[:20],
            }

        elif intent.type == IntentType.FOLDER_EXISTS:
            context.query_type = "folder_exists"
            exists = cypher_result.row_count > 0
            if cypher_result.rows and "folder_exists" in cypher_result.rows[0]:
                exists = cypher_result.rows[0]["folder_exists"]
            context.query_result = {
                "exists": exists,
                "count": cypher_result.row_count,
                "entity": container_singular,
            }

        elif intent.type == IntentType.FOLDER_CONTENTS:
            context.query_type = "folder_contents"
            # Extract folder info and documents from query result
            if cypher_result.rows:
                first_row = cypher_result.rows[0]
                context.folder_path = first_row.get("folder_path", "")
                context.query_result = {
                    "folder_name": first_row.get("folder_name", ""),
                    "folder_path": first_row.get("folder_path", ""),
                    "folder_type": first_row.get("folder_type", ""),
                    "total_documents": first_row.get("total_documents", 0),
                    "documents": first_row.get("documents", []),
                }

        elif intent.type == IntentType.FOLDER_BROWSE:
            context.query_type = "folder_structure"
            context.query_result = {
                "count": cypher_result.row_count,
                "structure": cypher_result.rows,
            }

        else:
            context.query_type = "folder_general"
            context.query_result = {
                "count": cypher_result.row_count,
                "items": cypher_result.rows[:20],
            }

        # Extract folder names for reference
        folder_names = []
        folder_paths = []
        for row in cypher_result.rows:
            if row.get("name"):
                folder_names.append(row["name"])
            if row.get("folder_name"):
                folder_names.append(row["folder_name"])
            if row.get("path"):
                folder_paths.append(row["path"])
            if row.get("folder_path"):
                folder_paths.append(row["folder_path"])

        context.folder_hierarchy = list(set(folder_paths))[:10]

        # Merge folder details into existing details (preserve terminology!)
        # IMPORTANT: Don't overwrite - context.details already has container_term_* from earlier
        context.details.update({
            "folder_names": list(set(folder_names))[:10],
            "intent_type": intent_type,
        })

        return context

    async def _answer_temporally(
        self,
        intent: Intent,
        tenant_id: str,
    ) -> ReasoningResult:
        """
        Answer a temporal query using the temporal aspects of the graph.
        """
        # Build temporal Cypher query
        cypher_query = self._builder.build_query(intent, tenant_id)
        cypher_result = await self._execute_cypher(cypher_query, tenant_id)

        # Build temporal context
        structural_context = self._build_temporal_context(
            intent=intent,
            cypher_result=cypher_result,
        )

        return ReasoningResult(
            type=ReasoningType.TEMPORAL,
            structural_context=structural_context,
            cypher_result=cypher_result,
            requires_rag=False,
            requires_llm_interpretation=True,
            reasoning_explanation=(
                f"Temporal query answered from graph. "
                f"Found {cypher_result.row_count} temporal results."
            ),
        )

    async def _answer_multihop(
        self,
        intent: Intent,
        tenant_id: str,
    ) -> ReasoningResult:
        """
        Answer a multi-hop query by traversing the graph.
        """
        # Build multi-hop Cypher query
        cypher_query = self._builder.build_query(intent, tenant_id)
        cypher_result = await self._execute_cypher(cypher_query, tenant_id)

        # Build structural context with traversal info
        structural_context = self._build_multihop_context(
            intent=intent,
            cypher_result=cypher_result,
        )

        # Multi-hop queries might still need focused RAG for content
        needs_content = intent.requires_content

        return ReasoningResult(
            type=ReasoningType.MULTIHOP if not needs_content else ReasoningType.HYBRID,
            structural_context=structural_context,
            cypher_result=cypher_result,
            target_document_ids=[
                row.get("document_id") for row in cypher_result.rows
                if row.get("document_id")
            ] if needs_content else [],
            requires_rag=needs_content,
            rag_scope="focused" if needs_content else "none",
            requires_llm_interpretation=True,
            reasoning_explanation=(
                f"Multi-hop traversal completed with {intent.multihop_query.estimated_hops if intent.multihop_query else 'N/A'} hops. "
                f"Found {cypher_result.row_count} results."
            ),
        )

    async def _prepare_focused_rag(
        self,
        intent: Intent,
        tenant_id: str,
    ) -> ReasoningResult:
        """
        Prepare for focused RAG by identifying specific target documents.

        Instead of searching the entire corpus, we:
        1. Use the graph to find relevant documents structurally
        2. Pass only those document IDs to RAG
        3. Include structural context for the LLM
        """
        # First, locate documents structurally
        cypher_query = self._builder.build_query(intent, tenant_id)
        cypher_result = await self._execute_cypher(cypher_query, tenant_id)

        # Extract document IDs for focused RAG
        target_doc_ids = [
            row.get("document_id") for row in cypher_result.rows
            if row.get("document_id")
        ]

        # Build structural context
        structural_context = self._build_structural_context(
            intent=intent,
            cypher_result=cypher_result,
        )

        return ReasoningResult(
            type=ReasoningType.FOCUSED_RAG,
            structural_context=structural_context,
            cypher_result=cypher_result,
            target_document_ids=target_doc_ids,
            requires_rag=True,
            rag_scope="focused",
            requires_llm_interpretation=True,
            reasoning_explanation=(
                f"Content needed from {len(target_doc_ids)} specific documents. "
                f"RAG will be focused on these documents only."
            ),
        )

    def _prepare_full_rag(
        self,
        intent: Intent,
        tenant_id: str,
    ) -> ReasoningResult:
        """
        Prepare for full RAG when structural filtering isn't sufficient.
        """
        # Still build some structural context if we have entities
        structural_context = StructuralContext(
            query_type="general",
            query_result={"intent": _get_enum_value(intent.type)},
            details={"entities": self._entities_to_dict(intent.entities)},
        )

        return ReasoningResult(
            type=ReasoningType.FULL_RAG,
            structural_context=structural_context,
            requires_rag=True,
            rag_scope="full_corpus",
            requires_llm_interpretation=True,
            reasoning_explanation=(
                f"Full corpus search needed. Intent: {_get_enum_value(intent.type)}"
            ),
        )

    async def _answer_legally(
        self,
        intent: Intent,
        query: str,
        tenant_id: str,
    ) -> ReasoningResult:
        """
        Answer a legal query using the Legal Knowledge Graph.

        Provides applicable laws, articles, and compliance context
        without requiring RAG for legal content.
        """
        legal_context = LegalContext()

        # Detect legal domain from query
        legal_domain = self._detect_legal_domain(query)
        if legal_domain:
            legal_context.legal_domain = legal_domain

        # Handle different legal intent types
        intent_type = _get_enum_value(intent.type)

        if intent_type == "legal_applicability":
            # What laws apply to a document type/domain?
            legal_context.query_type = "applicability"

            # Extract document type from entities if available
            doc_types = intent.entities.document_types
            doc_type = _get_enum_value(doc_types[0]) if doc_types else None

            # Find applicable laws
            laws = await self._legal_graph.find_applicable_laws_for_domain(
                document_type=doc_type,
                domain=legal_domain,
            )
            legal_context.applicable_laws = laws
            legal_context.confidence = 0.8 if laws else 0.3

        elif intent_type == "legal_compliance":
            # Does document comply with specific law?
            legal_context.query_type = "compliance"

            # Try to extract law reference from query
            law_ref = self._extract_law_reference(query)
            if law_ref:
                law = await self._legal_graph.get_law(law_ref)
                if law:
                    legal_context.referenced_law = law
                    # Get relevant articles
                    articles = await self._legal_graph.get_articles_for_law(law_ref)
                    legal_context.relevant_articles = articles
                    legal_context.confidence = 0.9

            # Add compliance hints based on domain
            if legal_domain:
                hints = self._get_compliance_hints(legal_domain)
                legal_context.compliance_requirements = hints

        elif intent_type == "legal_reference":
            # Query about specific law/article
            legal_context.query_type = "reference"

            law_ref = self._extract_law_reference(query)
            if law_ref:
                law = await self._legal_graph.get_law(law_ref)
                if law:
                    legal_context.referenced_law = law
                    legal_context.applicable_laws = [law]

                    # Try to find specific article
                    article_num = self._extract_article_number(query)
                    if article_num:
                        articles = await self._legal_graph.get_articles_for_law(law_ref)
                        for art in articles:
                            if art.get("article_number") == article_num:
                                legal_context.referenced_article = art
                                break

                    legal_context.confidence = 0.95

        elif intent_type == "legal_document_laws":
            # What laws govern a specific document?
            legal_context.query_type = "document_laws"

            # This requires document context - would need document_id
            # For now, infer from document type/domain
            doc_types = intent.entities.document_types
            doc_type = _get_enum_value(doc_types[0]) if doc_types else None

            laws = await self._legal_graph.find_applicable_laws_for_domain(
                document_type=doc_type,
                domain=legal_domain,
            )
            legal_context.applicable_laws = laws
            legal_context.confidence = 0.7 if laws else 0.3

        # Build structural context for non-legal aspects
        structural_context = StructuralContext(
            query_type=f"legal_{legal_context.query_type}",
            query_result={
                "legal_domain": legal_domain,
                "laws_found": len(legal_context.applicable_laws),
            },
            details={"entities": self._entities_to_dict(intent.entities)},
        )

        return ReasoningResult(
            type=ReasoningType.LEGAL,
            structural_context=structural_context,
            legal_context=legal_context,
            requires_rag=False,  # Legal context from graph is sufficient
            requires_llm_interpretation=True,
            reasoning_explanation=(
                f"Legal query answered from Legal Knowledge Graph. "
                f"Domain: {legal_domain or 'general'}, "
                f"Laws found: {len(legal_context.applicable_laws)}"
            ),
        )

    async def _enrich_with_legal_context(
        self,
        result: ReasoningResult,
        query: str,
        tenant_id: str,
    ) -> ReasoningResult:
        """
        Enrich an existing reasoning result with legal context.

        Called when a non-legal query mentions laws or legal concepts.
        """
        legal_context = LegalContext()

        # Detect domain from query
        legal_domain = self._detect_legal_domain(query)
        if legal_domain:
            legal_context.legal_domain = legal_domain

        # Try to find applicable laws based on detected domain and document types
        doc_types = []
        if result.structural_context and result.structural_context.document_types:
            doc_types = result.structural_context.document_types

        doc_type = doc_types[0] if doc_types else None

        # Get applicable laws
        laws = await self._legal_graph.find_applicable_laws_for_domain(
            document_type=doc_type,
            domain=legal_domain,
        )

        if laws:
            legal_context.applicable_laws = laws
            legal_context.confidence = 0.6  # Lower confidence for enrichment

        # Check for specific law reference
        law_ref = self._extract_law_reference(query)
        if law_ref:
            law = await self._legal_graph.get_law(law_ref)
            if law:
                legal_context.referenced_law = law
                legal_context.confidence = 0.8

        # Only add legal context if we found something useful
        if legal_context.applicable_laws or legal_context.referenced_law:
            result.legal_context = legal_context

            # Update reasoning type to indicate enrichment
            if result.type == ReasoningType.STRUCTURAL:
                result.type = ReasoningType.LEGAL_ENRICHED
            elif result.type == ReasoningType.FOCUSED_RAG:
                result.type = ReasoningType.HYBRID

            result.reasoning_explanation += (
                f" | Legal context added: {len(legal_context.applicable_laws)} applicable laws."
            )

        return result

    def _extract_law_reference(self, query: str) -> Optional[str]:
        """
        Extract a BOE law reference from query.

        Returns BOE ID (e.g., 'BOE-A-2015-11430') if found.
        """
        import re

        query_lower = query.lower()

        # Direct BOE reference
        boe_match = re.search(r'boe-[a-z]-\d{4}-\d+', query_lower)
        if boe_match:
            return boe_match.group(0).upper()

        # Common law abbreviations to BOE ID mapping
        law_abbrevs = {
            "estatuto de los trabajadores": "BOE-A-2015-11430",
            " et ": "BOE-A-2015-11430",
            "rgpd": "BOE-A-2018-16673",
            "lopd": "BOE-A-2018-16673",
            "ley de prevención de riesgos laborales": "BOE-A-1995-24292",
            "lprl": "BOE-A-1995-24292",
            "código civil": "BOE-A-1889-4763",
            "ley general tributaria": "BOE-A-2003-23186",
            "lgt": "BOE-A-2003-23186",
            "ley de arrendamientos urbanos": "BOE-A-1994-26003",
            "lau": "BOE-A-1994-26003",
            "ley de sociedades de capital": "BOE-A-2010-10544",
            "lsc": "BOE-A-2010-10544",
        }

        for pattern, boe_id in law_abbrevs.items():
            if pattern in query_lower:
                return boe_id

        return None

    def _extract_article_number(self, query: str) -> Optional[str]:
        """Extract article number from query."""
        import re

        # Match patterns like "Art. 34", "artículo 34", "art 34.1"
        patterns = [
            r'art[íi]culo\s+(\d+(?:\.\d+)?(?:\s*bis)?)',
            r'art\.?\s*(\d+(?:\.\d+)?(?:\s*bis)?)',
        ]

        query_lower = query.lower()
        for pattern in patterns:
            match = re.search(pattern, query_lower)
            if match:
                return match.group(1).strip()

        return None

    def _get_compliance_hints(self, domain: str) -> List[str]:
        """Get compliance hints for a legal domain."""
        hints = {
            "labor": [
                "Verificar límites de jornada laboral (40h/semana, Art. 34 ET)",
                "Comprobar período de prueba según categoría",
                "Verificar cláusulas de no competencia",
                "Revisar condiciones de despido",
            ],
            "fiscal": [
                "Verificar tipo de IVA aplicado",
                "Comprobar retenciones de IRPF",
                "Revisar datos fiscales obligatorios en facturas",
            ],
            "privacy": [
                "Verificar cláusula de protección de datos",
                "Comprobar base legal del tratamiento",
                "Revisar derechos ARCO/ARSULIPO",
                "Verificar consentimiento explícito si aplica",
            ],
            "real_estate": [
                "Verificar duración mínima del contrato (LAU)",
                "Comprobar fianza legal",
                "Revisar cláusulas de actualización de renta",
            ],
        }
        return hints.get(domain, [])

    async def _execute_cypher(
        self,
        cypher_query: str,
        tenant_id: str,
    ) -> CypherQueryResult:
        """Execute a Cypher query against the structural graph."""
        start_time = time.time()

        try:
            # Parse the query to determine return columns
            # This is a simplified approach - in production, parse properly
            return_columns = self._extract_return_columns(cypher_query)

            logger.debug(f"🔍 Cypher query: {cypher_query}")
            logger.debug(f"🔍 Return columns: {return_columns}")

            async with self._graph._get_connection() as conn:
                results = await self._graph._execute_cypher(
                    conn,
                    cypher_query,
                    return_columns,
                )

                execution_time = (time.time() - start_time) * 1000

                logger.debug(f"🔍 Raw Cypher results: {results}")

                # Process results
                rows = results if results else []

                # Check for count result
                count = None
                if rows and "total" in rows[0]:
                    count = rows[0]["total"]
                    logger.debug(f"🔍 Found 'total' in row[0]: {count} (type: {type(count)})")
                elif rows and "count" in rows[0]:
                    count = rows[0]["count"]
                    logger.debug(f"🔍 Found 'count' in row[0]: {count} (type: {type(count)})")

                return CypherQueryResult(
                    query=cypher_query,
                    success=True,
                    rows=rows,
                    row_count=len(rows),
                    count=count,
                    items=rows,
                    execution_time_ms=execution_time,
                )

        except Exception as e:
            logger.error(f"Cypher query failed: {e}")
            raise CypherQueryError(
                message=f"Structural query failed: {e}",
                query=cypher_query,
                original_error=str(e),
            )

    def _extract_return_columns(self, cypher_query: str) -> List[tuple]:
        """
        Extract return column specifications from a Cypher query.

        This is a simplified parser - in production, use proper parsing.
        """
        import re

        # Find the RETURN clause
        return_match = re.search(
            r"RETURN\s+(.+?)(?:ORDER BY|LIMIT|$)",
            cypher_query,
            re.IGNORECASE | re.DOTALL,
        )

        if not return_match:
            return [("result", "agtype")]

        return_clause = return_match.group(1).strip()

        # Split by comma, handling AS aliases
        columns = []
        for col in return_clause.split(","):
            col = col.strip()

            # Check for alias
            alias_match = re.search(r"\s+as\s+(\w+)\s*$", col, re.IGNORECASE)
            if alias_match:
                col_name = alias_match.group(1)
            else:
                # Extract simple name
                col_name = re.sub(r"[^\w]", "_", col.split(".")[-1])

            columns.append((col_name, "agtype"))

        return columns if columns else [("result", "agtype")]

    def _build_structural_context(
        self,
        intent: Intent,
        cypher_result: CypherQueryResult,
    ) -> StructuralContext:
        """Build structural context from query results."""
        context = StructuralContext()

        # Determine query type and actual count
        # For count queries, use the COUNT result, not row_count
        actual_count = cypher_result.row_count  # Default for non-count queries

        if intent.entities.count_requested:
            context.query_type = "count"
            # Use the actual count value from the Cypher COUNT query
            if cypher_result.count is not None:
                actual_count = cypher_result.count
                context.query_result = {"count": actual_count}
        elif intent.entities.exists_check:
            context.query_type = "exists"
            exists = cypher_result.row_count > 0
            context.query_result = {
                "exists": exists,
                "count": cypher_result.row_count,
            }
        elif intent.type == IntentType.STRUCTURAL_LOCATION:
            context.query_type = "location"
        else:
            context.query_type = "list"

        # Extract document info
        # For count queries, use actual_count; for list queries, use row_count
        context.document_count = actual_count
        context.document_ids = [
            row.get("document_id", "") for row in cypher_result.rows
            if row.get("document_id")
        ]
        context.document_titles = [
            row.get("title", "Untitled") for row in cypher_result.rows
            if row.get("title")
        ]
        context.document_types = [
            row.get("semantic_type", "") for row in cypher_result.rows
            if row.get("semantic_type")
        ]

        # Extract folder paths
        folder_paths = set()
        for row in cypher_result.rows:
            if row.get("folder_path"):
                folder_paths.add(row["folder_path"])

        if folder_paths:
            context.folder_path = list(folder_paths)[0] if len(folder_paths) == 1 else None
            context.folder_hierarchy = list(folder_paths)

        # Extract domains
        domains = set()
        for row in cypher_result.rows:
            if row.get("domain"):
                domains.add(row["domain"])
        context.semantic_domain = list(domains)[0] if len(domains) == 1 else None
        context.semantic_types = list(set(context.document_types))

        # Full query result in details
        context.query_result = {
            "type": context.query_type,
            "count": context.document_count,
            "items": cypher_result.rows[:20],  # Limit for context size
        }

        return context

    def _build_temporal_context(
        self,
        intent: Intent,
        cypher_result: CypherQueryResult,
    ) -> StructuralContext:
        """Build context for temporal queries."""
        context = self._build_structural_context(intent, cypher_result)

        # Add temporal-specific information
        if intent.temporal_markers:
            intent_type_str = _get_enum_value(intent.type)
            context.query_type = f"temporal_{intent_type_str.replace('temporal_', '')}"

            if intent.temporal_markers.start_date:
                context.details["start_date"] = intent.temporal_markers.start_date.isoformat()
            if intent.temporal_markers.end_date:
                context.details["end_date"] = intent.temporal_markers.end_date.isoformat()
            if intent.temporal_markers.point_in_time:
                context.details["point_in_time"] = intent.temporal_markers.point_in_time.isoformat()

        return context

    def _build_multihop_context(
        self,
        intent: Intent,
        cypher_result: CypherQueryResult,
    ) -> StructuralContext:
        """Build context for multi-hop queries."""
        context = self._build_structural_context(intent, cypher_result)

        # Add multi-hop specific info
        if intent.multihop_query:
            context.query_type = f"multihop_{intent.multihop_query.estimated_hops}hop"
            context.details["hops"] = intent.multihop_query.estimated_hops
            context.details["start_entity"] = intent.multihop_query.start_entity_value

        return context

    def _entities_to_dict(self, entities: StructuralEntities) -> Dict[str, Any]:
        """Convert entities to dictionary for context."""
        return {
            "clients": entities.client_names,
            "document_types": [_get_enum_value(t) for t in entities.document_types],
            "domains": [_get_enum_value(d) for d in entities.domains],
            "years": entities.years,
            "folders": entities.folder_names,
        }


# Global singleton instance
pre_llm_engine = PreLLMReasoningEngine()
