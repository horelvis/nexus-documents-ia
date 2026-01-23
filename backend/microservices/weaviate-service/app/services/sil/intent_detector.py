"""
Intent Detector for SIL

Analyzes queries to determine:
1. Intent type (structural, temporal, multi-hop, content-required)
2. Extracted entities (clients, folders, document types, dates)
3. Whether the query can be answered without reading document content

Key Insight:
Many business questions are about STRUCTURE, not content:
- "How many contracts do we have?" → STRUCTURAL (count)
- "Where is the ACME contract?" → STRUCTURAL (location)
- "What changed this week?" → TEMPORAL (range)
- "What are the penalty clauses?" → CONTENT_REQUIRED

The detector routes queries to the most efficient answering strategy.

IMPORTANT: This detector supports DYNAMIC TERMINOLOGY learned from each tenant's data.
Instead of hardcoding terms like "expediente" or "contrato", it can query the
TenantKnowledgeService to learn what terminology each tenant uses.
"""

import logging
import re
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING
from datetime import datetime, timedelta

from .schemas import (
    Intent,
    IntentType,
    StructuralEntities,
    TemporalMarkers,
    MultiHopQuery,
    SemanticType,
    FolderType,
    DomainType,
    TargetEntity,
)

if TYPE_CHECKING:
    from app.services.tenant_knowledge_service import TenantKnowledgeService

logger = logging.getLogger(__name__)


# =============================================================================
# INTENT DETECTION PATTERNS
# =============================================================================

# Patterns that indicate STRUCTURAL queries (can be answered from graph)
STRUCTURAL_COUNT_PATTERNS = [
    r"cuántos?",
    r"how many",
    r"número de",
    r"count",
    r"total de",
    r"cantidad de",
]

STRUCTURAL_LIST_PATTERNS = [
    r"listar?",
    r"list",
    r"muéstrame",
    r"show me",
    r"qué (documentos|contratos|archivos)",
    r"cuáles",
    r"which",
]

STRUCTURAL_EXISTS_PATTERNS = [
    r"existe",
    r"hay",
    r"tenemos",
    r"is there",
    r"do we have",
    r"existe algún",
]

STRUCTURAL_LOCATION_PATTERNS = [
    r"dónde está",
    r"where is",
    r"ubicación de",
    r"en qué carpeta",
    r"in which folder",
]

# Patterns that indicate FOLDER/EXPEDIENTE queries (about folders, not documents)
FOLDER_KEYWORDS = [
    r"expediente",
    r"carpeta",
    r"folder",
    r"caso",
    r"case",
    r"proyecto",
    r"project",
    r"asunto",
    r"matter",
]

FOLDER_COUNT_PATTERNS = [
    r"cuántos?\s+(expedientes?|carpetas?|casos?|proyectos?|asuntos?)",
    r"how many\s+(folders?|cases?|projects?|matters?)",
    r"número de\s+(expedientes?|carpetas?|casos?|proyectos?)",
    r"total de\s+(expedientes?|carpetas?|casos?)",
]

FOLDER_LIST_PATTERNS = [
    r"listar?\s+(expedientes?|carpetas?|casos?|proyectos?)",
    r"list\s+(folders?|cases?|projects?|matters?)",
    r"muéstrame\s+los?\s+(expedientes?|carpetas?|casos?)",
    r"show me\s+(the\s+)?(folders?|cases?|projects?)",
    r"qué\s+(expedientes?|carpetas?|casos?)",
    r"cuáles\s+(expedientes?|carpetas?|casos?)",
    r"mis\s+(expedientes?|carpetas?|casos?)",
    r"my\s+(folders?|cases?|projects?)",
]

FOLDER_EXISTS_PATTERNS = [
    r"existe\s+(el\s+|un\s+)?(expediente|carpeta|caso|proyecto)",
    r"hay\s+(algún\s+)?(expediente|carpeta|caso|proyecto)",
    r"tenemos\s+(el\s+|un\s+)?(expediente|carpeta|caso|proyecto)",
    r"is there\s+(a\s+)?(folder|case|project|matter)",
]

