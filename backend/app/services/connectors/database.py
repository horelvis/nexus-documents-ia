"""
Database Connector Adapter

Implements ConnectorAdapter for generic database BLOB storage.
Supports multiple database engines: PostgreSQL, MySQL, MariaDB, SQLite, SQL Server, Oracle.

Features:
- Multi-engine support via SQLAlchemy async
- BLOB, file path, and URL storage types
- Configurable column mapping
- Custom SQL queries
- Incremental sync via timestamp columns

Example usage:
    config = DatabaseConfig(
        engine=DatabaseEngine.POSTGRESQL,
        host="localhost",
        database="documents",
        username="user",
        password="secret",
        table_name="files",
        storage_type=DocumentStorageType.BLOB,
        column_mapping={
            "id": "file_id",
            "content": "file_data",
            "filename": "original_name",
        }
    )
    adapter = DatabaseAdapter(connector, config.model_dump())
    documents, has_more = await adapter.list_documents()
"""

import asyncio
import base64
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncConnection

from app.db.models import Connector
from app.schemas.connector import (
    DatabaseConfig,
    DatabaseEngine,
    DocumentStorageType,
)
from app.schemas.unified_document import (
    ConnectorType,
    HealthCheckResult,
    IndexingStatus,
    UnifiedDocument,
)

from .base import (
    ConnectorAdapter,
    ConnectorConnectionError,
    ConnectorAuthError,
)

logger = logging.getLogger(__name__)


