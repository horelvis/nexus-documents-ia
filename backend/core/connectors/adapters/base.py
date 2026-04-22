"""
Base Metadata Adapter

Abstract base class for all metadata adapters. Each adapter knows how to
extract and normalize metadata from its source system into NormalizedMetadata.
"""

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Type

from ..metadata_schema import (
    NormalizedMetadata,
    MetadataRichness,
    DocumentOrigin,
    TemporalInfo,
    OwnershipInfo,
    ClassificationInfo,
    BusinessProperties,
    PathComponents,
)

logger = logging.getLogger(__name__)


class PathIntelligence:
    """
    Extracts information from file paths when rich metadata is not available.

    This is the fallback strategy for metadata-poor connectors (filesystem, database).
    It uses patterns, heuristics, and naming conventions to infer structure.
    """

    # Common year patterns in paths
    YEAR_PATTERNS = [
        r'/(\d{4})/',           # /2024/
        r'_(\d{4})_',           # _2024_
        r'-(\d{4})-',           # -2024-
        r'(\d{4})[_-]',         # 2024_ or 2024-
        r'[_-](\d{4})',         # _2024 or -2024
    ]

    # Month patterns
    MONTH_PATTERNS = [
        r'/(\d{4})/(\d{1,2})/',       # /2024/01/
        r'/(\d{4})[_-](\d{2})/',      # /2024-01/
        r'(\d{4})[_-](\d{2})[_-]',    # 2024-01-
    ]

    # Document type patterns (from filename)
    TYPE_PATTERNS = {
        'contract': [r'contrat[oa]s?', r'contract', r'acuerdo', r'agreement'],
        'invoice': [r'factura', r'invoice', r'bill', r'recibo', r'receipt'],
        'report': [r'informe', r'report', r'reporte', r'analisis'],
        'proposal': [r'propuesta', r'proposal', r'cotizaci[oó]n', r'quote'],
        'manual': [r'manual', r'guide', r'gu[ií]a', r'handbook'],
        'policy': [r'pol[ií]tica', r'policy', r'norma', r'procedure'],
        'memo': [r'memo', r'circular', r'comunicado', r'notice'],
        'presentation': [r'presentaci[oó]n', r'presentation', r'slides'],
        'spreadsheet': [r'datos', r'data', r'excel', r'hoja'],
        'email': [r'email', r'correo', r'mensaje', r'mail'],
        'legal': [r'legal', r'jur[ií]dico', r'sentencia', r'demanda'],
    }

    # Client/project extraction patterns
    CLIENT_PATTERNS = [
        r'/clientes?/([^/]+)/',
        r'/clients?/([^/]+)/',
        r'/customer/([^/]+)/',
        r'/([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*[-_]\s*(?:contrat|project|factura)',
    ]

    PROJECT_PATTERNS = [
        r'/proyectos?/([^/]+)/',
        r'/projects?/([^/]+)/',
        r'/([^/]+)-proyecto-',
        r'/([^/]+)-project-',
    ]

    @classmethod
    def parse_path(cls, path: str) -> PathComponents:
        """
        Parse a file path into components with intelligent extraction.
        """
        # Normalize path separators
        path = path.replace('\\', '/')

        # Extract basic components
        parts = path.rstrip('/').split('/')
        filename = parts[-1] if parts else ""
        folder_chain = parts[:-1] if len(parts) > 1 else []

        # Extract extension
        ext_match = re.search(r'\.([a-zA-Z0-9]+)$', filename)
        extension = ext_match.group(1).lower() if ext_match else None

        # Parent folder
        parent = folder_chain[-1] if folder_chain else None

        # Build components
        components = PathComponents(
            full_path=path,
            filename=filename,
            extension=extension,
            parent_folder=parent,
            folder_chain=folder_chain,
            depth=len(folder_chain),
        )

        # Try to extract year
        components.year_from_path = cls._extract_year(path)

        # Try to extract month (if year found)
        if components.year_from_path:
            month = cls._extract_month(path, components.year_from_path)
            if month:
                components.month_from_path = month

        # Try to extract client name
        components.client_from_path = cls._extract_client(path)

        # Try to extract project name
        components.project_from_path = cls._extract_project(path)

        return components

    @classmethod
    def _extract_year(cls, path: str) -> Optional[int]:
        """Extract year from path using patterns."""
        current_year = datetime.now().year

        for pattern in cls.YEAR_PATTERNS:
            match = re.search(pattern, path)
            if match:
                year = int(match.group(1))
                # Sanity check: year should be reasonable (1900-current+1)
                if 1900 <= year <= current_year + 1:
                    return year
        return None

    @classmethod
    def _extract_month(cls, path: str, year: int) -> Optional[int]:
        """Extract month from path if year is known."""
        for pattern in cls.MONTH_PATTERNS:
            match = re.search(pattern, path)
            if match:
                found_year = int(match.group(1))
                if found_year == year:
                    month = int(match.group(2))
                    if 1 <= month <= 12:
                        return month
        return None

    @classmethod
    def _extract_client(cls, path: str) -> Optional[str]:
        """Extract client name from path."""
        path_lower = path.lower()
        for pattern in cls.CLIENT_PATTERNS:
            match = re.search(pattern, path_lower)
            if match:
                client = match.group(1).strip()
                # Clean up common prefixes/suffixes
                client = re.sub(r'^(client[_-]?|cliente[_-]?)', '', client, flags=re.IGNORECASE)
                return client.title() if client else None
        return None

    @classmethod
    def _extract_project(cls, path: str) -> Optional[str]:
        """Extract project name from path."""
        path_lower = path.lower()
        for pattern in cls.PROJECT_PATTERNS:
            match = re.search(pattern, path_lower)
            if match:
                project = match.group(1).strip()
                return project.title() if project else None
        return None

    @classmethod
    def infer_semantic_type(cls, filename: str, path: str) -> tuple[Optional[str], float]:
        """
        Infer document semantic type from filename and path.

        Returns:
            Tuple of (type, confidence)
        """
        text = f"{filename} {path}".lower()

        for doc_type, patterns in cls.TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    # Higher confidence if in filename vs path
                    confidence = 0.7 if re.search(pattern, filename, re.IGNORECASE) else 0.5
                    return doc_type, confidence

        return None, 0.0