FOLDER_CONTENTS_PATTERNS = [
    r"qué\s+(hay|contiene|tiene)\s+(en\s+)?(el\s+)?(expediente|carpeta|caso)",
    r"contenido\s+del?\s+(expediente|carpeta|caso)",
    r"documentos?\s+(del?|en\s+el?)\s+(expediente|carpeta|caso)",
    r"what's\s+in\s+(the\s+)?(folder|case|project)",
    r"contents?\s+of\s+(the\s+)?(folder|case|project)",
    r"documents?\s+in\s+(the\s+)?(folder|case|project)",
    r"archivos?\s+(del?|en\s+el?)\s+(expediente|carpeta|caso)",
]

FOLDER_BROWSE_PATTERNS = [
    r"estructura\s+(de\s+)?(carpetas?|expedientes?)",
    r"folder\s+structure",
    r"árbol\s+de\s+(carpetas?|directorios?)",
    r"directory\s+tree",
    r"navegar\s+(por\s+)?(carpetas?|estructura)",
    r"browse\s+(folders?|structure)",
]

# Patterns that indicate TEMPORAL queries
TEMPORAL_POINT_PATTERNS = [
    r"el día",
    r"on (january|february|march|april|may|june|july|august|september|october|november|december)",
    r"el \d{1,2} de",
    r"on \d{1,2}(st|nd|rd|th)?",
    r"hace \d+ (días|semanas|meses)",
    r"\d+ (days|weeks|months) ago",
]

TEMPORAL_RANGE_PATTERNS = [
    r"esta semana",
    r"this week",
    r"este mes",
    r"this month",
    r"última(s)? semana(s)?",
    r"last week",
    r"últimos? \d+ días",
    r"last \d+ days",
    r"desde (el|la)",
    r"since",
    r"entre .* y",
    r"between .* and",
]

TEMPORAL_EVOLUTION_PATTERNS = [
    r"cómo (ha|han) evolucionado",
    r"how has .* evolved",
    r"evolución de",
    r"evolution of",
    r"historial de",
    r"history of",
    r"cambios en",
    r"changes in",
]

TEMPORAL_CHANGE_PATTERNS = [
    r"qué (ha |)cambiad[oa]",
    r"what (has |)changed",
    r"qué se (ha |)añadid[oa]",
    r"what was added",
    r"qué se (ha |)eliminad[oa]",
    r"what was deleted",
    r"modificaciones",
    r"modifications",
]

# Patterns that indicate MULTI-HOP queries
MULTIHOP_PATTERNS = [
    r"que también",
    r"that also",
    r"que además",
    r"which also",
    r"relacionados? con .* que",
    r"related to .* who",
    r"de (clientes|personas|empleados) que",
    r"of (clients|people|employees) who",
    r"documentos? de .* de .* de",  # multiple "de" = multiple hops
    r"documentos? creados? por .* del departamento",
]

# Patterns that REQUIRE document content (cannot be structural)
CONTENT_REQUIRED_PATTERNS = [
    r"qué dice",
    r"what does .* say",
    r"contenido de",
    r"content of",
    r"cláusula(s)?",
    r"clause(s)?",
    r"resumen",
    r"summary",
    r"analiza",
    r"analyze",
    r"extrae",
    r"extract",
    r"menciona",
    r"mentions",
    r"términos?",
    r"terms?",
    r"condiciones?",
    r"conditions?",
]

# Patterns that indicate LEGAL queries (leverage Legal Knowledge Graph)
LEGAL_APPLICABILITY_PATTERNS = [
    r"qué leyes? (aplica|rigen|regulan)",
    r"what laws? (apply|govern|regulate)",
    r"legislación aplicable",
    r"applicable legislation",
    r"normativa (aplicable|que rige)",
    r"qué normativa",
    r"bajo qué ley",
    r"under which law",
    r"marco legal",
    r"legal framework",
]

LEGAL_COMPLIANCE_PATTERNS = [
    r"cumple (con )?.*?(rgpd|gdpr|lopd|et|lgt|lau)",
    r"complies? with",
    r"cumplimiento (de|con)",
    r"compliance with",
    r"es legal",
    r"is (it )?legal",
    r"conforme a (la )?ley",
    r"according to law",
    r"incumple",
    r"violates?",
    r"infracción",
    r"breach",
]

