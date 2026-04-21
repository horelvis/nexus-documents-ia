"""
Service for performing health checks on connectors.

Supports different connector types with type-specific health checks.
"""

import base64
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class HealthCheckResult(BaseModel):
    """Result of connector health check."""

    status: str  # "healthy", "degraded", "unhealthy"
    message: str
    response_time_ms: float
    details: Dict[str, Any] = {}


class ConnectorHealthService:
    """Service for checking connector health."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    async def check_health(
        self,
        connector_type: str,
        config: Dict[str, Any]
    ) -> HealthCheckResult:
        """
        Perform health check based on connector type.

        Args:
            connector_type: Type of connector (alfresco, google_drive, etc.)
            config: Connector configuration

        Returns:
            HealthCheckResult with status and details
        """
        start_time = time.time()

        try:
            if connector_type == "alfresco":
                return await self._check_alfresco(config, start_time)
            elif connector_type in ("google_drive", "google_workspace"):
                return await self._check_google(config, start_time)
            elif connector_type in ("sharepoint", "onedrive"):
                return await self._check_microsoft(config, start_time)
            elif connector_type == "s3":
                return await self._check_s3(config, start_time)
            elif connector_type == "azure_blob":
                return await self._check_azure_blob(config, start_time)
            else:
                return HealthCheckResult(
                    status="unknown",
                    message=f"Health check not implemented for connector type: {connector_type}",
                    response_time_ms=(time.time() - start_time) * 1000,
                    details={"connector_type": connector_type}
                )
        except Exception as e:
            logger.error(f"Health check failed for {connector_type}: {e}")
            return HealthCheckResult(
                status="unhealthy",
                message=f"Health check failed: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"error": str(e), "error_type": type(e).__name__}
            )

    async def _check_alfresco(
        self,
        config: Dict[str, Any],
        start_time: float
    ) -> HealthCheckResult:
        """
        Check Alfresco connector health.

        Tests:
        1. Authentication (GET /people/-me-)
        2. Discovery API (optional)
        3. Search API (AFTS query)
        4. Sites listing
        """
        url = config.get("url", "").rstrip("/")
        username = config.get("username", "")
        password = config.get("password", "")
        api_path = config.get("api_path", "/alfresco/api/-default-/public/alfresco/versions/1")
        search_api_path = config.get("search_api_path", "/alfresco/api/-default-/public/search/versions/1")
        default_site = config.get("default_site_id")

        if not url or not username or not password:
            return HealthCheckResult(
                status="unhealthy",
                message="Missing required configuration: url, username, or password",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"missing_fields": [k for k in ["url", "username", "password"] if not config.get(k)]}
            )

        # Basic auth header
        auth_str = f"{username}:{password}"
        auth_bytes = base64.b64encode(auth_str.encode()).decode()
        headers = {
            "Authorization": f"Basic {auth_bytes}",
            "Accept": "application/json"
        }

        details: Dict[str, Any] = {"url": url}
        issues: list = []
        authenticated_user = None
        search_working = False
        sites_count = 0

        try:
            async with httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=float(self.timeout),
                    write=30.0,
                    pool=5.0
                )
            ) as client:
                # Test 1: Authentication - GET /people/-me-
                try:
                    response = await client.get(f"{url}{api_path}/people/-me-")
                    if response.status_code == 401:
                        return HealthCheckResult(
                            status="unhealthy",
                            message="Authentication failed: Invalid credentials",
                            response_time_ms=(time.time() - start_time) * 1000,
                            details={"status_code": 401}
                        )
                    response.raise_for_status()
                    user_data = response.json().get("entry", {})
                    authenticated_user = user_data.get("displayName") or user_data.get("id")
                    details["authenticated_user"] = authenticated_user
                    details["user_id"] = user_data.get("id")
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 401:
                        return HealthCheckResult(
                            status="unhealthy",
                            message="Authentication failed: Invalid credentials",
                            response_time_ms=(time.time() - start_time) * 1000,
                            details={"status_code": 401}
                        )
                    issues.append(f"User API error: {e.response.status_code}")

                # Test 2: Discovery API (optional, may not be available)
                try:
                    response = await client.get(f"{url}/alfresco/api/discovery")
                    if response.status_code == 200:
                        discovery = response.json().get("entry", {}).get("repository", {})
                        details["api_version"] = discovery.get("version", {}).get("display")
                        details["edition"] = discovery.get("edition")
                        details["repository_id"] = discovery.get("id")
                except Exception:
                    pass  # Discovery is optional

                # Test 3: Search API
                try:
                    search_body = {
                        "query": {"query": 'TYPE:"cm:folder"', "language": "afts"},
                        "paging": {"maxItems": 1}
                    }
                    response = await client.post(
                        f"{url}{search_api_path}/search",
                        json=search_body
                    )
                    response.raise_for_status()
                    search_data = response.json()
                    search_working = True
                    details["search_api"] = "working"
                    details["total_folders"] = search_data.get("list", {}).get("pagination", {}).get("totalItems", 0)
                except httpx.HTTPStatusError as e:
                    issues.append(f"Search API error: {e.response.status_code}")
                    details["search_api"] = f"error: {e.response.status_code}"

                # Test 4: List sites
                try:
                    response = await client.get(
                        f"{url}{api_path}/sites",
                        params={"maxItems": 50}
                    )
                    response.raise_for_status()
                    sites = response.json().get("list", {}).get("entries", [])
                    sites_count = len(sites)
                    details["sites_count"] = sites_count
                    details["sites"] = [s.get("entry", {}).get("id") for s in sites[:5]]

                    # Check default site if configured
                    if default_site:
                        site_exists = any(
                            s.get("entry", {}).get("id") == default_site
                            for s in sites
                        )
                        details["default_site_accessible"] = site_exists
                        if not site_exists:
                            issues.append(f"Default site '{default_site}' not found")
                except httpx.HTTPStatusError as e:
                    issues.append(f"Sites API error: {e.response.status_code}")

        except httpx.ConnectError:
            return HealthCheckResult(
                status="unhealthy",
                message=f"Connection failed: Unable to reach {url}",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"url": url, "error": "connection_failed"}
            )
        except httpx.TimeoutException:
            return HealthCheckResult(
                status="unhealthy",
                message=f"Connection timeout after {self.timeout}s",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"url": url, "timeout": self.timeout}
            )

        # Determine status
        response_time = (time.time() - start_time) * 1000

        if not authenticated_user:
            status = "unhealthy"
            message = "Failed to authenticate with Alfresco"
        elif not search_working:
            status = "degraded"
            message = f"Connected but Search API not working. {'; '.join(issues)}"
        elif issues:
            status = "degraded"
            message = f"Connected with issues: {'; '.join(issues)}"
        else:
            status = "healthy"
            message = f"Connected to Alfresco as {authenticated_user}"

        # Include response_time_ms in details for API response
        details["response_time_ms"] = response_time

        return HealthCheckResult(
            status=status,
            message=message,
            response_time_ms=response_time,
            details=details
        )

    async def _check_google(
        self,
        config: Dict[str, Any],
        start_time: float
    ) -> HealthCheckResult:
        """Check Google Drive/Workspace connector."""
        # For service account, we need to test OAuth flow
        client_id = config.get("client_id")
        service_account_json = config.get("service_account_json")

        if not client_id:
            return HealthCheckResult(
                status="unhealthy",
                message="Missing client_id configuration",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"missing_fields": ["client_id"]}
            )

        # If service account is configured, we could test it
        if service_account_json:
            return HealthCheckResult(
                status="healthy",
                message="Service account configured (full test requires OAuth)",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"auth_type": "service_account", "client_id": client_id[:20] + "..."}
            )

        return HealthCheckResult(
            status="healthy",
            message="OAuth configuration valid (requires user authorization to test)",
            response_time_ms=(time.time() - start_time) * 1000,
            details={"auth_type": "oauth", "client_id": client_id[:20] + "..."}
        )

    async def _check_microsoft(
        self,
        config: Dict[str, Any],
        start_time: float
    ) -> HealthCheckResult:
        """Check SharePoint/OneDrive connector."""
        # Note: "tenant_id" here refers to the Azure AD directory identifier
        # used to construct the Microsoft OAuth URL (third-party OAuth protocol,
        # not our application multi-tenancy model). Preserved intentionally.
        ms_tenant = config.get("tenant_id")  # noqa: tenant_removal
        client_id = config.get("client_id")
        client_secret = config.get("client_secret")

        if not ms_tenant or not client_id:
            return HealthCheckResult(
                status="unhealthy",
                message="Missing required configuration",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"missing_fields": [k for k in ["tenant_id", "client_id"] if not config.get(k)]}  # noqa: tenant_removal
            )

        # If client_secret is configured, we could test app-only auth
        if client_secret:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    # Test token endpoint reachability
                    response = await client.post(
                        f"https://login.microsoftonline.com/{ms_tenant}/oauth2/v2.0/token",
                        data={
                            "grant_type": "client_credentials",
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "scope": "https://graph.microsoft.com/.default"
                        }
                    )

                    if response.status_code == 200:
                        return HealthCheckResult(
                            status="healthy",
                            message="Successfully authenticated with Microsoft Graph",
                            response_time_ms=(time.time() - start_time) * 1000,
                            details={"auth_type": "client_credentials", "tenant_id": ms_tenant}  # noqa: tenant_removal
                        )
                    else:
                        return HealthCheckResult(
                            status="unhealthy",
                            message=f"Authentication failed: {response.status_code}",
                            response_time_ms=(time.time() - start_time) * 1000,
                            details={"status_code": response.status_code}
                        )
            except Exception as e:
                return HealthCheckResult(
                    status="unhealthy",
                    message=f"Connection error: {str(e)}",
                    response_time_ms=(time.time() - start_time) * 1000,
                    details={"error": str(e)}
                )

        return HealthCheckResult(
            status="healthy",
            message="OAuth configuration valid (requires user authorization to test)",
            response_time_ms=(time.time() - start_time) * 1000,
            details={"auth_type": "oauth", "tenant_id": ms_tenant}  # noqa: tenant_removal
        )

    async def _check_s3(
        self,
        config: Dict[str, Any],
        start_time: float
    ) -> HealthCheckResult:
        """Check AWS S3 connector."""
        bucket_name = config.get("bucket_name")
        region = config.get("region", "us-east-1")
        access_key_id = config.get("access_key_id")
        secret_access_key = config.get("secret_access_key")

        if not bucket_name:
            return HealthCheckResult(
                status="unhealthy",
                message="Missing bucket_name configuration",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"missing_fields": ["bucket_name"]}
            )

        if access_key_id and secret_access_key:
            # TODO: Test actual S3 connection with boto3
            return HealthCheckResult(
                status="healthy",
                message=f"S3 credentials configured for bucket: {bucket_name}",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"bucket": bucket_name, "region": region}
            )

        return HealthCheckResult(
            status="degraded",
            message="S3 bucket configured but no credentials provided",
            response_time_ms=(time.time() - start_time) * 1000,
            details={"bucket": bucket_name, "region": region}
        )

    async def _check_azure_blob(
        self,
        config: Dict[str, Any],
        start_time: float
    ) -> HealthCheckResult:
        """Check Azure Blob Storage connector."""
        storage_account = config.get("storage_account")
        container_name = config.get("container_name")
        connection_string = config.get("connection_string")

        if not storage_account or not container_name:
            return HealthCheckResult(
                status="unhealthy",
                message="Missing required configuration",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"missing_fields": [k for k in ["storage_account", "container_name"] if not config.get(k)]}
            )

        if connection_string:
            # TODO: Test actual Azure connection
            return HealthCheckResult(
                status="healthy",
                message=f"Azure Blob configured for container: {container_name}",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"storage_account": storage_account, "container": container_name}
            )

        return HealthCheckResult(
            status="degraded",
            message="Azure Blob configured but no connection string provided",
            response_time_ms=(time.time() - start_time) * 1000,
            details={"storage_account": storage_account, "container": container_name}
        )


# Singleton instance
_health_service: Optional[ConnectorHealthService] = None


def get_connector_health_service() -> ConnectorHealthService:
    """Get or create health service instance."""
    global _health_service
    if _health_service is None:
        _health_service = ConnectorHealthService()
    return _health_service
