"""
Structural Metadata Extractor

Extracts STRUCTURAL metadata from documents - NOT content.
Focus on: WHERE (location), WHAT TYPE (semantic classification),
HOW RELATED (relationships with other documents).

Key Principle:
- Extract location in folder hierarchy
- Infer semantic type from metadata and path
- Detect relationships based on naming patterns and metadata
- Generate structural description for embedding
- NEVER extract or embed actual document content

Enhanced with NLP (v2.0):
- Lemmatization for morphological flexibility
- Semantic similarity for synonym matching
- Fuzzy matching for typo tolerance
- Zero-shot classification for unknown types

Connector-Agnostic (v3.0):
- Uses MetadataAdapter pattern for different connectors
- PathIntelligence for metadata-poor sources
- Automatic inference based on metadata richness level
"""

import logging
import os
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

from .schemas import (
    StructuralMetadata,
    FolderSemantics,
    DocumentRelationship,
    SemanticType,
    DomainType,
    RelationshipEdgeType,
)

# Import connector-agnostic metadata adapters
try:
    from core.connectors import (
        MetadataAdapterRegistry,
        NormalizedMetadata,
        MetadataRichness,
    )
    ADAPTERS_AVAILABLE = True
except ImportError:
    ADAPTERS_AVAILABLE = False

logger = logging.getLogger(__name__)

# NLP Enhancement flag (can be disabled via environment)
USE_NLP_CLASSIFICATION = os.getenv("SIL_USE_NLP", "true").lower() == "true"


# =============================================================================
# PATTERN DEFINITIONS FOR EXTRACTION
# =============================================================================

# Patterns for inferring semantic type from filename/path
SEMANTIC_TYPE_PATTERNS = {
    SemanticType.CONTRACT: [
        r"contrat[oe]",
        r"contract",
        r"acuerdo",
        r"agreement",
        r"convenio",
    ],
    SemanticType.INVOICE: [
        r"factura",
        r"invoice",
        r"recibo",
        r"receipt",
    ],
    SemanticType.AMENDMENT: [
        r"adend[ua]",
        r"amendment",
        r"modificaci[oó]n",
        r"anexo",
    ],
    SemanticType.REPORT: [
        r"informe",
        r"report",
        r"reporte",
    ],
    SemanticType.POLICY: [
        r"pol[ií]tica",
        r"policy",
        r"normativa",
    ],
    SemanticType.PROCEDURE: [
        r"procedimiento",
        r"procedure",
        r"proceso",
    ],
    SemanticType.MEMO: [
        r"memo",
        r"memorando",
        r"comunicado",
    ],
    SemanticType.OFFER_LETTER: [
        r"oferta",
        r"offer",
        r"propuesta",
    ],
    SemanticType.EMPLOYEE_FILE: [
        r"expediente",
        r"employee.*file",
        r"legajo",
    ],
    SemanticType.FINANCIAL_STATEMENT: [
        r"estado.*financiero",
        r"financial.*statement",
        r"balance",
    ],
    SemanticType.TECHNICAL_SPEC: [
        r"especificaci[oó]n",
        r"spec",
        r"technical",
    ],
}

# Patterns for inferring domain from folder path
DOMAIN_PATTERNS = {
    DomainType.LEGAL: [
        r"legal",
        r"jur[ií]dico",
        r"contratos",
        r"contracts",
        r"abogad[oa]",
    ],
    DomainType.HR: [
        r"rrhh",
        r"recursos.*humanos",
        r"human.*resources",
        r"hr",
        r"personal",
        r"empleados",
    ],
    DomainType.FINANCE: [
        r"finanz",
        r"finance",
        r"contab",
        r"accounting",
        r"tesor",
        r"treasury",
    ],
    DomainType.FISCAL: [
        r"fiscal",
        r"tax",
        r"impuesto",
        r"tribut",
    ],
    DomainType.SALES: [
        r"ventas",
        r"sales",
        r"comercial",
        r"clientes",
        r"customers",
    ],
    DomainType.MARKETING: [
        r"marketing",
        r"mercadeo",
        r"publicidad",
    ],
    DomainType.IT: [
        r"ti",
        r"it",
        r"sistemas",
        r"tecnolog",
        r"software",
    ],
    DomainType.COMPLIANCE: [
        r"compliance",
        r"cumplimiento",
        r"audit",
        r"control.*interno",
    ],
}

# Patterns for detecting version relationships
VERSION_PATTERNS = [
    r"v(\d+)",
    r"version[_\s]?(\d+)",
    r"rev[_\s]?(\d+)",
    r"_(\d{8})$",  # Date suffix like _20240115
]

# Patterns for detecting client names in paths
CLIENT_FOLDER_PATTERNS = [
    r"/clients?/([^/]+)",
    r"/clientes?/([^/]+)",
    r"/customers?/([^/]+)",
]