LEGAL_REFERENCE_PATTERNS = [
    r"(qué dice|qué establece) (el )?art[íi]culo",
    r"what does article .* (say|state)",
    r"según (el )?art[íi]culo",
    r"according to article",
    r"art\.?\s*\d+",
    r"estatuto de los trabajadores",
    r"código civil",
    r"ley de",
    r"real decreto",
    r"boe-[a-z]-\d{4}",
]

LEGAL_DOCUMENT_LAWS_PATTERNS = [
    r"qué leyes? (rigen|aplican a) (este|el|la|los|las)",
    r"what laws? (govern|apply to) (this|the)",
    r"legislación de (este|el|la)",
    r"legislation (for|of) (this|the)",
    r"regulación (del|de la|de este)",
]

# Entity extraction patterns
CLIENT_PATTERNS = [
    r"cliente\s+([A-Z][A-Za-z0-9]+)",
    r"client\s+([A-Z][A-Za-z0-9]+)",
    r"de\s+([A-Z][A-Z0-9]{2,})",  # Acronyms like ACME
    r"for\s+([A-Z][A-Za-z0-9]+)",
]

DOCUMENT_TYPE_KEYWORDS = {
    "contrato": SemanticType.CONTRACT,
    "contract": SemanticType.CONTRACT,
    "factura": SemanticType.INVOICE,
    "invoice": SemanticType.INVOICE,
    "informe": SemanticType.REPORT,
    "report": SemanticType.REPORT,
    "política": SemanticType.POLICY,
    "policy": SemanticType.POLICY,
    "ficha de empleado": SemanticType.EMPLOYEE_FILE,
    "employee file": SemanticType.EMPLOYEE_FILE,
    "nómina": SemanticType.EMPLOYEE_FILE,
    "payroll": SemanticType.EMPLOYEE_FILE,
}

# Keywords that indicate FOLDER types (expediente = case/folder, not document)
FOLDER_TYPE_KEYWORDS = {
    "expediente": FolderType.CASE,
    "case": FolderType.CASE,
    "caso": FolderType.CASE,
    "carpeta": FolderType.GENERAL,
    "folder": FolderType.GENERAL,
    "proyecto": FolderType.PROJECT,
    "project": FolderType.PROJECT,
    "asunto": FolderType.MATTER,
    "matter": FolderType.MATTER,
    "cliente": FolderType.CLIENT_FOLDER,
    "client folder": FolderType.CLIENT_FOLDER,
}

DOMAIN_KEYWORDS = {
    "legal": DomainType.LEGAL,
    "jurídico": DomainType.LEGAL,
    "rrhh": DomainType.HR,
    "recursos humanos": DomainType.HR,
    "hr": DomainType.HR,
    "human resources": DomainType.HR,
    "finanzas": DomainType.FINANCE,
    "finance": DomainType.FINANCE,
    "fiscal": DomainType.FISCAL,
    "ventas": DomainType.SALES,
    "sales": DomainType.SALES,
    "marketing": DomainType.MARKETING,
    "it": DomainType.IT,
    "tecnología": DomainType.IT,
}


