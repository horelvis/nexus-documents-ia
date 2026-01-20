"""
Sharing Insights Tools for Qwen-Agent Framework

These tools provide Emma AI with the ability to query document sharing
and site guest information from the PostgreSQL database via REST API.

IMPORTANT: These tools DO NOT access the database directly. They call the
main API's /sharing-insights endpoints via HTTP.

FRAMEWORK: Qwen-Agent
Reference: https://github.com/QwenLM/Qwen-Agent

MIGRATION NOTE:
- Migrated from MS Agent Framework @ai_function pattern
- Uses class-based tools with @register_tool decorator
"""

import asyncio
import json
import logging
from typing import Union

from qwen_agent.tools.base import BaseTool, register_tool

from app.core.execution_context import resolve_tenant_id
from app.services.sharing_insights_client import get_sharing_insights_client

logger = logging.getLogger(__name__)


# =============================================================================
# Async Helper
# =============================================================================

def _run_async(coro):
    """Run an async coroutine from sync context."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=60)
    except RuntimeError:
        return asyncio.run(coro)


def _format_response(data: dict, max_items: int = 20) -> str:
    """Format API response as JSON string for agent consumption."""
    for key, value in data.items():
        if isinstance(value, list) and len(value) > max_items:
            data[key] = value[:max_items]
            data[f"{key}_truncated"] = True
            data[f"{key}_total"] = len(value)

    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


# =============================================================================
# Document Shares Tools
# =============================================================================

@register_tool('query_recent_shares')
class QueryRecentSharesTool(BaseTool):
    """Get documents that have been shared recently."""

    description = '''Get documents that have been shared recently.

Use this to answer questions like:
- "What documents have I shared this week?"
- "Show me recent document shares"
- "What files did I share in the last month?"

Returns JSON with list of recent shares including document_title, recipient_email, share_type, access_count, created_at.'''

    parameters = [
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID for data isolation',
            'required': True
        },
        {
            'name': 'days',
            'type': 'integer',
            'description': 'Number of days to look back (default 7, max 365)',
            'required': False
        },
        {
            'name': 'limit',
            'type': 'integer',
            'description': 'Maximum number of results (default 20)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params)

        tenant_id = params.get('tenant_id')
        days = params.get('days', 7)
        limit = params.get('limit', 20)

        return _run_async(self._query_recent_shares(tenant_id, days, limit))

    async def _query_recent_shares(self, tenant_id: str, days: int, limit: int) -> str:
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


@register_tool('query_shares_to_recipient')
class QuerySharesToRecipientTool(BaseTool):
    """Find all documents shared with a specific person."""

    description = '''Find all documents shared with a specific person.

Use this to answer questions like:
- "What documents have I shared with john@example.com?"
- "What can Maria access?"
- "Show shares to the client"

Returns JSON with shares to that recipient including document_title, share_type, access_count, created_at.'''

    parameters = [
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID for data isolation',
            'required': True
        },
        {
            'name': 'email',
            'type': 'string',
            'description': 'Email address of the recipient',
            'required': True
        },
        {
            'name': 'limit',
            'type': 'integer',
            'description': 'Maximum number of results (default 20)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params)

        tenant_id = params.get('tenant_id')
        email = params.get('email')
        limit = params.get('limit', 20)

        return _run_async(self._query_shares_to_recipient(tenant_id, email, limit))

    async def _query_shares_to_recipient(self, tenant_id: str, email: str, limit: int) -> str:
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


@register_tool('query_sharing_statistics')
class QuerySharingStatisticsTool(BaseTool):
    """Get statistics about document sharing activity."""

    description = '''Get statistics about document sharing activity.

Use this to answer questions like:
- "How many documents have been shared?"
- "What are the sharing statistics?"
- "Which documents are most shared?"

Returns JSON with statistics including total_shares, active_shares, expired_shares, total_access_count, unique_recipients, most_shared_documents.'''

    parameters = [
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID for data isolation',
            'required': True
        },
        {
            'name': 'days',
            'type': 'integer',
            'description': 'Period to analyze in days (default 30)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params)

        tenant_id = params.get('tenant_id')
        days = params.get('days', 30)

        return _run_async(self._query_sharing_statistics(tenant_id, days))

    async def _query_sharing_statistics(self, tenant_id: str, days: int) -> str:
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

@register_tool('query_site_guests')
class QuerySiteGuestsTool(BaseTool):
    """List external guests who have access to the site portal."""

    description = '''List external guests who have access to the site portal.

Use this to answer questions like:
- "Who are my external guests?"
- "List invited users"
- "Show me site guests"
- "Who has portal access?"

Returns JSON with guest list including email, name, is_active, permissions, invited_at, last_access_at, shares_count.'''

    parameters = [
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID for data isolation',
            'required': True
        },
        {
            'name': 'active_only',
            'type': 'boolean',
            'description': 'Only show active guests (default false)',
            'required': False
        },
        {
            'name': 'limit',
            'type': 'integer',
            'description': 'Maximum number of results (default 50)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params)

        tenant_id = params.get('tenant_id')
        active_only = params.get('active_only', False)
        limit = params.get('limit', 50)

        return _run_async(self._query_site_guests(tenant_id, active_only, limit))

    async def _query_site_guests(self, tenant_id: str, active_only: bool, limit: int) -> str:
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


@register_tool('query_guest_documents')
class QueryGuestDocumentsTool(BaseTool):
    """Get all documents accessible by a specific guest."""

    description = '''Get all documents accessible by a specific guest.

Use this to answer questions like:
- "What can guest@example.com see?"
- "What documents does the external user have access to?"
- "Show what Juan can access in the portal"

Returns JSON with accessible documents including document_title, share_name, permission_type, shared_at, shared_by.'''

    parameters = [
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID for data isolation',
            'required': True
        },
        {
            'name': 'email',
            'type': 'string',
            'description': "Guest's email address",
            'required': True
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params)

        tenant_id = params.get('tenant_id')
        email = params.get('email')

        return _run_async(self._query_guest_documents(tenant_id, email))

    async def _query_guest_documents(self, tenant_id: str, email: str) -> str:
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


@register_tool('query_guest_activity')
class QueryGuestActivityTool(BaseTool):
    """Get activity history for a specific guest."""

    description = '''Get activity history for a specific guest.

Use this to answer questions like:
- "What has guest@example.com done?"
- "Show me the activity of the external user"
- "When did Juan last access documents?"

Returns JSON with activity logs including action, document_title, created_at, success.'''

    parameters = [
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID for data isolation',
            'required': True
        },
        {
            'name': 'email',
            'type': 'string',
            'description': "Guest's email address",
            'required': True
        },
        {
            'name': 'days',
            'type': 'integer',
            'description': 'Number of days to look back (default 30)',
            'required': False
        },
        {
            'name': 'limit',
            'type': 'integer',
            'description': 'Maximum number of results (default 50)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params)

        tenant_id = params.get('tenant_id')
        email = params.get('email')
        days = params.get('days', 30)
        limit = params.get('limit', 50)

        return _run_async(self._query_guest_activity(tenant_id, email, days, limit))

    async def _query_guest_activity(self, tenant_id: str, email: str, days: int, limit: int) -> str:
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


@register_tool('query_guest_statistics')
class QueryGuestStatisticsTool(BaseTool):
    """Get statistics about site guests."""

    description = '''Get statistics about site guests.

Use this to answer questions like:
- "How many guests do I have?"
- "Site guest statistics"
- "Who are the most active external users?"

Returns JSON with statistics including total_guests, active_guests, total_logins, total_document_views, most_active_guests, guests_by_permission.'''

    parameters = [
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID for data isolation',
            'required': True
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params)

        tenant_id = params.get('tenant_id')

        return _run_async(self._query_guest_statistics(tenant_id))

    async def _query_guest_statistics(self, tenant_id: str) -> str:
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

@register_tool('query_sharing_overview')
class QuerySharingOverviewTool(BaseTool):
    """Get a high-level overview of all sharing activity."""

    description = '''Get a high-level overview of all sharing activity.

Use this to answer questions like:
- "Give me an overview of sharing"
- "Summary of document sharing"
- "What's the sharing status?"

Returns JSON with overview including total_document_shares, active_document_shares, total_share_accesses, total_site_guests, shares_last_7_days, guest_invitations_last_7_days.'''

    parameters = [
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID for data isolation',
            'required': True
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params)

        tenant_id = params.get('tenant_id')

        return _run_async(self._query_sharing_overview(tenant_id))

    async def _query_sharing_overview(self, tenant_id: str) -> str:
        actual_tenant_id = resolve_tenant_id(tenant_id)
        logger.info(f"Query sharing overview: tenant={actual_tenant_id}")

        try:
            client = get_sharing_insights_client()
            result = await client.get_sharing_overview(tenant_id=actual_tenant_id)
            return _format_response(result)
        except Exception as e:
            logger.error(f"Error querying sharing overview: {e}")
            return json.dumps({"error": str(e)})


# =============================================================================
# Tool Registration Exports
# =============================================================================

SHARING_INSIGHTS_TOOLS = [
    QueryRecentSharesTool,
    QuerySharesToRecipientTool,
    QuerySharingStatisticsTool,
    QuerySiteGuestsTool,
    QueryGuestDocumentsTool,
    QueryGuestActivityTool,
    QueryGuestStatisticsTool,
    QuerySharingOverviewTool,
]

SHARING_INSIGHTS_TOOL_NAMES = [
    'query_recent_shares',
    'query_shares_to_recipient',
    'query_sharing_statistics',
    'query_site_guests',
    'query_guest_documents',
    'query_guest_activity',
    'query_guest_statistics',
    'query_sharing_overview',
]


def get_sharing_insights_tools() -> list:
    """
    Get list of sharing insights tool names for use in Qwen-Agent Assistant's function_list.
    """
    return SHARING_INSIGHTS_TOOL_NAMES
