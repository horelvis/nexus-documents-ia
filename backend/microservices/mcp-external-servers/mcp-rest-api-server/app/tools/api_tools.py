"""
MCP REST API Tools.

Provides tools for calling external REST APIs.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import get_endpoints, APIEndpointConfig

logger = logging.getLogger(__name__)


async def _get_client(endpoint: APIEndpointConfig) -> httpx.AsyncClient:
    """Create an HTTP client with appropriate authentication."""
    headers = {}

    if endpoint.auth_type == "api_key" and endpoint.api_key:
        headers[endpoint.api_key_header] = endpoint.api_key

    elif endpoint.auth_type == "bearer" and endpoint.bearer_token:
        headers["Authorization"] = f"Bearer {endpoint.bearer_token}"

    elif endpoint.auth_type == "basic" and endpoint.username and endpoint.password:
        import base64
        creds = base64.b64encode(
            f"{endpoint.username}:{endpoint.password}".encode()
        ).decode()
        headers["Authorization"] = f"Basic {creds}"

    return httpx.AsyncClient(
        base_url=endpoint.base_url,
        headers=headers,
        timeout=endpoint.timeout_seconds,
    )


async def rest_get(
    endpoint_name: str,
    path: str,
    tenant_id: str,
    params: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Perform a GET request to an external REST API.

    Use this tool when you need to retrieve data from an external API.
    The endpoint must be pre-configured in the server.

    Args:
        endpoint_name: Name of the configured API endpoint
        path: API path to call (e.g., "/users/123")
        tenant_id: Tenant identifier for access control
        params: Optional query parameters
        headers: Optional additional headers

    Returns:
        API response with:
        - status_code: HTTP status code
        - data: Response body (JSON parsed if possible)
        - headers: Response headers
    """
    endpoints = get_endpoints()

    if endpoint_name not in endpoints:
        return {
            "success": False,
            "error": f"Unknown endpoint: {endpoint_name}",
            "available_endpoints": list(endpoints.keys()),
        }

    endpoint = endpoints[endpoint_name]

    if not endpoint.is_accessible_by_tenant(tenant_id):
        return {
            "success": False,
            "error": f"Access denied to endpoint {endpoint_name} for tenant {tenant_id}",
        }

    try:
        async with await _get_client(endpoint) as client:
            response = await client.get(
                path,
                params=params,
                headers=headers,
            )

            try:
                data = response.json()
            except Exception:
                data = response.text

            return {
                "success": True,
                "status_code": response.status_code,
                "data": data,
                "headers": dict(response.headers),
            }

    except httpx.TimeoutException:
        return {
            "success": False,
            "error": "Request timed out",
            "endpoint": endpoint_name,
            "path": path,
        }
    except Exception as e:
        logger.error(f"REST GET failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "endpoint": endpoint_name,
            "path": path,
        }


async def rest_post(
    endpoint_name: str,
    path: str,
    tenant_id: str,
    body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Perform a POST request to an external REST API.

    Use this tool when you need to send data to an external API.
    The endpoint must be pre-configured in the server.

    Args:
        endpoint_name: Name of the configured API endpoint
        path: API path to call (e.g., "/users")
        tenant_id: Tenant identifier for access control
        body: Request body (will be sent as JSON)
        params: Optional query parameters
        headers: Optional additional headers

    Returns:
        API response with:
        - status_code: HTTP status code
        - data: Response body (JSON parsed if possible)
        - headers: Response headers
    """
    endpoints = get_endpoints()

    if endpoint_name not in endpoints:
        return {
            "success": False,
            "error": f"Unknown endpoint: {endpoint_name}",
        }

    endpoint = endpoints[endpoint_name]

    if not endpoint.is_accessible_by_tenant(tenant_id):
        return {
            "success": False,
            "error": f"Access denied to endpoint {endpoint_name}",
        }

    try:
        async with await _get_client(endpoint) as client:
            response = await client.post(
                path,
                json=body,
                params=params,
                headers=headers,
            )

            try:
                data = response.json()
            except Exception:
                data = response.text

            return {
                "success": True,
                "status_code": response.status_code,
                "data": data,
                "headers": dict(response.headers),
            }

    except httpx.TimeoutException:
        return {
            "success": False,
            "error": "Request timed out",
        }
    except Exception as e:
        logger.error(f"REST POST failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


async def rest_query(
    endpoint_name: str,
    path: str,
    tenant_id: str,
    params: Optional[Dict[str, str]] = None,
    page: int = 1,
    page_size: int = 20,
    pagination_style: str = "offset",
) -> Dict[str, Any]:
    """
    Query an external REST API with pagination support.

    Use this tool when you need to retrieve paginated data from an API.
    Supports offset-based and cursor-based pagination.

    Args:
        endpoint_name: Name of the configured API endpoint
        path: API path to query
        tenant_id: Tenant identifier
        params: Additional query parameters
        page: Page number (for offset pagination)
        page_size: Number of items per page
        pagination_style: "offset" or "cursor"

    Returns:
        Query result with:
        - data: Response data
        - page: Current page
        - page_size: Items per page
        - has_more: Whether more pages exist
    """
    endpoints = get_endpoints()

    if endpoint_name not in endpoints:
        return {
            "success": False,
            "error": f"Unknown endpoint: {endpoint_name}",
        }

    endpoint = endpoints[endpoint_name]

    if not endpoint.is_accessible_by_tenant(tenant_id):
        return {
            "success": False,
            "error": f"Access denied",
        }

    try:
        # Build pagination params
        query_params = dict(params or {})

        if pagination_style == "offset":
            query_params["page"] = str(page)
            query_params["page_size"] = str(page_size)
        else:
            query_params["limit"] = str(page_size)

        async with await _get_client(endpoint) as client:
            response = await client.get(path, params=query_params)

            try:
                data = response.json()
            except Exception:
                data = response.text

            # Try to detect if there are more pages
            has_more = False
            if isinstance(data, list):
                has_more = len(data) >= page_size
            elif isinstance(data, dict):
                has_more = data.get("has_more", data.get("hasMore", len(data.get("items", data.get("data", []))) >= page_size))

            return {
                "success": True,
                "data": data,
                "page": page,
                "page_size": page_size,
                "has_more": has_more,
                "status_code": response.status_code,
            }

    except Exception as e:
        logger.error(f"REST query failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


async def list_endpoints(tenant_id: str) -> Dict[str, Any]:
    """
    List available API endpoints for a tenant.

    Use this tool to discover what external APIs are available.

    Args:
        tenant_id: Tenant identifier

    Returns:
        List of available endpoints with:
        - name: Endpoint name
        - description: What the endpoint provides
        - base_url: The API base URL
    """
    endpoints = get_endpoints()

    available = []
    for name, endpoint in endpoints.items():
        if endpoint.is_accessible_by_tenant(tenant_id):
            available.append({
                "name": name,
                "description": endpoint.description,
                "base_url": endpoint.base_url,
            })

    return {
        "success": True,
        "endpoints": available,
        "count": len(available),
    }