class IntentDetector:
    """
    Detects the intent of a query for optimal routing.

    The detector determines:
    1. Whether a query is structural, temporal, multi-hop, or content-required
    2. What entities are mentioned (clients, folders, document types)
    3. What temporal markers are present
    4. The confidence level of the detection

    IMPORTANT: This detector supports DYNAMIC TERMINOLOGY from tenant data.
    Call with tenant_knowledge parameter to use learned terminology instead of defaults.
    """

    def __init__(self):
        self._initialized = False
        # Cache of tenant-specific folder/document terms
        self._tenant_folder_terms: Dict[str, Set[str]] = {}
        self._tenant_document_terms: Dict[str, Set[str]] = {}

    async def initialize(self) -> None:
        """Initialize the detector."""
        if self._initialized:
            return
        self._initialized = True
        logger.info("✅ IntentDetector initialized")

    def set_tenant_terminology(
        self,
        tenant_id: str,
        folder_terms: Set[str],
        document_terms: Set[str],
    ) -> None:
        """
        Set learned terminology for a tenant.

        This allows the detector to use tenant-specific terminology
        instead of hardcoded patterns.

        Args:
            tenant_id: The tenant's ID
            folder_terms: Terms that refer to folders/containers (e.g., "expediente", "caso")
            document_terms: Terms that refer to documents (e.g., "contrato", "factura")
        """
        self._tenant_folder_terms[tenant_id] = {t.lower() for t in folder_terms}
        self._tenant_document_terms[tenant_id] = {t.lower() for t in document_terms}
        logger.debug(
            f"Set terminology for tenant {tenant_id}: "
            f"{len(folder_terms)} folder terms, {len(document_terms)} document terms"
        )

    def _get_folder_terms(self, tenant_id: Optional[str] = None) -> Set[str]:
        """Get folder terms for a tenant, or default set."""
        if tenant_id and tenant_id in self._tenant_folder_terms:
            # Combine learned terms with base patterns
            return self._tenant_folder_terms[tenant_id] | set(FOLDER_TYPE_KEYWORDS.keys())
        return set(FOLDER_TYPE_KEYWORDS.keys())

    def _get_document_terms(self, tenant_id: Optional[str] = None) -> Set[str]:
        """Get document terms for a tenant, or default set."""
        if tenant_id and tenant_id in self._tenant_document_terms:
            # Combine learned terms with base patterns
            return self._tenant_document_terms[tenant_id] | set(DOCUMENT_TYPE_KEYWORDS.keys())
        return set(DOCUMENT_TYPE_KEYWORDS.keys())

    async def detect_intent(
        self,
        query: str,
        tenant_id: Optional[str] = None,
        knowledge_service: Optional["TenantKnowledgeService"] = None,
    ) -> Intent:
        """
        Detect the intent of a query.

        Args:
            query: The user's query
            tenant_id: Optional tenant ID for tenant-specific terminology
            knowledge_service: Optional service to query SIL for terminology

        Returns:
            Intent object with type, entities, and confidence
        """
        query_lower = query.lower()

        # If knowledge service provided, query SIL for tenant terminology
        if knowledge_service and tenant_id:
            try:
                container_types = await knowledge_service.get_container_types(tenant_id, limit=10)
                document_types = await knowledge_service.get_document_types(tenant_id, limit=10)
                self.set_tenant_terminology(
                    tenant_id=tenant_id,
                    folder_terms=set(t.lower() for t in container_types),
                    document_terms=set(t.lower() for t in document_types),
                )
            except Exception as e:
                logger.debug(f"Could not load tenant terminology: {e}")

        # Extract structural entities first (now with tenant context)
        entities = self._extract_structural_entities(query, query_lower, tenant_id)

        # Check for temporal markers
        temporal_markers = self._detect_temporal_markers(query, query_lower)

        # Detect intent type
        intent_type, confidence, reasoning = self._detect_intent_type(
            query=query,
            query_lower=query_lower,
            entities=entities,
            temporal_markers=temporal_markers,
        )

        # Check if multi-hop query
        multihop_query = None
        if self._is_multihop_query(query_lower):
            intent_type = IntentType.MULTIHOP_SIMPLE
            estimated_hops = self._estimate_hops(query_lower)
            if estimated_hops > 2:
                intent_type = IntentType.MULTIHOP_COMPLEX
            multihop_query = self._parse_multihop_query(query, entities)
            confidence = min(confidence + 0.1, 0.95)

        # Determine if content is required
        requires_content = self._requires_content(intent_type, query_lower)

        # Estimate complexity
        complexity = self._estimate_complexity(
            intent_type=intent_type,
            entities=entities,
            temporal_markers=temporal_markers,
            multihop_query=multihop_query,
        )

        return Intent(
            type=intent_type,
            confidence=confidence,
            target_entity=entities.target_entity,
            entities=entities,
            temporal_markers=temporal_markers,
            multihop_query=multihop_query,
            requires_content=requires_content,
            requires_planning=complexity >= 3,
            estimated_complexity=complexity,
            reasoning=reasoning,
        )

    def _extract_structural_entities(
        self,
        query: str,
        query_lower: str,
        tenant_id: Optional[str] = None,
    ) -> StructuralEntities:
        """
        Extract structural entities from the query.

        Uses tenant-specific terminology if available, otherwise falls back to defaults.

        Args:
            query: Original query
            query_lower: Lowercased query
            tenant_id: Optional tenant ID for tenant-specific terminology
        """
        entities = StructuralEntities()

        # Extract client names
        for pattern in CLIENT_PATTERNS:
            matches = re.findall(pattern, query, re.IGNORECASE)
            entities.client_names.extend(matches)
        entities.client_names = list(set(entities.client_names))

        # Get tenant-specific terminology (or defaults)
        folder_terms = self._get_folder_terms(tenant_id)
        document_terms = self._get_document_terms(tenant_id)

        # Check if query is about folders/containers using learned terminology
        is_folder_query = any(term in query_lower for term in folder_terms)
        # Also check the base FOLDER_KEYWORDS patterns
        is_folder_query = is_folder_query or any(re.search(kw, query_lower) for kw in FOLDER_KEYWORDS)

        # Extract folder types (using both learned and default terms)
        for keyword, folder_type in FOLDER_TYPE_KEYWORDS.items():
            if keyword in query_lower:
                if folder_type not in entities.folder_types:
                    entities.folder_types.append(folder_type)

        # If tenant has learned folder terms, also check those
        if tenant_id in self._tenant_folder_terms:
            for term in self._tenant_folder_terms[tenant_id]:
                if term in query_lower and FolderType.GENERAL not in entities.folder_types:
                    # Add as general folder type (learned terms are tenant-specific)
                    entities.folder_types.append(FolderType.GENERAL)

        # Extract document types (only if not primarily a folder query)
        for keyword, doc_type in DOCUMENT_TYPE_KEYWORDS.items():
            if keyword in query_lower:
                if doc_type not in entities.document_types:
                    entities.document_types.append(doc_type)

        # Extract domains
        for keyword, domain in DOMAIN_KEYWORDS.items():
            if keyword in query_lower:
                if domain not in entities.domains:
                    entities.domains.append(domain)

        # Extract years
        year_matches = re.findall(r"\b(20\d{2}|19\d{2})\b", query)
        entities.years = [int(y) for y in year_matches]

        # Detect quantifiers for documents
        entities.count_requested = any(
            re.search(p, query_lower) for p in STRUCTURAL_COUNT_PATTERNS
        )
        entities.list_requested = any(
            re.search(p, query_lower) for p in STRUCTURAL_LIST_PATTERNS
        )
        entities.exists_check = any(
            re.search(p, query_lower) for p in STRUCTURAL_EXISTS_PATTERNS
        )

        # Detect folder-specific quantifiers
        folder_count = any(re.search(p, query_lower) for p in FOLDER_COUNT_PATTERNS)
        folder_list = any(re.search(p, query_lower) for p in FOLDER_LIST_PATTERNS)
        folder_exists = any(re.search(p, query_lower) for p in FOLDER_EXISTS_PATTERNS)
        entities.contents_requested = any(re.search(p, query_lower) for p in FOLDER_CONTENTS_PATTERNS)
        entities.browse_requested = any(re.search(p, query_lower) for p in FOLDER_BROWSE_PATTERNS)

        # Determine target entity type
        if is_folder_query or folder_count or folder_list or folder_exists or entities.contents_requested or entities.browse_requested:
            if entities.contents_requested:
                # "What's in folder X" asks about both folder and its documents
                entities.target_entity = TargetEntity.BOTH
            else:
                entities.target_entity = TargetEntity.FOLDER
            # Override count/list/exists if folder patterns matched
            if folder_count:
                entities.count_requested = True
            if folder_list:
                entities.list_requested = True
            if folder_exists:
                entities.exists_check = True
        else:
            entities.target_entity = TargetEntity.DOCUMENT

        # Extract folder names from path-like references
        folder_matches = re.findall(r"/([A-Za-z0-9_-]+)", query)
        entities.folder_names = folder_matches

        # Also extract folder names mentioned after "expediente/carpeta/caso"
        folder_name_patterns = [
            r"(?:expediente|carpeta|caso|proyecto|folder|case)\s+(?:de\s+)?([A-Z][A-Za-z0-9\s]+?)(?:\s|$|,|\.|¿|\?)",
            r"(?:expediente|carpeta|caso|proyecto|folder|case)\s+([A-Z][A-Z0-9-]+)",  # Acronyms
        ]
        for pattern in folder_name_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            for match in matches:
                clean_name = match.strip()
                if clean_name and clean_name not in entities.folder_names:
                    entities.folder_names.append(clean_name)

        return entities

    def _detect_temporal_markers(
        self,
        query: str,
        query_lower: str,
    ) -> Optional[TemporalMarkers]:
        """Detect temporal markers in the query."""
        markers = TemporalMarkers()
        has_temporal = False

        # Check for range patterns
        for pattern in TEMPORAL_RANGE_PATTERNS:
            if re.search(pattern, query_lower):
                has_temporal = True
                markers.start_date, markers.end_date = self._parse_date_range(query_lower)
                break

        # Check for point-in-time patterns
        for pattern in TEMPORAL_POINT_PATTERNS:
            if re.search(pattern, query_lower):
                has_temporal = True
                markers.point_in_time = self._parse_point_in_time(query_lower)
                break

        # Check for evolution patterns
        for pattern in TEMPORAL_EVOLUTION_PATTERNS:
            if re.search(pattern, query_lower):
                has_temporal = True
                markers.evolution_requested = True
                break

        # Check for relative references
        relative_patterns = [
            (r"esta semana|this week", "this_week"),
            (r"este mes|this month", "this_month"),
            (r"hoy|today", "today"),
            (r"ayer|yesterday", "yesterday"),
            (r"última semana|last week", "last_week"),
            (r"último mes|last month", "last_month"),
        ]
        for pattern, ref in relative_patterns:
            if re.search(pattern, query_lower):
                has_temporal = True
                markers.relative_reference = ref
                break

        return markers if has_temporal else None

    def _parse_date_range(
        self,
        query_lower: str,
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Parse a date range from the query."""
        now = datetime.now()

        # Common relative ranges
        if "esta semana" in query_lower or "this week" in query_lower:
            start = now - timedelta(days=now.weekday())
            return start.replace(hour=0, minute=0, second=0), now

        if "este mes" in query_lower or "this month" in query_lower:
            start = now.replace(day=1, hour=0, minute=0, second=0)
            return start, now

        if "última semana" in query_lower or "last week" in query_lower:
            end = now - timedelta(days=now.weekday())
            start = end - timedelta(days=7)
            return start, end

        if "último mes" in query_lower or "last month" in query_lower:
            if now.month == 1:
                start = now.replace(year=now.year - 1, month=12, day=1)
            else:
                start = now.replace(month=now.month - 1, day=1)
            end = now.replace(day=1) - timedelta(days=1)
            return start, end

        # Try to parse "últimos X días"
        match = re.search(r"últimos? (\d+) días|last (\d+) days", query_lower)
        if match:
            days = int(match.group(1) or match.group(2))
            return now - timedelta(days=days), now

        return None, None

    def _parse_point_in_time(self, query_lower: str) -> Optional[datetime]:
        """Parse a point in time from the query."""
        now = datetime.now()

        # Handle "yesterday"
        if "ayer" in query_lower or "yesterday" in query_lower:
            return (now - timedelta(days=1)).replace(hour=12, minute=0, second=0)

        # Handle "X days ago"
        match = re.search(r"hace (\d+) días|(\d+) days ago", query_lower)
        if match:
            days = int(match.group(1) or match.group(2))
            return (now - timedelta(days=days)).replace(hour=12, minute=0, second=0)

        # More sophisticated date parsing would go here
        return None

    def _detect_intent_type(
        self,
        query: str,
        query_lower: str,
        entities: StructuralEntities,
        temporal_markers: Optional[TemporalMarkers],
    ) -> Tuple[IntentType, float, str]:
        """Detect the primary intent type."""

        # Check for LEGAL patterns first (high priority)
        for pattern in LEGAL_COMPLIANCE_PATTERNS:
            if re.search(pattern, query_lower):
                return (
                    IntentType.LEGAL_COMPLIANCE,
                    0.9,
                    f"Legal compliance query detected: matched pattern '{pattern}'",
                )

        for pattern in LEGAL_REFERENCE_PATTERNS:
            if re.search(pattern, query_lower):
                return (
                    IntentType.LEGAL_REFERENCE,
                    0.9,
                    f"Legal reference query detected: matched pattern '{pattern}'",
                )

        for pattern in LEGAL_APPLICABILITY_PATTERNS:
            if re.search(pattern, query_lower):
                return (
                    IntentType.LEGAL_APPLICABILITY,
                    0.85,
                    f"Legal applicability query detected: matched pattern '{pattern}'",
                )

        for pattern in LEGAL_DOCUMENT_LAWS_PATTERNS:
            if re.search(pattern, query_lower):
                return (
                    IntentType.LEGAL_DOCUMENT_LAWS,
                    0.85,
                    f"Document laws query detected: matched pattern '{pattern}'",
                )

        # Check for content-required patterns (high priority)
        for pattern in CONTENT_REQUIRED_PATTERNS:
            if re.search(pattern, query_lower):
                return (
                    IntentType.CONTENT_SPECIFIC
                    if entities.client_names or entities.document_types
                    else IntentType.CONTENT_GENERAL,
                    0.85,
                    f"Content required: matched pattern '{pattern}'",
                )

        # Check for temporal patterns
        if temporal_markers:
            if temporal_markers.evolution_requested:
                return (
                    IntentType.TEMPORAL_EVOLUTION,
                    0.9,
                    "Temporal evolution query detected",
                )
            if any(re.search(p, query_lower) for p in TEMPORAL_CHANGE_PATTERNS):
                return (
                    IntentType.TEMPORAL_RANGE,
                    0.9,
                    "Temporal change/range query detected",
                )
            if temporal_markers.point_in_time:
                return (
                    IntentType.TEMPORAL_POINT,
                    0.85,
                    "Point-in-time query detected",
                )
            if temporal_markers.start_date or temporal_markers.end_date:
                return (
                    IntentType.TEMPORAL_RANGE,
                    0.85,
                    "Temporal range query detected",
                )

        # Check for FOLDER-specific patterns FIRST (before document patterns)
        if entities.target_entity in (TargetEntity.FOLDER, TargetEntity.BOTH):
            if entities.browse_requested:
                return (
                    IntentType.FOLDER_BROWSE,
                    0.9,
                    "Folder structure browse requested",
                )
            if entities.contents_requested:
                return (
                    IntentType.FOLDER_CONTENTS,
                    0.9,
                    "Folder contents query detected",
                )
            if entities.count_requested:
                return (
                    IntentType.FOLDER_COUNT,
                    0.9,
                    "Folder count query detected",
                )
            if entities.list_requested:
                return (
                    IntentType.FOLDER_LIST,
                    0.9,
                    "Folder list query detected",
                )
            if entities.exists_check:
                return (
                    IntentType.FOLDER_EXISTS,
                    0.85,
                    "Folder existence check detected",
                )

        # Check for structural count patterns (documents)
        if entities.count_requested:
            return (
                IntentType.STRUCTURAL_COUNT,
                0.9,
                "Count query detected (structural)",
            )

        # Check for structural list patterns (documents)
        if entities.list_requested:
            return (
                IntentType.STRUCTURAL_LIST,
                0.85,
                "List query detected (structural)",
            )

        # Check for exists patterns (documents)
        if entities.exists_check:
            return (
                IntentType.STRUCTURAL_EXISTS,
                0.85,
                "Existence check detected (structural)",
            )

        # Check for location patterns
        for pattern in STRUCTURAL_LOCATION_PATTERNS:
            if re.search(pattern, query_lower):
                return (
                    IntentType.STRUCTURAL_LOCATION,
                    0.9,
                    "Location query detected (structural)",
                )

        # Default: If we have specific entities, try focused content
        if entities.client_names or entities.document_types:
            return (
                IntentType.CONTENT_SPECIFIC,
                0.7,
                "Specific entities detected, may need focused content retrieval",
            )

        # Fallback to general content
        return (
            IntentType.CONTENT_GENERAL,
            0.5,
            "No structural pattern detected, defaulting to content search",
        )

    def _is_multihop_query(self, query_lower: str) -> bool:
        """Check if the query requires multi-hop traversal."""
        return any(re.search(p, query_lower) for p in MULTIHOP_PATTERNS)

    def _estimate_hops(self, query_lower: str) -> int:
        """Estimate the number of hops required."""
        # Count relationship indicators
        hop_indicators = [
            r"de .* de",
            r"que tiene",
            r"relacionado con",
            r"del departamento de",
            r"creado por .* que",
        ]

        count = 1
        for pattern in hop_indicators:
            if re.search(pattern, query_lower):
                count += 1

        return min(count, 5)  # Cap at 5 hops

    def _parse_multihop_query(
        self,
        query: str,
        entities: StructuralEntities,
    ) -> MultiHopQuery:
        """Parse a multi-hop query into a traversal plan."""
        # This is a simplified implementation
        # A full implementation would use NLP to decompose the query

        multihop = MultiHopQuery()

        # If we have client names, start from client
        if entities.client_names:
            multihop.start_entity_type = "Client"
            multihop.start_entity_value = entities.client_names[0]

        # If we have document types, that's what we're looking for
        if entities.document_types:
            multihop.return_type = "Document"
            multihop.return_fields = ["title", "folder_path", "semantic_type"]

        multihop.estimated_hops = self._estimate_hops(query.lower())

        return multihop

    def _requires_content(
        self,
        intent_type: IntentType,
        query_lower: str,
    ) -> bool:
        """Determine if the query requires reading document content."""
        content_intents = {
            IntentType.CONTENT_SPECIFIC,
            IntentType.CONTENT_SUMMARY,
            IntentType.CONTENT_EXTRACTION,
            IntentType.CONTENT_GENERAL,
            IntentType.CONTENT_COMPLEX,
        }
        return intent_type in content_intents

    def _estimate_complexity(
        self,
        intent_type: IntentType,
        entities: StructuralEntities,
        temporal_markers: Optional[TemporalMarkers],
        multihop_query: Optional[MultiHopQuery],
    ) -> int:
        """
        Estimate query complexity on a 1-5 scale.

        1 = Simple structural query
        2 = Structural with filters
        3 = Temporal or multi-hop
        4 = Complex multi-hop
        5 = Complex content analysis
        """
        base_complexity = {
            IntentType.STRUCTURAL: 1,
            IntentType.STRUCTURAL_COUNT: 1,
            IntentType.STRUCTURAL_LIST: 1,
            IntentType.STRUCTURAL_EXISTS: 1,
            IntentType.STRUCTURAL_LOCATION: 1,
            # Folder intents - also low complexity (graph queries)
            IntentType.FOLDER_COUNT: 1,
            IntentType.FOLDER_LIST: 1,
            IntentType.FOLDER_EXISTS: 1,
            IntentType.FOLDER_CONTENTS: 2,  # Slightly higher - needs join
            IntentType.FOLDER_BROWSE: 2,
            IntentType.TEMPORAL_POINT: 2,
            IntentType.TEMPORAL_RANGE: 2,
            IntentType.TEMPORAL_EVOLUTION: 3,
            IntentType.TEMPORAL_COMPARISON: 3,
            IntentType.MULTIHOP_SIMPLE: 3,
            IntentType.MULTIHOP_COMPLEX: 4,
            IntentType.CONTENT_SPECIFIC: 3,
            IntentType.CONTENT_SUMMARY: 3,
            IntentType.CONTENT_EXTRACTION: 3,
            IntentType.CONTENT_GENERAL: 4,
            IntentType.CONTENT_COMPLEX: 5,
            # Legal intents - relatively low complexity since answered from graph
            IntentType.LEGAL_APPLICABILITY: 2,
            IntentType.LEGAL_COMPLIANCE: 2,
            IntentType.LEGAL_REFERENCE: 2,
            IntentType.LEGAL_DOCUMENT_LAWS: 2,
            IntentType.UNKNOWN: 3,
        }.get(intent_type, 3)

        # Add complexity for multiple filters
        filter_count = (
            len(entities.client_names)
            + len(entities.document_types)
            + len(entities.domains)
            + len(entities.years)
        )
        if filter_count > 2:
            base_complexity += 1

        # Add complexity for temporal
        if temporal_markers and temporal_markers.evolution_requested:
            base_complexity += 1

        # Add complexity for multi-hop
        if multihop_query and multihop_query.estimated_hops > 3:
            base_complexity += 1

        return min(base_complexity, 5)


# Global singleton instance
intent_detector = IntentDetector()