class DatabaseAdapter(ConnectorAdapter):
    """
    Database connector adapter for BLOB storage.

    Connects to various RDBMS via SQLAlchemy async and extracts
    documents stored as BLOBs, file paths, or URLs.

    Supported databases:
    - PostgreSQL (asyncpg)
    - MySQL/MariaDB (aiomysql)
    - SQLite (aiosqlite)
    - SQL Server (aioodbc)
    - Oracle (oracledb)
    """

    connector_type = ConnectorType.DATABASE

    def __init__(self, connector: Connector, config: Dict[str, Any]):
        """
        Initialize database adapter.

        Args:
            connector: Connector model from database
            config: Database configuration (parsed from connector.config)
        """
        super().__init__(connector, config)

        # Parse and validate config
        self.db_config = DatabaseConfig(**config)
        self._engine = None
        self._owner_id = connector.created_by_id

    async def _get_engine(self):
        """Get or create async SQLAlchemy engine."""
        if self._engine is None:
            connection_url = self.db_config.get_connection_url()

            # Engine-specific connect args
            connect_args = {}

            if self.db_config.engine == DatabaseEngine.MSSQL:
                # SQL Server specific options
                connect_args["timeout"] = self.db_config.timeout_seconds

            if self.db_config.ssl_enabled:
                if self.db_config.engine == DatabaseEngine.POSTGRESQL:
                    ssl_context = "require" if self.db_config.ssl_verify else "prefer"
                    connect_args["ssl"] = ssl_context
                elif self.db_config.engine in [DatabaseEngine.MYSQL, DatabaseEngine.MARIADB]:
                    connect_args["ssl"] = {"ca": self.db_config.ssl_ca_cert} if self.db_config.ssl_ca_cert else True

            self._engine = create_async_engine(
                connection_url,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
                pool_recycle=3600,
                connect_args=connect_args if connect_args else None,
            )

        return self._engine

    async def list_documents(
        self,
        modified_after: Optional[datetime] = None,
        skip: int = 0,
        max_items: int = 100,
    ) -> Tuple[List[UnifiedDocument], bool]:
        """
        List documents from the database.

        Args:
            modified_after: Only return documents modified after this date
            skip: Number of results to skip (pagination)
            max_items: Maximum number of results to return

        Returns:
            Tuple of (documents, has_more)
        """
        logger.info(
            f"[{self.connector_id}] Listing documents from database "
            f"(modified_after={modified_after}, skip={skip}, max_items={max_items})"
        )

        try:
            engine = await self._get_engine()
            documents = []

            async with engine.connect() as conn:
                # Build query
                base_query = self.db_config.build_select_query()

                # Add date filter for incremental sync
                if modified_after:
                    modified_col = self.db_config.column_mapping.get("modified_at", "modified_at")
                    if "WHERE" in base_query.upper():
                        base_query += f" AND {modified_col} > :modified_after"
                    else:
                        base_query += f" WHERE {modified_col} > :modified_after"

                # Add pagination
                # Note: Different databases have different syntax
                if self.db_config.engine in [DatabaseEngine.POSTGRESQL, DatabaseEngine.SQLITE]:
                    query = f"{base_query} LIMIT :limit OFFSET :offset"
                elif self.db_config.engine in [DatabaseEngine.MYSQL, DatabaseEngine.MARIADB]:
                    query = f"{base_query} LIMIT :offset, :limit"
                elif self.db_config.engine == DatabaseEngine.MSSQL:
                    query = f"{base_query} OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY"
                elif self.db_config.engine == DatabaseEngine.ORACLE:
                    query = f"SELECT * FROM ({base_query}) WHERE ROWNUM BETWEEN :offset + 1 AND :offset + :limit"
                else:
                    query = f"{base_query} LIMIT :limit OFFSET :offset"

                # Execute query
                params = {
                    "limit": max_items + 1,  # +1 to check if more exists
                    "offset": skip,
                }
                if modified_after:
                    params["modified_after"] = modified_after

                result = await conn.execute(text(query), params)
                rows = result.fetchall()
                columns = result.keys()

                # Check if there are more results
                has_more = len(rows) > max_items
                rows = rows[:max_items]

                # Convert rows to UnifiedDocuments
                for row in rows:
                    row_dict = dict(zip(columns, row))
                    doc = self._parse_row(row_dict)
                    if doc:
                        documents.append(doc)

            logger.info(
                f"[{self.connector_id}] Found {len(documents)} documents "
                f"(has_more={has_more})"
            )
            return documents, has_more

        except Exception as e:
            logger.error(f"[{self.connector_id}] Failed to list documents: {e}")
            raise ConnectorConnectionError(
                f"Database query failed: {e}",
                self.connector_id
            )

    def _parse_row(self, row: Dict[str, Any]) -> Optional[UnifiedDocument]:
        """
        Parse database row into UnifiedDocument.

        Args:
            row: Dictionary with column values

        Returns:
            UnifiedDocument or None if parsing fails
        """
        try:
            # Get mapped values
            external_id = str(row.get("id", ""))
            if not external_id:
                logger.warning("Row missing ID column")
                return None

            filename = row.get("filename", f"document_{external_id}")
            mime_type = row.get("mime_type")
            size_bytes = row.get("size", 0)

            # Parse dates
            source_created = None
            source_modified = None

            created_raw = row.get("created_at")
            if created_raw:
                if isinstance(created_raw, datetime):
                    source_created = created_raw
                elif isinstance(created_raw, str):
                    try:
                        source_created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                    except Exception:
                        pass

            modified_raw = row.get("modified_at")
            if modified_raw:
                if isinstance(modified_raw, datetime):
                    source_modified = modified_raw
                elif isinstance(modified_raw, str):
                    try:
                        source_modified = datetime.fromisoformat(modified_raw.replace("Z", "+00:00"))
                    except Exception:
                        pass

            # Build external path/URL based on storage type
            external_path = None
            external_url = None

            if self.db_config.storage_type == DocumentStorageType.FILE_PATH:
                relative_path = row.get("content", "")
                if self.db_config.file_base_path:
                    external_path = os.path.join(self.db_config.file_base_path, relative_path)
                else:
                    external_path = relative_path
            elif self.db_config.storage_type == DocumentStorageType.URL:
                external_url = row.get("content", "")
                external_path = external_url

            # Extract file extension
            file_extension = None
            if filename and "." in filename:
                file_extension = filename.rsplit(".", 1)[-1].lower()

            # Build custom metadata from extra columns
            custom_metadata = {
                "database_engine": self.db_config.engine.value,
                "table": self.db_config.table_name,
                "storage_type": self.db_config.storage_type.value,
            }

            # Add extra columns to metadata
            for col in self.db_config.extra_columns:
                if col in row and row[col] is not None:
                    custom_metadata[col] = row[col]

            # Add all non-standard columns as metadata
            standard_cols = {"id", "content", "filename", "mime_type", "size", "created_at", "modified_at"}
            for key, value in row.items():
                if key not in standard_cols and value is not None:
                    # Handle non-serializable types
                    if isinstance(value, (bytes, bytearray)):
                        continue  # Skip binary data
                    elif isinstance(value, datetime):
                        custom_metadata[key] = value.isoformat()
                    else:
                        custom_metadata[key] = value

            return self._create_unified_document(
                external_id=external_id,
                filename=filename,
                owner_id=self._owner_id or self.tenant_id,
                title=filename,
                mime_type=mime_type,
                size_bytes=size_bytes or 0,
                file_extension=file_extension,
                external_path=external_path,
                external_url=external_url,
                source_created_at=source_created,
                source_modified_at=source_modified,
                indexing_status=IndexingStatus.PENDING,
                custom_metadata=custom_metadata,
            )

        except Exception as e:
            logger.error(f"Failed to parse row: {e}")
            return None

    async def download_content(self, document: UnifiedDocument) -> bytes:
        """
        Download document content.

        For BLOB storage: fetches from database
        For file path: reads from disk
        For URL: fetches via HTTP

        Args:
            document: UnifiedDocument with external_id

        Returns:
            bytes: File content
        """
        logger.info(
            f"[{self.connector_id}] Downloading {document.filename} "
            f"(storage_type={self.db_config.storage_type.value})"
        )

        try:
            if self.db_config.storage_type == DocumentStorageType.BLOB:
                return await self._download_blob(document.external_id)
            elif self.db_config.storage_type == DocumentStorageType.FILE_PATH:
                return await self._download_file(document.external_path)
            elif self.db_config.storage_type == DocumentStorageType.URL:
                return await self._download_url(document.external_url or document.external_path)
            else:
                raise ValueError(f"Unknown storage type: {self.db_config.storage_type}")

        except Exception as e:
            logger.error(f"[{self.connector_id}] Download failed: {e}")
            raise

    async def _download_blob(self, external_id: str) -> bytes:
        """Download BLOB content from database."""
        engine = await self._get_engine()

        content_col = self.db_config.column_mapping.get("content", "content")
        id_col = self.db_config.column_mapping.get("id", "id")
        table = self.db_config.table_name

        if self.db_config.schema_name:
            table = f"{self.db_config.schema_name}.{table}"

        query = f"SELECT {content_col} FROM {table} WHERE {id_col} = :doc_id"

        async with engine.connect() as conn:
            result = await conn.execute(text(query), {"doc_id": external_id})
            row = result.fetchone()

            if not row:
                raise FileNotFoundError(f"Document {external_id} not found")

            content = row[0]

            if content is None:
                raise ValueError(f"Document {external_id} has NULL content")

            # Handle different content formats
            if isinstance(content, bytes):
                return content
            elif isinstance(content, str):
                # Might be base64 encoded
                try:
                    return base64.b64decode(content)
                except Exception:
                    return content.encode("utf-8")
            elif isinstance(content, memoryview):
                return bytes(content)
            else:
                raise ValueError(f"Unknown content type: {type(content)}")

    async def _download_file(self, file_path: str) -> bytes:
        """Download content from file system."""
        if not file_path:
            raise ValueError("File path is empty")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Check file size
        file_size = os.path.getsize(file_path)
        max_size = self.db_config.max_blob_size_mb * 1024 * 1024

        if file_size > max_size:
            raise ValueError(
                f"File too large: {file_size / 1024 / 1024:.1f}MB "
                f"(max: {self.db_config.max_blob_size_mb}MB)"
            )

        # Read file asynchronously
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: open(file_path, "rb").read()
        )

    async def _download_url(self, url: str) -> bytes:
        """Download content from URL."""
        if not url:
            raise ValueError("URL is empty")

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=float(self.db_config.timeout_seconds),
                write=10.0,
                pool=5.0,
            )
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    async def health_check(self) -> HealthCheckResult:
        """
        Check database connectivity.

        Tests:
        1. Connection establishment
        2. Query execution
        3. Response time
        """
        start_time = time.time()

        try:
            engine = await self._get_engine()

            async with engine.connect() as conn:
                # Simple connectivity test
                if self.db_config.engine == DatabaseEngine.ORACLE:
                    test_query = "SELECT 1 FROM DUAL"
                else:
                    test_query = "SELECT 1"

                result = await conn.execute(text(test_query))
                result.fetchone()

                # Optional: count documents
                doc_count = None
                if self.db_config.table_name:
                    try:
                        table = self.db_config.table_name
                        if self.db_config.schema_name:
                            table = f"{self.db_config.schema_name}.{table}"
                        count_result = await conn.execute(
                            text(f"SELECT COUNT(*) FROM {table}")
                        )
                        doc_count = count_result.scalar()
                    except Exception:
                        pass

                elapsed_ms = (time.time() - start_time) * 1000

                return HealthCheckResult(
                    is_healthy=True,
                    status="healthy",
                    message=f"Connected to {self.db_config.engine.value} database",
                    details={
                        "engine": self.db_config.engine.value,
                        "database": self.db_config.database,
                        "host": self.db_config.host,
                        "table": self.db_config.table_name,
                        "document_count": doc_count,
                    },
                    response_time_ms=elapsed_ms,
                )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            error_msg = str(e)

            # Detect specific error types
            if "password" in error_msg.lower() or "authentication" in error_msg.lower():
                return HealthCheckResult(
                    is_healthy=False,
                    status="unhealthy",
                    message="Authentication failed - check credentials",
                    details={"error": error_msg},
                    response_time_ms=elapsed_ms,
                )

            if "connect" in error_msg.lower() or "refused" in error_msg.lower():
                return HealthCheckResult(
                    is_healthy=False,
                    status="unhealthy",
                    message=f"Connection failed to {self.db_config.host}:{self.db_config.port or self.db_config.get_default_port()}",
                    details={"error": error_msg},
                    response_time_ms=elapsed_ms,
                )

            return HealthCheckResult(
                is_healthy=False,
                status="unhealthy",
                message=f"Health check failed: {error_msg[:100]}",
                details={"error": error_msg},
                response_time_ms=elapsed_ms,
            )

    async def get_document_by_id(self, external_id: str) -> Optional[UnifiedDocument]:
        """
        Get a single document by ID.

        Args:
            external_id: Document ID in the database

        Returns:
            UnifiedDocument if found, None otherwise
        """
        try:
            engine = await self._get_engine()

            # Build query for single document
            id_col = self.db_config.column_mapping.get("id", "id")
            base_query = self.db_config.build_select_query()

            if "WHERE" in base_query.upper():
                query = f"{base_query} AND {id_col} = :doc_id"
            else:
                query = f"{base_query} WHERE {id_col} = :doc_id"

            async with engine.connect() as conn:
                result = await conn.execute(text(query), {"doc_id": external_id})
                row = result.fetchone()

                if not row:
                    return None

                columns = result.keys()
                row_dict = dict(zip(columns, row))
                return self._parse_row(row_dict)

        except Exception as e:
            logger.error(f"[{self.connector_id}] Failed to get document {external_id}: {e}")
            return None

    def supports_incremental_sync(self) -> bool:
        """Check if connector supports incremental sync."""
        # Supports if modified_at column is mapped
        return bool(self.db_config.column_mapping.get("modified_at"))

    def get_rate_limit_config(self) -> Dict[str, Any]:
        """Get rate limiting configuration."""
        return {
            "requests_per_second": 50,  # Database can handle more
            "concurrent_downloads": 10,
            "retry_after_ms": 500,
        }

    async def close(self):
        """Close database connection pool."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
