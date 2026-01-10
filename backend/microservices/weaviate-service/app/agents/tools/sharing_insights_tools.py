"""
Sharing Insights Tools for Agent Framework

These functions provide Emma AI with the ability to query document sharing
and site guest information from the PostgreSQL database via REST API.

IMPORTANT: These tools DO NOT access the database directly. They call the
main API's /sharing-insights endpoints via HTTP.

Parameters use Annotated[type, Field(description="...")] format for
proper schema generation.

FRAMEWORK: Microsoft Agent Framework
"""

import json
import logging
from typing import Annotated, Optional

from pydantic import Field

from app.core.execution_context import resolve_tenant_id
from app.services.sharing_insights_client import get_sharing_insights_client

# Import ai_function from Agent Framework
try:
    from agent_framework import ai_function
except ImportError:
    # Fallback identity decorator if Agent Framework not installed
    def ai_function(func):
        return func

logger = logging.getLogger(__name__)


def _format_response(data: dict, max_items: int = 20) -> str:
    """Format API response as JSON string for agent consumption."""
    # Truncate lists if too long
    for key, value in data.items():
        if isinstance(value, list) and len(value) > max_items:
            data[key] = value[:max_items]
            data[f"{key}_truncated"] = True
            data[f"{key}_total"] = len(value)

    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


# =============================================================================
# Document Shares Tools
# =============================================================================

@ai_function
async def query_recent_shares(
    tenant_id: Annotated[str, Field(description="Tenant ID for data isolation")],
    days: Annotated[int, Field(description="Number of days to look back")] = 7,
    limit: Annotated[int, Field(description="Maximum number of results")] = 20,
) -> str:
    """
    Get documents that have been shared recently.

    Use this tool to answer questions like:
    - "What documents have I shared this week?"
    - "Show me recent document shares"
    - "What files did I share in the last month?"

    Args:
        tenant_id: Tenant identifier for data isolation
        days: How many days to look back (default 7, max 365)
        limit: Maximum results to return (default 20)

    Returns:
        JSON string with list of recent shares including:
        - document_title: Name of the shared document
        - recipient_email: Who it was shared with
        - share_type: Type of share (view, download, edit)
        - access_count: How many times it was accessed
        - created_at: When it was shared
    """
    actual_tenant_id = resolve_tenant_id(tenant_id)
    logger.info(f"Query recent shares: tenant={actual_tenant_id}, days={days}")

    try:
        client = get_sharing_insights_client()
        result = await client.get_recent_shares(
            tenant_id=actual_tenant_id,
            days=min(days, 365),
            limit=min(limit, 50)
        )
        return _format_response(result)
    except Exception as e:
        logger.error(f"Error querying recent shares: {e}")
        return json.dumps({"error": str(e), "shares": []})


@ai_function
async def query_shares_to_recipient(
    tenant_id: Annotated[str, Field(description="Tenant ID for data isolation")],
    email: Annotated[str, Field(description="Email address of the recipient")],
    limit: Annotated[int, Field(description="Maximum number of results")] = 20,
) -> str:
    """
    Find all documents shared with a specific person.

    Use this tool to answer questions like:
    - "What documents have I shared with john@example.com?"
    - "What can Maria access?"
    - "Show shares to the client"

    Args:
        tenant_id: Tenant identifier
        email: Email address of the recipient to search
        limit: Maximum results

    Returns:
        JSON string with shares to that recipient including:
        - document_title: Document name
        - share_type: Permission level
        - access_count: Times accessed
        - created_at: When shared
    """
    actual_tenant_id = resolve_tenant_id(tenant_id)
    logger.info(f"Query shares to recipient: tenant={actual_tenant_id}, email={email}")

    try:
        client = get_sharing_insights_client()
        result = await client.get_shares_by_recipient(
            tenant_id=actual_tenant_id,
            email=email,
            limit=min(limit, 50)
        )
        return _format_response(result)
    except Exception as e:
        logger.error(f"Error querying shares by recipient: {e}")
        return json.dumps({"error": str(e), "shares": []})


@ai_function
async def query_sharing_statistics(
    tenant_id: Annotated[str, Field(description="Tenant ID for data isolation")],
    days: Annotated[int, Field(description="Period to analyze in days")] = 30,
) -> str:
    """
    Get statistics about document sharing activity.

    Use this tool to answer questions like:
    - "How many documents have been shared?"
    - "What are the sharing statistics?"
    - "Which documents are most shared?"

    Args:
        tenant_id: Tenant identifier
        days: Period to analyze (default 30 days)

    Returns:
        JSON string with statistics including:
        - total_shares: Total number of shares
        - active_shares: Currently active shares
        - expired_shares: Expired shares
        - total_access_count: Total accesses
        - unique_recipients: Unique people shared with
        - most_shared_documents: Top shared documents
    """
    actual_tenant_id = resolve_tenant_id(tenant_id)
    logger.info(f"Query sharing statistics: tenant={actual_tenant_id}, days={days}")

    try:
        client = get_sharing_insights_client()
        result = await client.get_share_statistics(
            tenant_id=actual_tenant_id,
            days=min(days, 365)
        )
        return _format_response(result)
    except Exception as e:
        logger.error(f"Error querying sharing statistics: {e}")
        return json.dumps({"error": str(e)})


# =============================================================================
# Site Guests Tools
# =============================================================================