class MetadataAdapter(ABC):
    """
    Abstract base class for metadata adapters.

    Each connector type implements this to normalize its metadata
    into the common NormalizedMetadata schema.
    """

    # Subclasses must define these
    connector_type: str = "unknown"
    richness_level: MetadataRichness = MetadataRichness.MINIMAL

    def __init__(self):
        self._path_intelligence = PathIntelligence()

    @abstractmethod
    def normalize(
        self,
        document_id: str,
        tenant_id: str,
        raw_metadata: Dict[str, Any],
        file_path: Optional[str] = None,
    ) -> NormalizedMetadata:
        """
        Normalize source-specific metadata into common schema.

        Args:
            document_id: Unique document identifier
            tenant_id: Tenant identifier
            raw_metadata: Source system metadata (connector-specific)
            file_path: File path in source system

        Returns:
            NormalizedMetadata with all available information
        """
        pass

    def _create_base_metadata(
        self,
        document_id: str,
        tenant_id: str,
        external_id: str,
        file_path: str,
        raw_metadata: Dict[str, Any],
    ) -> NormalizedMetadata:
        """
        Create base NormalizedMetadata with path parsing.

        Subclasses call this first, then enrich with connector-specific data.
        """
        # Parse path
        path_components = PathIntelligence.parse_path(file_path or "")

        # Create origin
        origin = DocumentOrigin(
            connector_type=self.connector_type,
            external_id=external_id,
            external_path=file_path,
        )

        return NormalizedMetadata(
            document_id=document_id,
            tenant_id=tenant_id,
            richness_level=self.richness_level,
            origin=origin,
            path=path_components,
            raw_metadata=raw_metadata,
        )

    def _apply_path_inference(self, metadata: NormalizedMetadata) -> None:
        """
        Apply path-based inference for missing fields.

        This is called after connector-specific processing to fill gaps.
        """
        # Infer semantic type if not set
        if not metadata.classification.semantic_type:
            inferred_type, confidence = PathIntelligence.infer_semantic_type(
                metadata.path.filename,
                metadata.path.full_path
            )
            if inferred_type:
                metadata.classification.semantic_type = inferred_type
                metadata.classification.semantic_type_confidence = confidence
                metadata.classification.semantic_type_source = "path_inference"

        # Infer client if not set
        if not metadata.business.client_name and metadata.path.client_from_path:
            metadata.business.client_name = metadata.path.client_from_path

        # Infer project if not set
        if not metadata.business.project_name and metadata.path.project_from_path:
            metadata.business.project_name = metadata.path.project_from_path


class MetadataAdapterRegistry:
    """
    Registry for metadata adapters.

    Allows getting the appropriate adapter for a connector type.
    """

    _adapters: Dict[str, Type[MetadataAdapter]] = {}
    _instances: Dict[str, MetadataAdapter] = {}

    @classmethod
    def register(cls, connector_type: str, adapter_class: Type[MetadataAdapter]) -> None:
        """Register an adapter for a connector type."""
        cls._adapters[connector_type] = adapter_class
        logger.debug(f"Registered metadata adapter: {connector_type} -> {adapter_class.__name__}")

    @classmethod
    def get_adapter(cls, connector_type: str) -> MetadataAdapter:
        """
        Get an adapter instance for a connector type.

        Returns a cached instance if available.
        """
        if connector_type not in cls._instances:
            adapter_class = cls._adapters.get(connector_type)
            if not adapter_class:
                # Fallback to generic adapter
                logger.warning(f"No adapter for {connector_type}, using GenericMetadataAdapter")
                adapter_class = GenericMetadataAdapter
            cls._instances[connector_type] = adapter_class()

        return cls._instances[connector_type]

    @classmethod
    def list_adapters(cls) -> List[str]:
        """List all registered connector types."""
        return list(cls._adapters.keys())


class GenericMetadataAdapter(MetadataAdapter):
    """
    Generic fallback adapter for unknown connector types.

    Uses only path intelligence for metadata inference.
    """

    connector_type = "generic"
    richness_level = MetadataRichness.MINIMAL

    def normalize(
        self,
        document_id: str,
        tenant_id: str,
        raw_metadata: Dict[str, Any],
        file_path: Optional[str] = None,
    ) -> NormalizedMetadata:
        """Normalize using only path inference."""
        metadata = self._create_base_metadata(
            document_id=document_id,
            tenant_id=tenant_id,
            external_id=raw_metadata.get("external_id", document_id),
            file_path=file_path or raw_metadata.get("path", ""),
            raw_metadata=raw_metadata,
        )

        # Extract basic file info if available
        if "size" in raw_metadata:
            metadata.file_size = raw_metadata["size"]
        if "mime_type" in raw_metadata:
            metadata.mime_type = raw_metadata["mime_type"]

        # Apply path inference for everything else
        self._apply_path_inference(metadata)

        return metadata
