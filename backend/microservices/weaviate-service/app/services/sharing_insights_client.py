"""
Sharing Insights HTTP Client

Client for calling the main API's sharing insights endpoints.
Used by @ai_function tools to retrieve sharing data for Emma AI.

All calls use the internal X-API-Key authentication and pass
tenant_id via X-Tenant-ID header.
"""

import logging
from typing import Optional, Dict, Any
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Default timeout for HTTP requests
DEFAULT_TIMEOUT = 30.0


class SharingInsightsClient:
    """
    HTTP client for sharing insights API.

    Provides methods matching the @ai_function tools that Emma uses.
    All methods are async and return parsed JSON responses.
    """

    def __init__(self):
        self.base_url = f"{settings.api_url}/api/v1/sharing-insights"
        self.api_key = settings.MICROSERVICES_API_KEY

    def _get_headers(self, tenant_id: str) -> Dict[str, str]:
        """Get headers for internal API calls."""
        return {
            "X-API-Key": self.api_key,
            "X-Tenant-ID": tenant_id,
            "Content-Type": "application/json"
        }

    async def _make_request(
        self,
        endpoint: str,
        tenant_id: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = DEFAULT_TIMEOUT
    ) -> Dict[str, Any]:
        """
        Make an HTTP GET request to the sharing insights API.

        Args:
            endpoint: API endpoint path (without base URL)
            tenant_id: Tenant ID for data isolation
            params: Query parameters
            timeout: Request timeout in seconds

        Returns:
            Parsed JSON response

        Raises:
            Exception: If request fails
        """
        url = f"{self.base_url}{endpoint}/internal"
        headers = self._get_headers(tenant_id)

        logger.debug(f"Sharing insights request: {url} tenant={tenant_id}")

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
                raise Exception(f"API error: {e.response.status_code} - {e.response.text}")
            except httpx.RequestError as e:
                logger.error(f"Request error: {e}")
                raise Exception(f"Request failed: {str(e)}")

    # =========================================================================
    # Document Shares Methods
    # =========================================================================

    async def get_recent_shares(
        self,
        tenant_id: str,
        days: int = 7,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get documents shared within the last N days.

        Args:
            tenant_id: Tenant identifier
            days: Number of days to look back
            limit: Maximum results

        Returns:
            Dict with shares list and metadata
        """
        return await self._make_request(
            endpoint="/recent-shares",
            tenant_id=tenant_id,
            params={"days": days, "limit": limit}
        )

    async def get_shares_by_recipient(
        self,
        tenant_id: str,
        email: str,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get shares sent to a specific email.

        Args:
            tenant_id: Tenant identifier
            email: Recipient email to filter
            limit: Maximum results

        Returns:
            Dict with shares for that recipient
        """
        return await self._make_request(
            endpoint="/shares-by-recipient",
            tenant_id=tenant_id,
            params={"email": email, "limit": limit}
        )

    async def get_share_statistics(
        self,
        tenant_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get aggregated sharing statistics.

        Args:
            tenant_id: Tenant identifier
            days: Period to analyze

        Returns:
            Dict with aggregated stats
        """
        return await self._make_request(
            endpoint="/share-statistics",
            tenant_id=tenant_id,
            params={"days": days}
        )

    # =========================================================================
    # Site Guests Methods
    # =========================================================================

    async def get_site_guests(
        self,
        tenant_id: str,
        active_only: bool = False,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get site guests list.

        Args:
            tenant_id: Tenant identifier
            active_only: Only return active guests
            limit: Maximum results

        Returns:
            Dict with guests list
        """
        return await self._make_request(
            endpoint="/site-guests",
            tenant_id=tenant_id,
            params={"active_only": active_only, "limit": limit}
        )

    async def get_guest_documents(
        self,
        tenant_id: str,
        email: str
    ) -> Dict[str, Any]:
        """
        Get documents accessible by a guest.

        Args:
            tenant_id: Tenant identifier
            email: Guest email

        Returns:
            Dict with accessible documents
        """
        return await self._make_request(
            endpoint="/guest-documents",
            tenant_id=tenant_id,
            params={"email": email}
        )

    async def get_guest_activity(
        self,
        tenant_id: str,
        email: str,
        days: int = 30,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get activity logs for a guest.

        Args:
            tenant_id: Tenant identifier
            email: Guest email
            days: Days to look back
            limit: Maximum results

        Returns:
            Dict with activity logs
        """
        return await self._make_request(
            endpoint="/guest-activity",
            tenant_id=tenant_id,
            params={"email": email, "days": days, "limit": limit}
        )

    async def get_guest_statistics(
        self,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Get aggregated guest statistics.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dict with guest stats
        """
        return await self._make_request(
            endpoint="/guest-statistics",
            tenant_id=tenant_id
        )

    # =========================================================================
    # Overview Methods
    # =========================================================================

    async def get_sharing_overview(
        self,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Get high-level sharing overview.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dict with overview stats
        """
        return await self._make_request(
            endpoint="/overview",
            tenant_id=tenant_id
        )


# Singleton instance
_client: Optional[SharingInsightsClient] = None


def get_sharing_insights_client() -> SharingInsightsClient:
    """Get or create the sharing insights client singleton."""
    global _client
    if _client is None:
        _client = SharingInsightsClient()
    return _client
