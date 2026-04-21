"""
Channel Integration Tools for Emma.

These tools allow Emma to search content indexed from external channels
(Gmail, Google Drive, etc.) that users have connected.

The tools query the same Weaviate collection as regular documents, but
filter by source_type to target specific channels.

Channel Data Flow:
    1. User connects channel (Gmail, Drive) via OAuth
    2. ChannelService syncs content to Weaviate (background job)
    3. Documents are indexed with source_type and channel_id metadata
    4. Emma uses these tools to search channel content
    5. Results include original URLs for user to access source

PRIVACY NOTE:
    Personal channels (Gmail) are filtered by user_id to ensure users
    can only access their own content. Shared channels (Google Drive with
    sharing enabled) may allow access across users within the same tenant.

Note: These tools search INDEXED content, not the source directly.
      For real-time source access, see the OAuth tools module.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from app.services.weaviate_service import WeaviateService
from app.schemas.weaviate import SearchRequest
from app.core.security import get_tenant_collection_name

from .base import (
    BaseTool,
    ToolCall,
    ToolDefinition,
    ToolExecutionContext,
    ToolParameter,
    ToolParameterType,
    ToolResult,
    ToolResultStatus,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Parameter Models
# =============================================================================

class SearchEmailsParams(BaseModel):
    """Parameters for email search tool."""
    query: str = Field(..., description="Search query for emails")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum number of results")
    from_sender: Optional[str] = Field(default=None, description="Filter by sender email/name")
    subject_contains: Optional[str] = Field(default=None, description="Filter by subject text")


class SearchDriveParams(BaseModel):
    """Parameters for Google Drive search tool."""
    query: str = Field(..., description="Search query for Drive files")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum number of results")
    file_type: Optional[str] = Field(
        default=None,
        description="Filter by file type (pdf, docx, spreadsheet, etc.)"
    )
    folder: Optional[str] = Field(default=None, description="Filter by folder name")


class SearchChannelParams(BaseModel):
    """Generic parameters for any channel search."""
    query: str = Field(..., description="Search query")
    source_type: str = Field(..., description="Channel type (gmail, google_drive, etc.)")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum results")
    filters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata filters"
    )


# =============================================================================
# Search Emails Tool
# =============================================================================

class SearchEmailsTool(BaseTool[SearchEmailsParams]):
    """
    Search emails indexed from connected Gmail accounts.

    This tool searches emails that have been synced and indexed
    from the user's connected Gmail channels.

    Results include:
    - Email subject and snippet
    - Sender information
    - Date received
    - Link to original email
    """

    def __init__(self, weaviate_service: Optional[WeaviateService] = None):
        """
        Initialize with optional pre-configured service.

        Args:
            weaviate_service: Optional WeaviateService instance
        """
        self._weaviate = weaviate_service

    @property
    def name(self) -> str:
        return "search_emails"

    @property
    def category(self) -> str:
        return "channel"

    @property
    def requires_auth(self) -> bool:
        return False  # Searches indexed content, not live Gmail

    @property
    def timeout_seconds(self) -> float:
        return 15.0

    def get_params_class(self) -> Type[SearchEmailsParams]:
        return SearchEmailsParams

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Search emails from the user's connected Gmail account. "
                "Use this to find relevant emails, conversations, and "
                "email attachments. Returns subject, sender, date, and content snippets."
            ),
            category=self.category,
            parameters=[
                ToolParameter(
                    name="query",
                    type=ToolParameterType.STRING,
                    description="Search terms to find in email content, subject, or sender",
                    required=True
                ),
                ToolParameter(
                    name="limit",
                    type=ToolParameterType.INTEGER,
                    description="Maximum number of emails to return (1-20, default 5)",
                    required=False,
                    default=5
                ),
                ToolParameter(
                    name="from_sender",
                    type=ToolParameterType.STRING,
                    description="Filter by sender email address or name",
                    required=False
                ),
                ToolParameter(
                    name="subject_contains",
                    type=ToolParameterType.STRING,
                    description="Filter to emails with this text in subject",
                    required=False
                ),
            ]
        )

    async def execute(
        self,
        params: SearchEmailsParams,
        context: ToolExecutionContext
    ) -> ToolResult:
        """
        Search indexed emails across the unified documents collection.

        Single-tenant: collections are globally fixed (see
        ``DOCUMENTS_COLLECTION`` in weaviate_service). Personal emails
        are scoped by ``user_id`` filter — users only see their own mail.

        Args:
            params: Search parameters
            context: Execution context (user_id + user_roles)

        Returns:
            ToolResult with matching emails
        """
        call_id = context.metadata.get("call_id", "")

        try:
            # Get or create Weaviate service
            weaviate = self._weaviate or WeaviateService()
            await weaviate.initialize()

            # Single-tenant: one global documents collection
            from app.services.weaviate_service import DOCUMENTS_COLLECTION
            search_collections = [DOCUMENTS_COLLECTION]

            # Build filters (will only be applied if collection has the property)
            filters = {"source_type": "gmail"}

            # PRIVACY: Emails are personal content - always filter by user_id
            # This ensures users can only see their own emails.
            if context.user_id:
                filters["user_id"] = context.user_id
                logger.debug(f"Applying user_id filter for email privacy: {context.user_id[:8]}...")
            else:
                logger.warning("⚠️ No user_id in context - email search may return results from other users!")

            if params.from_sender:
                filters["metadata.from"] = params.from_sender

            if params.subject_contains:
                filters["metadata.subject"] = params.subject_contains

            # Search the documents collection (gmail content is indexed there
            # with source_type="gmail" for filtering).
            results = await weaviate.search_across_collections(
                collections=search_collections,
                query=params.query,
                user_roles=context.user_roles,
                limit=params.limit,
                filters=filters,
                search_type="hybrid"
            )

            # Format results for LLM consumption
            # Filter to only include email-type documents
            formatted_results = []
            for doc_dict in results:
                metadata = doc_dict.get("metadata", {})
                content = doc_dict.get("content", "")
                doc_type = doc_dict.get("document_type", "")

                # Include if it's an email or has email-like metadata
                is_email = (
                    doc_type == "email" or
                    "from" in metadata or
                    "@" in str(metadata.get("from", "")) or
                    "subject" in metadata
                )

                if is_email:
                    # Use full content for emails (up to 4000 chars to fit in context)
                    # Previously limited to 300 chars which truncated most emails
                    email_content = content[:4000] + "..." if len(content) > 4000 else content
                    formatted_results.append({
                        "subject": metadata.get("subject", doc_dict.get("title", "No subject")),
                        "from": metadata.get("from", "Unknown sender"),
                        "date": metadata.get("date", "Unknown date"),
                        "content": email_content,  # Full email content, not just snippet
                        "url": doc_dict.get("external_url", metadata.get("web_link", "")),
                        "_source": doc_dict.get("_source_collection", "")
                    })

            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status=ToolResultStatus.SUCCESS,
                data={
                    "emails": formatted_results,
                    "total_found": len(formatted_results),
                    "query": params.query,
                    "collections_searched": len(search_collections)
                },
                metadata={
                    "source_type": "gmail",
                    "user_id": context.user_id,
                }
            )

        except Exception as e:
            logger.exception(f"Error searching emails: {e}")
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status=ToolResultStatus.ERROR,
                error=f"Failed to search emails: {str(e)}"
            )


# =============================================================================
# Search Drive Tool
# =============================================================================

class SearchDriveTool(BaseTool[SearchDriveParams]):
    """
    Search files indexed from connected Google Drive.

    This tool searches documents that have been synced and indexed
    from the user's connected Google Drive channels.

    Results include:
    - File name and type
    - Content snippet
    - Link to original file
    """

    def __init__(self, weaviate_service: Optional[WeaviateService] = None):
        self._weaviate = weaviate_service

    @property
    def name(self) -> str:
        return "search_drive"

    @property
    def category(self) -> str:
        return "channel"

    @property
    def requires_auth(self) -> bool:
        return False

    @property
    def timeout_seconds(self) -> float:
        return 15.0

    def get_params_class(self) -> Type[SearchDriveParams]:
        return SearchDriveParams

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Search files from the user's connected Google Drive. "
                "Use this to find documents, spreadsheets, presentations, and PDFs. "
                "Returns file names, content snippets, and links."
            ),
            category=self.category,
            parameters=[
                ToolParameter(
                    name="query",
                    type=ToolParameterType.STRING,
                    description="Search terms to find in file content or name",
                    required=True
                ),
                ToolParameter(
                    name="limit",
                    type=ToolParameterType.INTEGER,
                    description="Maximum number of files to return (1-20, default 5)",
                    required=False,
                    default=5
                ),
                ToolParameter(
                    name="file_type",
                    type=ToolParameterType.STRING,
                    description="Filter by type: pdf, docx, xlsx, pptx, txt, gdoc, gsheet, gslides",
                    required=False
                ),
                ToolParameter(
                    name="folder",
                    type=ToolParameterType.STRING,
                    description="Filter by folder name",
                    required=False
                ),
            ]
        )

    async def execute(
        self,
        params: SearchDriveParams,
        context: ToolExecutionContext
    ) -> ToolResult:
        """
        Search indexed Google Drive files across the unified documents
        collection.

        Args:
            params: Search parameters
            context: Execution context (user_id + user_roles)

        Returns:
            ToolResult with matching files
        """
        call_id = context.metadata.get("call_id", "")

        try:
            weaviate = self._weaviate or WeaviateService()
            await weaviate.initialize()

            # Single-tenant: one global documents collection
            from app.services.weaviate_service import DOCUMENTS_COLLECTION
            search_collections = [DOCUMENTS_COLLECTION]

            # Build filters (will only be applied if collection has the property)
            filters = {"source_type": "google_drive"}

            # PRIVACY: Google Drive files are filtered by user_id by default.
            if context.user_id:
                filters["user_id"] = context.user_id
                logger.debug(f"Applying user_id filter for Drive privacy: {context.user_id[:8]}...")
            else:
                logger.warning("⚠️ No user_id in context - Drive search may return results from other users!")

            if params.file_type:
                filters["metadata.file_type"] = params.file_type

            if params.folder:
                filters["metadata.folder"] = params.folder

            # Search the documents collection
            results = await weaviate.search_across_collections(
                collections=search_collections,
                query=params.query,
                user_roles=context.user_roles,
                limit=params.limit,
                filters=filters,
                search_type="hybrid"
            )

            # Format results, filtering to Drive-type documents
            formatted_results = []
            for doc_dict in results:
                metadata = doc_dict.get("metadata", {})
                content = doc_dict.get("content", "")

                # Include files that look like Drive documents
                is_drive_file = (
                    doc_dict.get("document_type") in ["file", "document", "spreadsheet", "presentation"] or
                    metadata.get("file_type") is not None or
                    metadata.get("mime_type") is not None
                )

                if is_drive_file:
                    # Use more content for Drive files (up to 3000 chars)
                    # Previously limited to 300 chars which truncated most documents
                    file_content = content[:3000] + "..." if len(content) > 3000 else content
                    formatted_results.append({
                        "name": doc_dict.get("title", metadata.get("name", "Untitled")),
                        "type": metadata.get("file_type", metadata.get("mime_type", "unknown")),
                        "content": file_content,  # More content instead of just snippet
                        "url": doc_dict.get("external_url", metadata.get("web_link", "")),
                        "_source": doc_dict.get("_source_collection", "")
                    })

            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status=ToolResultStatus.SUCCESS,
                data={
                    "files": formatted_results,
                    "total_found": len(formatted_results),
                    "query": params.query,
                    "collections_searched": len(search_collections)
                },
                metadata={
                    "source_type": "google_drive",
                    "user_id": context.user_id,
                }
            )

        except Exception as e:
            logger.exception(f"Error searching Drive: {e}")
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status=ToolResultStatus.ERROR,
                error=f"Failed to search Drive: {str(e)}"
            )


# =============================================================================
# Generic Channel Search Tool
# =============================================================================

class SearchChannelTool(BaseTool[SearchChannelParams]):
    """
    Generic tool for searching any indexed channel.

    This is a flexible tool that can search any channel type.
    Useful for future channel integrations.
    """

    def __init__(self, weaviate_service: Optional[WeaviateService] = None):
        self._weaviate = weaviate_service

    @property
    def name(self) -> str:
        return "search_channel"

    @property
    def category(self) -> str:
        return "channel"

    def get_params_class(self) -> Type[SearchChannelParams]:
        return SearchChannelParams

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Search content from a specific connected channel. "
                "Specify the source_type (gmail, google_drive, slack, etc.) "
                "to search that channel's indexed content."
            ),
            category=self.category,
            parameters=[
                ToolParameter(
                    name="query",
                    type=ToolParameterType.STRING,
                    description="Search terms",
                    required=True
                ),
                ToolParameter(
                    name="source_type",
                    type=ToolParameterType.STRING,
                    description="Channel type to search",
                    required=True,
                    enum=["gmail", "google_drive", "slack", "salesforce", "external_db"]
                ),
                ToolParameter(
                    name="limit",
                    type=ToolParameterType.INTEGER,
                    description="Maximum results (1-20)",
                    required=False,
                    default=5
                ),
            ]
        )

    async def execute(
        self,
        params: SearchChannelParams,
        context: ToolExecutionContext
    ) -> ToolResult:
        """
        Search content from a specific channel across the unified documents
        collection.
        """
        call_id = context.metadata.get("call_id", "")

        try:
            weaviate = self._weaviate or WeaviateService()
            await weaviate.initialize()

            # Single-tenant: one global documents collection
            from app.services.weaviate_service import DOCUMENTS_COLLECTION
            search_collections = [DOCUMENTS_COLLECTION]

            # Build filters (will only be applied if collection has the property)
            filters = {"source_type": params.source_type}

            # PRIVACY: Apply user_id filter for personal channels
            personal_channels = {"gmail", "outlook", "slack_dm", "personal_drive"}
            if params.source_type.lower() in personal_channels:
                if context.user_id:
                    filters["user_id"] = context.user_id
                    logger.debug(f"Applying user_id filter for personal channel: {params.source_type}")
                else:
                    logger.warning(f"⚠️ No user_id for personal channel {params.source_type}")

            if params.filters:
                filters.update(params.filters)

            # Search the documents collection
            results = await weaviate.search_across_collections(
                collections=search_collections,
                query=params.query,
                user_roles=context.user_roles,
                limit=params.limit,
                filters=filters,
                search_type="hybrid"
            )

            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status=ToolResultStatus.SUCCESS,
                data={
                    "results": results,
                    "total_found": len(results),
                    "source_type": params.source_type,
                    "collections_searched": len(search_collections)
                }
            )

        except Exception as e:
            logger.exception(f"Error searching channel {params.source_type}: {e}")
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status=ToolResultStatus.ERROR,
                error=str(e)
            )


# =============================================================================
# Registration
# =============================================================================

def register_channel_tools(registry) -> None:
    """
    Register all channel tools with the registry.

    Call this during application startup.

    Args:
        registry: ToolRegistry instance
    """
    registry.register(SearchEmailsTool())
    registry.register(SearchDriveTool())
    registry.register(SearchChannelTool())
    logger.info("Registered channel integration tools")