# Year patterns in folder paths
YEAR_PATTERN = r"(20\d{2}|19\d{2})"


class StructuralExtractor:
    """
    Extracts structural metadata from documents.

    Focus is on STRUCTURE, not CONTENT:
    - Location in folder hierarchy
    - Semantic type (what kind of document)
    - Relationships with other documents
    - Key properties from metadata (not from text)

    Enhanced with NLP for better classification:
    - Lemmatization handles morphological variations
    - Semantic similarity handles synonyms
    - Fuzzy matching handles typos
    - Zero-shot classification for unknown types

    Connector-Agnostic (v3.0):
    - Uses MetadataAdapter pattern for different connectors
    - Selects appropriate adapter based on connector_type
    - Falls back to PathIntelligence for metadata-poor sources
    """

    def __init__(self):
        self._initialized = False
        self._nlp_available = False
        self._classifier = None
        self._adapters_available = ADAPTERS_AVAILABLE

    async def initialize(self) -> None:
        """Initialize the extractor and NLP components."""
        if self._initialized:
            return

        # Try to initialize NLP classifier
        if USE_NLP_CLASSIFICATION:
            try:
                from .semantic_classifier import semantic_classifier
                await semantic_classifier.initialize()
                self._classifier = semantic_classifier
                self._nlp_available = semantic_classifier.is_initialized
                logger.info(f"✅ NLP Classifier initialized. Capabilities: {semantic_classifier.get_capabilities()}")
            except Exception as e:
                logger.warning(f"⚠️ NLP Classifier not available, using regex fallback: {e}")
                self._nlp_available = False
        else:
            logger.info("ℹ️ NLP Classification disabled via SIL_USE_NLP=false")

        self._initialized = True
        logger.info("✅ StructuralExtractor initialized")

    async def extract_with_adapter(
        self,
        document_id: str,
        tenant_id: str,
        connector_type: str,
        raw_metadata: Dict[str, Any],
        file_path: Optional[str] = None,
    ) -> StructuralMetadata:
        """
        Extract structural metadata using the connector-agnostic adapter pattern.

        This method:
        1. Selects the appropriate MetadataAdapter based on connector_type
        2. Normalizes metadata to common NormalizedMetadata schema
        3. Converts to StructuralMetadata for SIL indexing

        Args:
            document_id: Unique document identifier
            tenant_id: Tenant identifier
            connector_type: Type of connector (alfresco, google_drive, filesystem, database)
            raw_metadata: Raw metadata from the connector
            file_path: File path in source system

        Returns:
            StructuralMetadata ready for SIL indexing
        """
        if not self._initialized:
            await self.initialize()

        if not self._adapters_available:
            # Fall back to legacy extraction
            logger.warning("MetadataAdapters not available, using legacy extraction")
            return await self.extract_structural_metadata(
                document_id=document_id,
                file_path=file_path or "",
                connector_metadata=raw_metadata,
                tenant_id=tenant_id,
            )

        # Get appropriate adapter
        adapter = MetadataAdapterRegistry.get_adapter(connector_type)
        logger.debug(f"Using {adapter.__class__.__name__} for {connector_type}")

        # Normalize metadata
        normalized = adapter.normalize(
            document_id=document_id,
            tenant_id=tenant_id,
            raw_metadata=raw_metadata,
            file_path=file_path,
        )

        # Convert NormalizedMetadata to StructuralMetadata
        return self._convert_normalized_to_structural(normalized, raw_metadata)

    def _convert_normalized_to_structural(
        self,
        normalized: "NormalizedMetadata",
        raw_metadata: Dict[str, Any],
    ) -> StructuralMetadata:
        """
        Convert NormalizedMetadata to StructuralMetadata.

        Maps the connector-agnostic normalized format to the SIL-specific format.
        """
        # Map semantic type from adapter to SIL SemanticType
        semantic_type = self._map_semantic_type(normalized.classification.semantic_type)

        # Map domain from adapter to SIL DomainType
        domain = self._map_domain(normalized.classification.domain)

        # Build folder semantics from normalized data
        folder_semantics = FolderSemantics(
            folder_name=normalized.path.parent_folder or "",
            folder_path=normalized.path.full_path.rsplit("/", 1)[0] if "/" in normalized.path.full_path else "",
            year=normalized.path.year_from_path,
            client=normalized.business.client_name or normalized.path.client_from_path,
            department=normalized.classification.domain,
            confidence=normalized.classification.semantic_type_confidence,
        )

        # Build key properties from normalized data
        key_properties = normalized.get_key_properties()

        # Add any additional properties from business section
        if normalized.business.reference_number:
            key_properties["reference_number"] = normalized.business.reference_number
        if normalized.business.project_name:
            key_properties["project"] = normalized.business.project_name
        if normalized.business.department:
            key_properties["department"] = normalized.business.department
        if normalized.business.status:
            key_properties["status"] = normalized.business.status

        # Include custom properties
        for k, v in normalized.business.custom.items():
            if v is not None and k not in key_properties:
                key_properties[k] = v

        # Generate folder hierarchy
        folder_path = normalized.path.full_path.rsplit("/", 1)[0] if "/" in normalized.path.full_path else ""
        folder_hierarchy = self._generate_folder_hierarchy(folder_path)

        # Get structural description from normalized metadata
        structural_description = normalized.get_structural_description()

        # Calculate importance based on richness level
        importance = self._calculate_importance_from_normalized(normalized)

        return StructuralMetadata(
            document_id=normalized.document_id,
            weaviate_document_id=raw_metadata.get("weaviate_id"),
            semantic_type=semantic_type,
            domain=domain,
            folder_path=folder_path,
            folder_hierarchy=folder_hierarchy,
            folder_semantics=folder_semantics,
            site_id=raw_metadata.get("site_id"),
            site_name=raw_metadata.get("site_name", ""),
            connector_id=normalized.origin.connector_id,
            key_properties=key_properties,
            relationships=[],  # Relationships detected separately
            created_at=normalized.temporal.created_at,
            modified_at=normalized.temporal.modified_at,
            valid_from=normalized.temporal.created_at,
            valid_to=None,
            structural_description=structural_description,
            importance=importance,
            tenant_id=normalized.tenant_id,
        )

    def _map_semantic_type(self, type_str: Optional[str]) -> SemanticType:
        """Map normalized semantic type string to SIL SemanticType enum."""
        if not type_str:
            return SemanticType.GENERAL

        type_mapping = {
            "contract": SemanticType.CONTRACT,
            "invoice": SemanticType.INVOICE,
            "report": SemanticType.REPORT,
            "policy": SemanticType.POLICY,
            "procedure": SemanticType.PROCEDURE,
            "memo": SemanticType.MEMO,
            "agreement": SemanticType.AGREEMENT,
            "case_file": SemanticType.EMPLOYEE_FILE,
            "case_document": SemanticType.GENERAL,
            "employee_record": SemanticType.EMPLOYEE_FILE,
            "employment_contract": SemanticType.CONTRACT,
            "document": SemanticType.GENERAL,
            "text": SemanticType.GENERAL,
            "spreadsheet": SemanticType.FINANCIAL_STATEMENT,
            "presentation": SemanticType.REPORT,
            "data": SemanticType.GENERAL,
            "email": SemanticType.MEMO,
            "proposal": SemanticType.OFFER_LETTER,
            "manual": SemanticType.TECHNICAL_SPEC,
            "legal": SemanticType.LEGAL_BRIEF,
        }

        normalized_type = type_str.lower()
        return type_mapping.get(normalized_type, SemanticType.GENERAL)

    def _map_domain(self, domain_str: Optional[str]) -> DomainType:
        """Map normalized domain string to SIL DomainType enum."""
        if not domain_str:
            return DomainType.GENERAL

        domain_mapping = {
            "legal": DomainType.LEGAL,
            "finance": DomainType.FINANCE,
            "hr": DomainType.HR,
            "sales": DomainType.SALES,
            "marketing": DomainType.MARKETING,
            "it": DomainType.IT,
            "compliance": DomainType.COMPLIANCE,
            "operations": DomainType.GENERAL,
        }

        normalized_domain = domain_str.lower()
        return domain_mapping.get(normalized_domain, DomainType.GENERAL)

    def _calculate_importance_from_normalized(
        self,
        normalized: "NormalizedMetadata",
    ) -> float:
        """Calculate importance score based on normalized metadata."""
        base_score = 0.5

        # Higher richness = more confident classification
        richness_bonus = {
            MetadataRichness.RICH: 0.2,
            MetadataRichness.BASIC: 0.1,
            MetadataRichness.MINIMAL: 0.05,
            MetadataRichness.DATABASE: 0.0,
        }
        base_score += richness_bonus.get(normalized.richness_level, 0)

        # Boost for high-confidence semantic type
        if normalized.classification.semantic_type_confidence > 0.8:
            base_score += 0.1

        # Boost for important document types
        important_types = {"contract", "agreement", "policy", "legal"}
        if normalized.classification.semantic_type and \
           normalized.classification.semantic_type.lower() in important_types:
            base_score += 0.1

        # Boost for having business properties
        if normalized.business.reference_number:
            base_score += 0.05
        if normalized.business.client_name:
            base_score += 0.05

        return min(base_score, 1.0)

    async def extract_structural_metadata(
        self,
        document_id: str,
        file_path: str,
        connector_metadata: Dict[str, Any],
        learned_context: Optional[Dict[str, Any]] = None,
        tenant_id: str = "",
    ) -> StructuralMetadata:
        """
        Extract ONLY structural information from a document.

        Args:
            document_id: Unique document identifier
            file_path: Full path to the document in the source system
            connector_metadata: Metadata from the connector (Alfresco, SharePoint, etc.)
            learned_context: Context learned about this folder/connector
            tenant_id: Tenant identifier

        Returns:
            StructuralMetadata with location, type, relationships, and description
        """
        learned_context = learned_context or {}

        # Extract folder path and semantics
        folder_path = self._extract_folder_path(file_path)
        folder_semantics = self._analyze_folder_semantics(folder_path, learned_context)

        # Infer semantic type (use async NLP-enhanced version)
        if self._nlp_available:
            semantic_type = await self._infer_semantic_type_async(
                file_path=file_path,
                metadata=connector_metadata,
                learned_context=learned_context,
            )
        else:
            semantic_type = self._infer_semantic_type(
                file_path=file_path,
                metadata=connector_metadata,
                learned_context=learned_context,
            )

        # Infer domain (use async NLP-enhanced version)
        if self._nlp_available:
            domain = await self._infer_domain_async(
                folder_path=folder_path,
                semantic_type=semantic_type,
                learned_context=learned_context,
            )
        else:
            domain = self._infer_domain(
                folder_path=folder_path,
                semantic_type=semantic_type,
                learned_context=learned_context,
            )

        # Extract key properties (from metadata, NOT content)
        key_properties = self._extract_key_properties(
            metadata=connector_metadata,
            folder_semantics=folder_semantics,
        )

        # Detect relationships
        relationships = await self._detect_relationships(
            document_id=document_id,
            file_path=file_path,
            metadata=connector_metadata,
            tenant_id=tenant_id,
        )

        # Extract temporal information
        created_at, modified_at = self._extract_temporal_info(connector_metadata)

        # Calculate importance score
        importance = self._calculate_importance(
            semantic_type=semantic_type,
            metadata=connector_metadata,
            learned_context=learned_context,
        )

        # Generate structural description for embedding
        structural_description = self._generate_structural_description(
            semantic_type=semantic_type,
            domain=domain,
            folder_path=folder_path,
            folder_semantics=folder_semantics,
            key_properties=key_properties,
            metadata=connector_metadata,
        )

        # Generate folder hierarchy from folder_path
        # e.g., "/Contratos/ACME" -> ["/", "/Contratos", "/Contratos/ACME"]
        folder_hierarchy = self._generate_folder_hierarchy(folder_path)

        return StructuralMetadata(
            document_id=document_id,
            weaviate_document_id=connector_metadata.get("weaviate_id"),
            semantic_type=semantic_type,
            domain=domain,
            folder_path=folder_path,
            folder_hierarchy=folder_hierarchy,
            folder_semantics=folder_semantics,
            site_id=connector_metadata.get("site_id"),
            site_name=connector_metadata.get("site_name", ""),
            connector_id=connector_metadata.get("connector_id"),
            key_properties=key_properties,
            relationships=relationships,
            created_at=created_at,
            modified_at=modified_at,
            valid_from=created_at,  # Initially same as created
            valid_to=None,  # Currently valid
            structural_description=structural_description,
            importance=importance,
            tenant_id=tenant_id,
        )

    def _extract_folder_path(self, file_path: str) -> str:
        """Extract the folder path from a file path."""
        if not file_path:
            return ""

        # Normalize path separators
        file_path = file_path.replace("\\", "/")

        # Remove filename to get folder path
        last_slash = file_path.rfind("/")
        if last_slash > 0:
            return file_path[:last_slash]

        return ""

    def _generate_folder_hierarchy(self, folder_path: str) -> List[str]:
        """
        Generate the folder hierarchy from a folder path.

        Args:
            folder_path: Full folder path (e.g., "/Contratos/ACME")

        Returns:
            List of paths from root to folder (e.g., ["/", "/Contratos", "/Contratos/ACME"])
        """
        if not folder_path:
            return []

        # Normalize path
        folder_path = folder_path.replace("\\", "/").strip()
        if not folder_path.startswith("/"):
            folder_path = "/" + folder_path

        hierarchy = ["/"]  # Always start with root
        parts = folder_path.split("/")

        current_path = ""
        for part in parts:
            if part:  # Skip empty parts
                current_path += "/" + part
                hierarchy.append(current_path)

        return hierarchy

    def _analyze_folder_semantics(
        self,
        folder_path: str,
        learned_context: Dict[str, Any],
    ) -> FolderSemantics:
        """
        Analyze folder path to extract semantic meaning.

        Examples:
        - "/Clients/ACME/2024/Contracts" → client=ACME, year=2024, doc_type=contracts
        - "/HR/Employees/Active" → department=HR, doc_type=employee_files
        """
        folder_name = folder_path.split("/")[-1] if folder_path else ""

        semantics = FolderSemantics(
            folder_name=folder_name,
            folder_path=folder_path,
        )

        # Extract year if present
        year_match = re.search(YEAR_PATTERN, folder_path)
        if year_match:
            semantics.year = int(year_match.group(1))

        # Extract client name if in client folder
        for pattern in CLIENT_FOLDER_PATTERNS:
            client_match = re.search(pattern, folder_path, re.IGNORECASE)
            if client_match:
                semantics.client = client_match.group(1)
                break

        # Infer department from folder path
        for domain, patterns in DOMAIN_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, folder_path, re.IGNORECASE):
                    semantics.department = domain.value
                    break

        # Check learned context for folder-specific semantics
        if "folder_semantics" in learned_context:
            fs = learned_context["folder_semantics"]
            if fs.get("department"):
                semantics.department = fs["department"]
            if fs.get("client"):
                semantics.client = fs["client"]
            if fs.get("document_type_hint"):
                semantics.document_type_hint = fs["document_type_hint"]
            semantics.confidence = fs.get("confidence", 0.7)
        else:
            # Calculate confidence based on how much we could infer
            inferred_count = sum([
                bool(semantics.year),
                bool(semantics.client),
                bool(semantics.department),
            ])
            semantics.confidence = min(0.3 + (inferred_count * 0.2), 0.9)

        return semantics

    async def _infer_semantic_type_async(
        self,
        file_path: str,
        metadata: Dict[str, Any],
        learned_context: Dict[str, Any],
    ) -> SemanticType:
        """
        Infer the semantic type of the document using NLP-enhanced classification.

        Priority:
        1. Explicit document_type in metadata
        2. Learned context from Data Learning System
        3. NLP-based classification (if available):
           a. Zero-shot classification
           b. Embedding similarity
           c. Lemma matching
           d. Fuzzy matching
        4. Regex pattern matching (fallback)
        """
        # Check explicit metadata first
        explicit_type = metadata.get("document_type", "").lower()
        for stype in SemanticType:
            if stype.value in explicit_type:
                return stype

        # Check learned context
        if learned_context.get("semantic_type"):
            try:
                return SemanticType(learned_context["semantic_type"])
            except ValueError:
                pass

        # Use NLP classifier if available
        if self._nlp_available and self._classifier:
            try:
                # Extract title or filename for classification
                title = metadata.get("title", "")
                filename = file_path.split("/")[-1] if file_path else ""

                result = await self._classifier.classify_document_type(
                    text=title or filename,
                    file_path=file_path,
                    metadata=metadata,
                )

                if result.confidence >= 0.5:
                    logger.debug(
                        f"NLP classified '{filename}' as {result.semantic_type.value} "
                        f"(confidence: {result.confidence:.2f}, method: {result.method})"
                    )
                    return result.semantic_type

            except Exception as e:
                logger.warning(f"NLP classification failed, using regex fallback: {e}")

        # Fallback: Pattern matching on path
        return self._infer_semantic_type_regex(file_path)

    def _infer_semantic_type_regex(self, file_path: str) -> SemanticType:
        """Fallback regex-based semantic type inference."""
        path_lower = file_path.lower()
        for stype, patterns in SEMANTIC_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, path_lower):
                    return stype
        return SemanticType.GENERAL

    def _infer_semantic_type(
        self,
        file_path: str,
        metadata: Dict[str, Any],
        learned_context: Dict[str, Any],
    ) -> SemanticType:
        """
        Synchronous wrapper for semantic type inference.
        Uses regex-only for sync contexts.
        """
        # Check explicit metadata first
        explicit_type = metadata.get("document_type", "").lower()
        for stype in SemanticType:
            if stype.value in explicit_type:
                return stype

        # Check learned context
        if learned_context.get("semantic_type"):
            try:
                return SemanticType(learned_context["semantic_type"])
            except ValueError:
                pass

        return self._infer_semantic_type_regex(file_path)

    async def _infer_domain_async(
        self,
        folder_path: str,
        semantic_type: SemanticType,
        learned_context: Dict[str, Any],
    ) -> DomainType:
        """Infer the domain/area using NLP-enhanced classification."""
        # Check learned context first
        if learned_context.get("domain"):
            try:
                return DomainType(learned_context["domain"])
            except ValueError:
                pass

        # Use NLP classifier if available
        if self._nlp_available and self._classifier:
            try:
                result = await self._classifier.classify_domain(
                    folder_path=folder_path,
                    semantic_type=semantic_type,
                )

                if result.confidence >= 0.5:
                    logger.debug(
                        f"NLP classified domain for '{folder_path}' as {result.domain.value} "
                        f"(confidence: {result.confidence:.2f}, method: {result.method})"
                    )
                    return result.domain

            except Exception as e:
                logger.warning(f"NLP domain classification failed, using regex fallback: {e}")

        # Fallback to regex
        return self._infer_domain_regex(folder_path, semantic_type)

    def _infer_domain_regex(
        self,
        folder_path: str,
        semantic_type: SemanticType,
    ) -> DomainType:
        """Fallback regex-based domain inference."""
        # Pattern matching on folder path
        path_lower = folder_path.lower()
        for domain, patterns in DOMAIN_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, path_lower):
                    return domain

        # Infer from semantic type
        type_to_domain = {
            SemanticType.CONTRACT: DomainType.LEGAL,
            SemanticType.AGREEMENT: DomainType.LEGAL,
            SemanticType.AMENDMENT: DomainType.LEGAL,
            SemanticType.LEGAL_BRIEF: DomainType.LEGAL,
            SemanticType.INVOICE: DomainType.FINANCE,
            SemanticType.FINANCIAL_STATEMENT: DomainType.FINANCE,
            SemanticType.TAX_RETURN: DomainType.FISCAL,
            SemanticType.EMPLOYEE_FILE: DomainType.HR,
            SemanticType.PERFORMANCE_REVIEW: DomainType.HR,
            SemanticType.OFFER_LETTER: DomainType.HR,
            SemanticType.TECHNICAL_SPEC: DomainType.IT,
        }

        return type_to_domain.get(semantic_type, DomainType.GENERAL)

    def _infer_domain(
        self,
        folder_path: str,
        semantic_type: SemanticType,
        learned_context: Dict[str, Any],
    ) -> DomainType:
        """Synchronous wrapper for domain inference."""
        # Check learned context first
        if learned_context.get("domain"):
            try:
                return DomainType(learned_context["domain"])
            except ValueError:
                pass

        return self._infer_domain_regex(folder_path, semantic_type)

    def _extract_key_properties(
        self,
        metadata: Dict[str, Any],
        folder_semantics: FolderSemantics,
    ) -> Dict[str, Any]:
        """
        Extract key properties from metadata.

        These are structural properties that can be used for filtering
        and graph traversal - NOT content extracted from the document.

        Includes:
        - Standard metadata (title, author)
        - Alfresco-specific properties (node_type, custom properties)
        - Parent folder properties (inherited from folder hierarchy)
        """
        properties = {}

        # Standard metadata fields
        if metadata.get("title"):
            properties["title"] = metadata["title"]

        # Filename and extension (for display in UI)
        if metadata.get("filename"):
            properties["filename"] = metadata["filename"]
        if metadata.get("file_extension"):
            properties["file_extension"] = metadata["file_extension"]
        if metadata.get("mime_type"):
            properties["mime_type"] = metadata["mime_type"]

        if metadata.get("author"):
            properties["author"] = metadata["author"]

        if folder_semantics.client:
            properties["client"] = folder_semantics.client

        if folder_semantics.year:
            properties["year"] = folder_semantics.year

        # Alfresco-specific base properties
        if metadata.get("alfresco_node_type"):
            properties["node_type"] = metadata["alfresco_node_type"]

        if metadata.get("alfresco_creator"):
            properties["creator"] = metadata["alfresco_creator"]

        if metadata.get("alfresco_parent_id"):
            properties["parent_id"] = metadata["alfresco_parent_id"]

        # Extract ALL Alfresco custom properties (exp:*, pmreg:*, etc.)
        # These contain the rich metadata from Alfresco content models
        alfresco_props = metadata.get("alfresco_properties", {})
        if alfresco_props:
            for prop_name, prop_value in alfresco_props.items():
                if prop_value is not None:
                    # Clean property name (remove namespace prefix for simpler access)
                    # e.g., "exp:clasificacion" -> "clasificacion"
                    clean_name = prop_name.split(":")[-1] if ":" in prop_name else prop_name
                    properties[clean_name] = prop_value

                    # Also store with original qualified name for precise lookup
                    properties[prop_name] = prop_value

        # Extract parent folder properties (inherited from containing folder)
        parent_folder_props = metadata.get("parent_folder_properties", {})
        if parent_folder_props:
            for prop_name, prop_value in parent_folder_props.items():
                if prop_value is not None:
                    clean_name = prop_name.split(":")[-1] if ":" in prop_name else prop_name
                    # Prefix with folder_ to distinguish from document properties
                    properties[f"folder_{clean_name}"] = prop_value

        # Store parent folder type if available (useful for expediente/registro detection)
        if metadata.get("parent_folder_type"):
            properties["folder_type"] = metadata["parent_folder_type"]

        # SharePoint-specific
        if metadata.get("sharepoint_site"):
            properties["site"] = metadata["sharepoint_site"]

        # Contract-specific properties (common names in both direct and alfresco_properties)
        for key in ["contract_number", "contract_date", "expiry_date", "amount", "currency"]:
            if metadata.get(key):
                properties[key] = metadata[key]

        # Document identifiers
        if metadata.get("document_number"):
            properties["document_number"] = metadata["document_number"]

        if metadata.get("version"):
            properties["version"] = metadata["version"]

        return properties

    async def _detect_relationships(
        self,
        document_id: str,
        file_path: str,
        metadata: Dict[str, Any],
        tenant_id: str,
    ) -> List[DocumentRelationship]:
        """
        Detect relationships with other documents.

        Types of relationships detected:
        - version_of: When filename contains version number
        - relates_to: Explicit relationships in metadata
        - sibling_of: Documents in same folder
        """
        relationships = []

        # Check for explicit parent/related documents in metadata
        if metadata.get("parent_document_id"):
            relationships.append(DocumentRelationship(
                target_document_id=metadata["parent_document_id"],
                relationship_type=RelationshipEdgeType.VERSION_OF,
                strength=0.9,
                inferred_from="metadata:parent_document_id",
            ))

        if metadata.get("relates_to"):
            for related_id in metadata["relates_to"]:
                relationships.append(DocumentRelationship(
                    target_document_id=related_id,
                    relationship_type=RelationshipEdgeType.RELATES_TO,
                    strength=0.8,
                    inferred_from="metadata:relates_to",
                ))

        if metadata.get("references"):
            for ref_id in metadata["references"]:
                relationships.append(DocumentRelationship(
                    target_document_id=ref_id,
                    relationship_type=RelationshipEdgeType.REFERENCES,
                    strength=0.7,
                    inferred_from="metadata:references",
                ))

        # Detect version relationship from filename
        filename = file_path.split("/")[-1] if file_path else ""
        for pattern in VERSION_PATTERNS:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                # This document is likely a version of another
                # The actual linking would be done in post-processing
                # when we can query for base document
                logger.debug(f"Document {document_id} appears to be a versioned file")
                break

        return relationships

    def _extract_temporal_info(
        self,
        metadata: Dict[str, Any],
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        """Extract creation and modification timestamps."""
        created_at = None
        modified_at = None

        # Try various metadata fields for creation date
        for field in ["created_at", "created", "creation_date", "date_created"]:
            if metadata.get(field):
                try:
                    value = metadata[field]
                    if isinstance(value, datetime):
                        created_at = value
                    elif isinstance(value, str):
                        created_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    break
                except (ValueError, TypeError):
                    continue

        # Try various metadata fields for modification date
        for field in ["modified_at", "modified", "modification_date", "date_modified", "updated_at"]:
            if metadata.get(field):
                try:
                    value = metadata[field]
                    if isinstance(value, datetime):
                        modified_at = value
                    elif isinstance(value, str):
                        modified_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    break
                except (ValueError, TypeError):
                    continue

        return created_at, modified_at

    def _calculate_importance(
        self,
        semantic_type: SemanticType,
        metadata: Dict[str, Any],
        learned_context: Dict[str, Any],
    ) -> float:
        """
        Calculate importance score for the document.

        Higher importance = more likely to be relevant in structural queries.
        """
        base_score = 0.5

        # Certain document types are typically more important
        high_importance_types = {
            SemanticType.CONTRACT: 0.2,
            SemanticType.AGREEMENT: 0.2,
            SemanticType.POLICY: 0.15,
            SemanticType.FINANCIAL_STATEMENT: 0.15,
            SemanticType.LEGAL_BRIEF: 0.15,
        }

        if semantic_type in high_importance_types:
            base_score += high_importance_types[semantic_type]

        # Check learned context for importance adjustment
        if learned_context.get("importance_boost"):
            base_score += learned_context["importance_boost"]

        # Documents with more metadata are typically more important
        metadata_completeness = min(len(metadata) / 10, 0.15)
        base_score += metadata_completeness

        return min(base_score, 1.0)

    def _generate_structural_description(
        self,
        semantic_type: SemanticType,
        domain: DomainType,
        folder_path: str,
        folder_semantics: FolderSemantics,
        key_properties: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> str:
        """
        Generate a textual description of the document's STRUCTURE.

        This description will be embedded for semantic search over structure.
        It describes WHERE the document is and WHAT TYPE it is,
        NOT what the document contains.

        Example:
        "Contrato de servicios profesionales con cliente ACME ubicado en
         /Clientes/ACME/2024/Contratos. Dominio: legal. Departamento: Ventas.
         Año: 2024. Autor: Juan García. Clasificación: K-2025-00001."
        """
        parts = []

        # Document type
        type_desc = self._get_type_description(semantic_type)
        if type_desc:
            parts.append(type_desc)

        # Client if known
        if folder_semantics.client:
            parts.append(f"del cliente {folder_semantics.client}")
        elif key_properties.get("client"):
            parts.append(f"del cliente {key_properties['client']}")

        # Title if available
        if key_properties.get("title"):
            parts.append(f"titulado '{key_properties['title']}'")

        # Location
        if folder_path:
            parts.append(f"ubicado en {folder_path}")

        # Domain
        if domain != DomainType.GENERAL:
            parts.append(f"Dominio: {domain.value}")

        # Department
        if folder_semantics.department:
            parts.append(f"Departamento: {folder_semantics.department}")

        # Year
        if folder_semantics.year:
            parts.append(f"Año: {folder_semantics.year}")
        elif key_properties.get("year"):
            parts.append(f"Año: {key_properties['year']}")

        # Author/Creator
        if key_properties.get("author"):
            parts.append(f"Autor: {key_properties['author']}")
        elif key_properties.get("creator"):
            parts.append(f"Creador: {key_properties['creator']}")

        # Dynamic content model properties
        # Include ALL custom properties from alfresco_properties (learned model)
        # Skip common/less useful properties
        skip_properties = {
            "title", "author", "creator", "client", "year",  # Already handled above
            "node_type", "parent_id",  # System properties
        }

        # Include all custom properties in the description
        # These come from the learned content model (exp:*, pmreg:*, etc.)
        for prop_key, prop_value in key_properties.items():
            # Skip already handled or system properties
            if prop_key in skip_properties:
                continue
            # Skip empty values
            if prop_value is None or prop_value == "":
                continue
            # Skip properties that start with folder_ (handled separately)
            if prop_key.startswith("folder_"):
                continue
            # Skip if already a qualified name we've seen (avoid duplicates)
            if ":" in prop_key and prop_key.split(":")[-1] in key_properties:
                continue

            # Format the property name for display
            # e.g., "exp:clasificacion" -> "Clasificación" or just use the clean name
            display_name = self._format_property_name(prop_key)
            parts.append(f"{display_name}: {prop_value}")

        # Include important folder properties
        for prop_key, prop_value in key_properties.items():
            if not prop_key.startswith("folder_"):
                continue
            if prop_value is None or prop_value == "":
                continue

            # Remove folder_ prefix and format
            clean_key = prop_key[7:]  # Remove "folder_"
            display_name = f"Carpeta {self._format_property_name(clean_key)}"
            parts.append(f"{display_name}: {prop_value}")

        # Node type if relevant (not standard cm:content/cm:folder)
        if key_properties.get("node_type") and key_properties["node_type"] not in {"cm:content", "cm:folder"}:
            parts.append(f"Tipo: {key_properties['node_type']}")

        # Join with appropriate separators
        description = " ".join(parts[:3]) + "."
        if len(parts) > 3:
            description += " " + " ".join(parts[3:])

        return description

    def _format_property_name(self, prop_name: str) -> str:
        """
        Format a property name for human-readable display.

        Converts technical property names to readable labels:
        - "exp:clasificacion" -> "Clasificación"
        - "numeroExpediente" -> "Número Expediente"
        - "fecha_apertura" -> "Fecha Apertura"

        Args:
            prop_name: Technical property name

        Returns:
            Human-readable label
        """
        # Remove namespace prefix if present (exp:, pmreg:, cm:, etc.)
        if ":" in prop_name:
            prop_name = prop_name.split(":")[-1]

        # Convert camelCase to Title Case with spaces
        # e.g., "numeroExpediente" -> "Número Expediente"
        result = ""
        for i, char in enumerate(prop_name):
            if char.isupper() and i > 0:
                result += " "
            result += char

        # Convert snake_case to Title Case
        result = result.replace("_", " ")

        # Capitalize first letter of each word
        result = result.title()

        return result

    def _get_type_description(self, semantic_type: SemanticType) -> str:
        """Get human-readable description for semantic type."""
        type_descriptions = {
            SemanticType.CONTRACT: "Contrato",
            SemanticType.AGREEMENT: "Acuerdo",
            SemanticType.AMENDMENT: "Adenda o modificación",
            SemanticType.ANNEX: "Anexo",
            SemanticType.INVOICE: "Factura",
            SemanticType.REPORT: "Informe",
            SemanticType.POLICY: "Política",
            SemanticType.PROCEDURE: "Procedimiento",
            SemanticType.MEMO: "Memorando",
            SemanticType.EMPLOYEE_FILE: "Expediente de empleado",
            SemanticType.FINANCIAL_STATEMENT: "Estado financiero",
            SemanticType.TECHNICAL_SPEC: "Especificación técnica",
        }
        return type_descriptions.get(semantic_type, "Documento")


# Global singleton instance
structural_extractor = StructuralExtractor()