@ai_function
async def query_site_guests(
    tenant_id: Annotated[str, Field(description="Tenant ID for data isolation")],
    active_only: Annotated[bool, Field(description="Only show active guests")] = False,
    limit: Annotated[int, Field(description="Maximum number of results")] = 50,
) -> str:
    """
    List external guests who have access to the site portal.

    Use this tool to answer questions like:
    - "Who are my external guests?"
    - "List invited users"
    - "Show me site guests"
    - "Who has portal access?"

    Args:
        tenant_id: Tenant identifier
        active_only: If True, only return active guests
        limit: Maximum results

    Returns:
        JSON string with guest list including:
        - email: Guest's email
        - name: Guest's name
        - is_active: Whether guest is active
        - can_view/can_download/can_upload: Permissions
        - invited_at: When they were invited
        - last_access_at: Last activity
        - shares_count: Number of share collections
    """
    actual_tenant_id = resolve_tenant_id(tenant_id)
    logger.info(f"Query site guests: tenant={actual_tenant_id}, active_only={active_only}")

    try:
        client = get_sharing_insights_client()
        result = await client.get_site_guests(
            tenant_id=actual_tenant_id,
            active_only=active_only,
            limit=min(limit, 100)
        )
        return _format_response(result)
    except Exception as e:
        logger.error(f"Error querying site guests: {e}")
        return json.dumps({"error": str(e), "guests": []})


@ai_function
async def query_guest_documents(
    tenant_id: Annotated[str, Field(description="Tenant ID for data isolation")],
    email: Annotated[str, Field(description="Guest's email address")],
) -> str:
    """
    Get all documents accessible by a specific guest.

    Use this tool to answer questions like:
    - "What can guest@example.com see?"
    - "What documents does the external user have access to?"
    - "Show what Juan can access in the portal"

    Args:
        tenant_id: Tenant identifier
        email: Guest's email address

    Returns:
        JSON string with accessible documents including:
        - document_title: Document name
        - share_name: Name of the share collection
        - permission_type: view/download/upload
        - shared_at: When it was shared
        - shared_by: Who shared it
    """
    actual_tenant_id = resolve_tenant_id(tenant_id)
    logger.info(f"Query guest documents: tenant={actual_tenant_id}, email={email}")

    try:
        client = get_sharing_insights_client()
        result = await client.get_guest_documents(
            tenant_id=actual_tenant_id,
            email=email
        )
        return _format_response(result)
    except Exception as e:
        logger.error(f"Error querying guest documents: {e}")
        return json.dumps({"error": str(e), "documents": []})


@ai_function
async def query_guest_activity(
    tenant_id: Annotated[str, Field(description="Tenant ID for data isolation")],
    email: Annotated[str, Field(description="Guest's email address")],
    days: Annotated[int, Field(description="Number of days to look back")] = 30,
    limit: Annotated[int, Field(description="Maximum number of results")] = 50,
) -> str:
    """
    Get activity history for a specific guest.

    Use this tool to answer questions like:
    - "What has guest@example.com done?"
    - "Show me the activity of the external user"
    - "When did Juan last access documents?"

    Args:
        tenant_id: Tenant identifier
        email: Guest's email address
        days: Days to look back (default 30)
        limit: Maximum results

    Returns:
        JSON string with activity logs including:
        - action: What they did (login, view, download)
        - document_title: Which document (if applicable)
        - created_at: When it happened
        - success: Whether it succeeded
    """
    actual_tenant_id = resolve_tenant_id(tenant_id)
    logger.info(f"Query guest activity: tenant={actual_tenant_id}, email={email}, days={days}")

    try:
        client = get_sharing_insights_client()
        result = await client.get_guest_activity(
            tenant_id=actual_tenant_id,
            email=email,
            days=min(days, 365),
            limit=min(limit, 100)
        )
        return _format_response(result)
    except Exception as e:
        logger.error(f"Error querying guest activity: {e}")
        return json.dumps({"error": str(e), "activities": []})


@ai_function
async def query_guest_statistics(
    tenant_id: Annotated[str, Field(description="Tenant ID for data isolation")],
) -> str:
    """
    Get statistics about site guests.

    Use this tool to answer questions like:
    - "How many guests do I have?"
    - "Site guest statistics"
    - "Who are the most active external users?"

    Args:
        tenant_id: Tenant identifier

    Returns:
        JSON string with statistics including:
        - total_guests: Total number of guests
        - active_guests: Currently active guests
        - total_logins: Total login count
        - total_document_views: Total views
        - most_active_guests: Most active guests
        - guests_by_permission: Breakdown by permission type
    """
    actual_tenant_id = resolve_tenant_id(tenant_id)
    logger.info(f"Query guest statistics: tenant={actual_tenant_id}")

    try:
        client = get_sharing_insights_client()
        result = await client.get_guest_statistics(tenant_id=actual_tenant_id)
        return _format_response(result)
    except Exception as e:
        logger.error(f"Error querying guest statistics: {e}")
        return json.dumps({"error": str(e)})


# =============================================================================
# Overview Tool
# =============================================================================

@ai_function
async def query_sharing_overview(
    tenant_id: Annotated[str, Field(description="Tenant ID for data isolation")],
) -> str:
    """
    Get a high-level overview of all sharing activity.

    Use this tool to answer questions like:
    - "Give me an overview of sharing"
    - "Summary of document sharing"
    - "What's the sharing status?"

    Args:
        tenant_id: Tenant identifier

    Returns:
        JSON string with overview including:
        - total_document_shares: Total shares created
        - active_document_shares: Currently active
        - total_share_accesses: Total accesses
        - total_site_guests: Number of guests
        - shares_last_7_days: Recent shares
        - guest_invitations_last_7_days: Recent invitations
    """
    actual_tenant_id = resolve_tenant_id(tenant_id)
    logger.info(f"Query sharing overview: tenant={actual_tenant_id}")

    try:
        client = get_sharing_insights_client()
        result = await client.get_sharing_overview(tenant_id=actual_tenant_id)
        return _format_response(result)
    except Exception as e:
        logger.error(f"Error querying sharing overview: {e}")
        return json.dumps({"error": str(e)})
