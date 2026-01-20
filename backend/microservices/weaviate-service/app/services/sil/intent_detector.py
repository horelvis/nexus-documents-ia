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
"""

import logging
import re
from typing import List, Optional, Tuple
from datetime import datetime, timedelta

from .schemas import (
    Intent,
    IntentType,
    StructuralEntities,
    TemporalMarkers,
    MultiHopQuery,
    SemanticType,
    DomainType,
)

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
    "expediente": SemanticType.EMPLOYEE_FILE,
    "employee file": SemanticType.EMPLOYEE_FILE,
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
    """

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the detector."""
        if self._initialized:
            return
        self._initialized = True
        logger.info("✅ IntentDetector initialized")

    async def detect_intent(self, query: str) -> Intent:
        """
        Detect the intent of a query.

        Args:
            query: The user's query

        Returns:
            Intent object with type, entities, and confidence
        """
        query_lower = query.lower()

        # Extract structural entities first
        entities = self._extract_structural_entities(query, query_lower)

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
    ) -> StructuralEntities:
        """Extract structural entities from the query."""
        entities = StructuralEntities()

        # Extract client names
        for pattern in CLIENT_PATTERNS:
            matches = re.findall(pattern, query, re.IGNORECASE)
            entities.client_names.extend(matches)
        entities.client_names = list(set(entities.client_names))

        # Extract document types
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

        # Detect quantifiers
        entities.count_requested = any(
            re.search(p, query_lower) for p in STRUCTURAL_COUNT_PATTERNS
        )
        entities.list_requested = any(
            re.search(p, query_lower) for p in STRUCTURAL_LIST_PATTERNS
        )
        entities.exists_check = any(
            re.search(p, query_lower) for p in STRUCTURAL_EXISTS_PATTERNS
        )

        # Extract folder names from path-like references
        folder_matches = re.findall(r"/([A-Za-z0-9_-]+)", query)
        entities.folder_names = folder_matches

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

        # Check for content-required patterns first (highest priority)
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

        # Check for structural count patterns
        if entities.count_requested:
            return (
                IntentType.STRUCTURAL_COUNT,
                0.9,
                "Count query detected (structural)",
            )

        # Check for structural list patterns
        if entities.list_requested:
            return (
                IntentType.STRUCTURAL_LIST,
                0.85,
                "List query detected (structural)",
            )

        # Check for exists patterns
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
