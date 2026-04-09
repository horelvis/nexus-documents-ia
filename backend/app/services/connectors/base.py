"""
Base Connector Adapter

Abstract base class that defines the interface for all connector implementations.
Each connector (Alfresco, SharePoint, Google Drive, etc.) must implement this interface
to participate in the unified ingestion system.

Design Pattern: Strategy Pattern
- ConnectorAdapter is the strategy interface
- Each concrete adapter (AlfrescoAdapter, SharePointAdapter) is a strategy implementation
- The UnifiedIndexingService is the context that uses strategies polymorphically

Key Responsibilities:
1. list_documents() - Discovery: Find documents matching configured filters
2. download_content() - Retrieval: Download document content
3. health_check() - Monitoring: Verify connectivity and permissions
"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from app.db.models import Connector
from app.schemas.unified_document import (
    UnifiedDocument,
    HealthCheckResult,
    SyncResult,
    ConnectorType,
)

logger = logging.getLogger(__name__)


class ConnectorAdapter(ABC):
    """
    Abstract base class for all connector adapters.

    Each connector type (Alfresco, SharePoint, etc.) must implement this interface
    to be used by the UnifiedIndexingService.

    The adapter pattern allows:
    1. Uniform interface for all connectors
    2. Easy addition of new connector types
    3. Testability via mock adapters
    4. Separation of concerns (connection logic vs orchestration)
    """

    # Class-level identifier for the connector type
    connector_type: ConnectorType

    def __init__(self, connector: Connector, config: Dict[str, Any]):
        """
        Initialize adapter with connector configuration.

        Args:
            connector: Connector model from database
            config: Type-specific configuration (parsed from connector.config)
        """
        self.connector = connector
        self.config = config
        self.connector_id = connector.id

    @abstractmethod
    async def list_documents(
        self,
        modified_after: Optional[datetime] = None,
        skip: int = 0,
        max_items: int = 100,
    ) -> Tuple[List[UnifiedDocument], bool]:
        """
        List documents from the source system.

        This method discovers documents that should be synced. It should:
        1. Apply configured filters (path, MIME type, etc.)
        2. Support incremental sync via modified_after
        3. Support pagination via skip/max_items
        4. Return UnifiedDocument WITHOUT file_bytes (discovery only)

        Args:
            modified_after: Only return documents modified after this date (incremental sync)
            skip: Number of results to skip (pagination)
            max_items: Maximum number of results to return

        Returns:
            Tuple of:
            - List[UnifiedDocument]: Documents found (without content)
            - bool: True if there are more results (pagination)

        Raises:
            ConnectionError: If unable to connect to source
            PermissionError: If access denied
        """
        pass

    @abstractmethod
    async def download_content(self, document: UnifiedDocument) -> bytes:
        """
        Download document content from the source system.

        This method fetches the actual file content. It should:
        1. Use document.external_id to locate the file
        2. Handle large files efficiently (streaming if possible)
        3. Respect timeout configurations

        Args:
            document: UnifiedDocument with external_id set

        Returns:
            bytes: Raw file content

        Raises:
            FileNotFoundError: If document no longer exists
            ConnectionError: If unable to connect to source
            PermissionError: If access denied
            TimeoutError: If download takes too long
        """
        pass

    @abstractmethod
    async def health_check(self) -> HealthCheckResult:
        """
        Verify connector connectivity and permissions.

        This method should:
        1. Test connection to the source system
        2. Verify credentials are valid
        3. Check required permissions exist
        4. Measure response time

        Returns:
            HealthCheckResult with status and details

        Note:
            Should NOT raise exceptions - return unhealthy status instead
        """
        pass

    async def get_document_by_id(self, external_id: str) -> Optional[UnifiedDocument]:
        """
        Get a single document by its external ID.

        Default implementation searches via list_documents with a filter.
        Subclasses may override with more efficient direct lookup.

        Args:
            external_id: Document ID in the source system

        Returns:
            UnifiedDocument if found, None otherwise
        """
        # Default: not implemented, subclasses can override
        logger.warning(
            f"get_document_by_id not implemented for {self.connector_type.value}, "
            "falling back to None"
        )
        return None

    async def delete_document(self, external_id: str) -> bool:
        """
        Delete a document from the source system (if supported).

        Most connectors are read-only, but some may support deletion.

        Args:
            external_id: Document ID in the source system

        Returns:
            True if deleted, False if not supported or failed
        """
        logger.warning(
            f"delete_document not supported for {self.connector_type.value}"
        )
        return False

    def get_rate_limit_config(self) -> Dict[str, Any]:
        """
        Get rate limiting configuration for this connector.

        Returns:
            Dict with rate limit settings:
            - requests_per_second: Max requests per second
            - concurrent_downloads: Max concurrent downloads
            - retry_after_ms: Default retry delay
        """
        return {
            "requests_per_second": 10,
            "concurrent_downloads": 3,
            "retry_after_ms": 1000,
        }

    def supports_incremental_sync(self) -> bool:
        """
        Check if connector supports incremental sync.

        Returns:
            True if modified_after parameter is supported
        """
        return True

    def supports_delta_tokens(self) -> bool:
        """
        Check if connector supports delta tokens for more efficient sync.

        Delta tokens (MS Graph) or pageTokens (Google Drive) allow
        more efficient incremental sync than date-based filtering.

        Returns:
            True if delta tokens are supported
        """
        return False

    def _create_unified_document(
        self,
        external_id: str,
        filename: str,
        owner_id: UUID,
        **kwargs,
    ) -> UnifiedDocument:
        """
        Helper to create UnifiedDocument with common fields pre-filled.

        Args:
            external_id: ID in source system
            filename: Document filename
            owner_id: User who owns the document
            **kwargs: Additional UnifiedDocument fields

        Returns:
            UnifiedDocument with connector fields populated
        """
        from uuid import uuid4

        doc = UnifiedDocument(
            document_id=uuid4(),
            connector_id=self.connector_id,
            connector_type=self.connector_type,
            external_id=external_id,
            filename=filename,
            owner_id=owner_id,
            title=kwargs.get("title", filename),
            **{k: v for k, v in kwargs.items() if k != "title"},
        )

        # Extract extension if not provided
        if not doc.file_extension:
            doc.extract_extension()

        return doc


class ConnectorError(Exception):
    """Base exception for connector errors."""

    def __init__(self, message: str, connector_id: UUID, details: Dict[str, Any] = None):
        super().__init__(message)
        self.connector_id = connector_id
        self.details = details or {}


class ConnectorConnectionError(ConnectorError):
    """Raised when unable to connect to the source system."""
    pass


class ConnectorAuthError(ConnectorError):
    """Raised when authentication fails."""
    pass


class ConnectorPermissionError(ConnectorError):
    """Raised when access is denied."""
    pass


class ConnectorRateLimitError(ConnectorError):
    """Raised when rate limited by the source system."""

    def __init__(
        self,
        message: str,
        connector_id: UUID,
        retry_after_seconds: int = 60,
        details: Dict[str, Any] = None,
    ):
        super().__init__(message, connector_id, details)
        self.retry_after_seconds = retry_after_seconds
