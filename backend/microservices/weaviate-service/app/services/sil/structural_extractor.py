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
"""

import logging
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

logger = logging.getLogger(__name__)


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
    """

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the extractor."""
        if self._initialized:
            return
        self._initialized = True
        logger.info("✅ StructuralExtractor initialized")

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

        # Infer semantic type
        semantic_type = self._infer_semantic_type(
            file_path=file_path,
            metadata=connector_metadata,
            learned_context=learned_context,
        )

        # Infer domain
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

        return StructuralMetadata(
            document_id=document_id,
            weaviate_document_id=connector_metadata.get("weaviate_id"),
            semantic_type=semantic_type,
            domain=domain,
            folder_path=folder_path,
            folder_semantics=folder_semantics,
            site_id=connector_metadata.get("site_id"),
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

    def _infer_semantic_type(
        self,
        file_path: str,
        metadata: Dict[str, Any],
        learned_context: Dict[str, Any],
    ) -> SemanticType:
        """
        Infer the semantic type of the document.

        Priority:
        1. Explicit document_type in metadata
        2. Learned context from Data Learning System
        3. Pattern matching on filename/path
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

        # Pattern matching on path
        path_lower = file_path.lower()
        for stype, patterns in SEMANTIC_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, path_lower):
                    return stype

        return SemanticType.GENERAL

    def _infer_domain(
        self,
        folder_path: str,
        semantic_type: SemanticType,
        learned_context: Dict[str, Any],
    ) -> DomainType:
        """Infer the domain/area from folder path and semantic type."""
        # Check learned context first
        if learned_context.get("domain"):
            try:
                return DomainType(learned_context["domain"])
            except ValueError:
                pass

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

    def _extract_key_properties(
        self,
        metadata: Dict[str, Any],
        folder_semantics: FolderSemantics,
    ) -> Dict[str, Any]:
        """
        Extract key properties from metadata.

        These are structural properties that can be used for filtering
        and graph traversal - NOT content extracted from the document.
        """
        properties = {}

        # Standard metadata fields
        if metadata.get("title"):
            properties["title"] = metadata["title"]

        if metadata.get("author"):
            properties["author"] = metadata["author"]

        if folder_semantics.client:
            properties["client"] = folder_semantics.client

        if folder_semantics.year:
            properties["year"] = folder_semantics.year

        # Connector-specific properties
        if metadata.get("alfresco_node_type"):
            properties["node_type"] = metadata["alfresco_node_type"]

        if metadata.get("sharepoint_site"):
            properties["site"] = metadata["sharepoint_site"]

        # Contract-specific properties (if in metadata)
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
         Año: 2024. Autor: Juan García."
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

        # Author
        if key_properties.get("author"):
            parts.append(f"Autor: {key_properties['author']}")

        # Join with appropriate separators
        description = " ".join(parts[:3]) + "."
        if len(parts) > 3:
            description += " " + " ".join(parts[3:])

        return description

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
