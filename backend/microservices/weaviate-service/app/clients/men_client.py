"""
MEN Service Client - Integration with Mixture of Experts Network.

Provides a client for the weaviate-service to communicate with
the MEN service for intelligent query routing and expert responses.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)


class MENClient:
    """
    Client for MEN Service API.

    Provides methods to:
    - Query the MEN pipeline for intelligent responses
    - Classify queries without generating responses
    - Manage conversation sessions

    Example usage:
        client = MENClient()
        result = await client.query(
            query="¿Cuántos contratos tiene ACME?",
            tenant_id="tenant-123",
            session_id="chat-456"
        )
        print(result["response"])
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 60.0
    ):
        """
        Initialize MEN client.

        Args:
            base_url: MEN service URL (default from settings)
            api_key: API key for authentication (default from settings)
            timeout: Request timeout in seconds
        """
        self.base_url = (
            base_url or
            getattr(settings, 'MEN_SERVICE_URL', None) or
            "http://men-service:8010"
        ).rstrip("/")
        self.api_key = api_key or settings.MICROSERVICES_API_KEY
        self.timeout = timeout

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def query(
        self,
        query: str,
        tenant_id: str,
        session_id: str = "default",
        tenant_schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Query the MEN service for an intelligent response.

        Pipeline:
        1. Orchestrator classifies domain
        2. Expert provides technical data (if available)
        3. LLM Modeler synthesizes response with memory

        Args:
            query: User's query text
            tenant_id: Tenant identifier
            session_id: Session for conversational memory
            tenant_schema: Tenant metadata (document_types, clients, etc.)

        Returns:
            Dict with: response, domain, expert_used, has_expert_data, session_id
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/men/query",
                    headers=self._get_headers(),
                    json={
                        "query": query,
                        "tenant_id": tenant_id,
                        "session_id": session_id,
                        "tenant_schema": tenant_schema
                    }
                )
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"MEN query failed with status {e.response.status_code}: {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"MEN query request failed: {e}")
            raise

    async def decide(self, query: str) -> Dict[str, Any]:
        """
        Classify a query without generating a response.

        Useful for routing decisions and pre-filtering.

        Args:
            query: Query to classify

        Returns:
            Dict with: domain, confidence, requires_expert
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/men/decide",
                    headers=self._get_headers(),
                    json={"query": query}
                )
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"MEN decide failed: {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"MEN decide request failed: {e}")
            raise

    async def get_session_history(
        self,
        session_id: str,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Get conversation history for a session.

        Args:
            session_id: Session identifier
            tenant_id: Tenant identifier

        Returns:
            Dict with: session_id, tenant_id, history, message_count
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/men/sessions/{session_id}/history",
                    headers=self._get_headers(),
                    params={"tenant_id": tenant_id}
                )
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"Get session history failed: {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Get session history request failed: {e}")
            raise

    async def clear_session(
        self,
        session_id: str,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Clear conversation history for a session.

        Args:
            session_id: Session identifier
            tenant_id: Tenant identifier

        Returns:
            Dict with: message, session_id, cleared
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/men/sessions/{session_id}/clear",
                    headers=self._get_headers(),
                    params={"tenant_id": tenant_id}
                )
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"Clear session failed: {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Clear session request failed: {e}")
            raise

    async def list_tenant_experts(self, tenant_id: str) -> Dict[str, Any]:
        """
        List experts available for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dict with: tenant_id, experts, generic_experts
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/men/tenants/{tenant_id}/experts",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"List experts failed: {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"List experts request failed: {e}")
            raise

    async def health_check(self) -> Dict[str, Any]:
        """
        Check MEN service health.

        Returns:
            Dict with: status, service, version, loaded, etc.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/men/health",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.warning(f"MEN health check failed: {e.response.status_code}")
            return {"status": "unhealthy", "error": str(e)}
        except httpx.RequestError as e:
            logger.warning(f"MEN health check request failed: {e}")
            return {"status": "unreachable", "error": str(e)}

    async def is_available(self) -> bool:
        """Check if MEN service is available and healthy."""
        try:
            health = await self.health_check()
            return health.get("status") in ["healthy", "starting"]
        except Exception:
            return False


# Singleton instance
_men_client: Optional[MENClient] = None


def get_men_client() -> MENClient:
    """Get or create the global MEN client instance."""
    global _men_client
    if _men_client is None:
        _men_client = MENClient()
    return _men_client
