"""
Workflow Service - Client for Camunda Workflow Service

Provides high-level workflow operations by communicating with
the camunda-service microservice.
"""

import logging
from typing import Optional, List, Dict, Any
import httpx
from functools import lru_cache

from app.core.config import settings


logger = logging.getLogger(__name__)


class WorkflowServiceError(Exception):
    """Base exception for workflow service errors."""
    def __init__(self, message: str, status_code: int = 500, details: Optional[str] = None):
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class WorkflowService:
    """
    Client service for interacting with Camunda workflows.

    Communicates with the camunda-service microservice which handles
    the actual Camunda 7 REST API calls.
    """

    def __init__(self):
        self.settings = settings
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def base_url(self) -> str:
        """Get camunda service URL."""
        return getattr(self.settings, 'CAMUNDA_SERVICE_URL', 'http://camunda-service:8001')

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(30.0, connect=10.0),
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": getattr(self.settings, 'MICROSERVICES_API_KEY', '')
                }
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        endpoint: str,
        tenant_id: str,
        json: Optional[Dict] = None,
        params: Optional[Dict] = None,
        files: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to camunda service."""
        client = await self._get_client()

        # Add tenant_id to params
        if params is None:
            params = {}
        params["tenant_id"] = tenant_id

        try:
            if files:
                response = await client.request(
                    method=method,
                    url=endpoint,
                    params=params,
                    files=files,
                    data=data
                )
            else:
                response = await client.request(
                    method=method,
                    url=endpoint,
                    params=params,
                    json=json
                )

            if response.status_code >= 400:
                error_detail = response.text
                logger.error(f"Camunda service error: {response.status_code} - {error_detail}")
                raise WorkflowServiceError(
                    f"Workflow service error: {response.status_code}",
                    status_code=response.status_code,
                    details=error_detail
                )

            return response.json() if response.content else {}

        except httpx.TimeoutException as e:
            logger.error(f"Timeout calling camunda service: {e}")
            raise WorkflowServiceError("Workflow service timeout", status_code=504)
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling camunda service: {e}")
            raise WorkflowServiceError(f"Workflow service error: {e}", status_code=502)

    # ============ Deployment Operations ============

    async def deploy_process(
        self,
        tenant_id: str,
        name: str,
        bpmn_xml: str,
        source: Optional[str] = None
    ) -> Dict[str, Any]:
        """Deploy a BPMN process definition."""
        return await self._request(
            "POST",
            "/api/v1/deployments/xml",
            tenant_id=tenant_id,
            json={
                "name": name,
                "bpmn_xml": bpmn_xml,
                "source": source
            }
        )

    async def get_deployments(
        self,
        tenant_id: str,
        name: Optional[str] = None,
        first_result: int = 0,
        max_results: int = 20
    ) -> Dict[str, Any]:
        """Get list of deployments."""
        params = {
            "first_result": first_result,
            "max_results": max_results
        }
        if name:
            params["name"] = name

        return await self._request(
            "GET",
            "/api/v1/deployments",
            tenant_id=tenant_id,
            params=params
        )

    async def delete_deployment(
        self,
        tenant_id: str,
        deployment_id: str,
        cascade: bool = True
    ) -> Dict[str, Any]:
        """Delete a deployment."""
        return await self._request(
            "DELETE",
            f"/api/v1/deployments/{deployment_id}",
            tenant_id=tenant_id,
            params={"cascade": str(cascade).lower()}
        )

    # ============ Process Definition Operations ============

    async def get_process_definitions(
        self,
        tenant_id: str,
        key: Optional[str] = None,
        latest_version: bool = True
    ) -> Dict[str, Any]:
        """Get process definitions."""
        params = {"latest_version": str(latest_version).lower()}
        if key:
            params["key"] = key

        return await self._request(
            "GET",
            "/api/v1/processes/definitions",
            tenant_id=tenant_id,
            params=params
        )

    async def get_process_definition_xml(
        self,
        tenant_id: str,
        key: str
    ) -> Dict[str, Any]:
        """Get BPMN XML for a process definition."""
        return await self._request(
            "GET",
            f"/api/v1/processes/definitions/{key}/xml",
            tenant_id=tenant_id
        )

    # ============ Process Instance Operations ============

    async def start_process(
        self,
        tenant_id: str,
        process_key: str,
        variables: Optional[Dict[str, Any]] = None,
        business_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Start a new process instance."""
        payload = {
            "process_key": process_key,
            "variables": variables or {}
        }
        if business_key:
            payload["business_key"] = business_key

        return await self._request(
            "POST",
            "/api/v1/processes/start",
            tenant_id=tenant_id,
            json=payload
        )

    async def get_process_instances(
        self,
        tenant_id: str,
        process_key: Optional[str] = None,
        business_key: Optional[str] = None,
        active: Optional[bool] = None,
        first_result: int = 0,
        max_results: int = 20
    ) -> Dict[str, Any]:
        """Get list of process instances."""
        params = {
            "first_result": first_result,
            "max_results": max_results
        }
        if process_key:
            params["process_key"] = process_key
        if business_key:
            params["business_key"] = business_key
        if active is not None:
            params["active"] = str(active).lower()

        return await self._request(
            "GET",
            "/api/v1/processes/instances",
            tenant_id=tenant_id,
            params=params
        )

    async def get_process_instance(
        self,
        tenant_id: str,
        instance_id: str
    ) -> Dict[str, Any]:
        """Get a specific process instance."""
        return await self._request(
            "GET",
            f"/api/v1/processes/instances/{instance_id}",
            tenant_id=tenant_id
        )

    async def get_process_instance_variables(
        self,
        tenant_id: str,
        instance_id: str
    ) -> Dict[str, Any]:
        """Get variables for a process instance."""
        return await self._request(
            "GET",
            f"/api/v1/processes/instances/{instance_id}/variables",
            tenant_id=tenant_id
        )

    async def cancel_process_instance(
        self,
        tenant_id: str,
        instance_id: str
    ) -> Dict[str, Any]:
        """Cancel a process instance."""
        return await self._request(
            "DELETE",
            f"/api/v1/processes/instances/{instance_id}",
            tenant_id=tenant_id
        )

    # ============ Task Operations ============

    async def get_tasks(
        self,
        tenant_id: str,
        assignee: Optional[str] = None,
        candidate_user: Optional[str] = None,
        process_instance_id: Optional[str] = None,
        process_definition_key: Optional[str] = None,
        unassigned: Optional[bool] = None,
        first_result: int = 0,
        max_results: int = 20
    ) -> Dict[str, Any]:
        """Get list of user tasks."""
        params = {
            "first_result": first_result,
            "max_results": max_results
        }
        if assignee:
            params["assignee"] = assignee
        if candidate_user:
            params["candidate_user"] = candidate_user
        if process_instance_id:
            params["process_instance_id"] = process_instance_id
        if process_definition_key:
            params["process_definition_key"] = process_definition_key
        if unassigned is not None:
            params["unassigned"] = str(unassigned).lower()

        return await self._request(
            "GET",
            "/api/v1/tasks",
            tenant_id=tenant_id,
            params=params
        )

    async def get_task(
        self,
        tenant_id: str,
        task_id: str
    ) -> Dict[str, Any]:
        """Get a specific task."""
        return await self._request(
            "GET",
            f"/api/v1/tasks/{task_id}",
            tenant_id=tenant_id
        )

    async def get_task_variables(
        self,
        tenant_id: str,
        task_id: str
    ) -> Dict[str, Any]:
        """Get variables for a task."""
        return await self._request(
            "GET",
            f"/api/v1/tasks/{task_id}/variables",
            tenant_id=tenant_id
        )

    async def complete_task(
        self,
        tenant_id: str,
        task_id: str,
        variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Complete a user task."""
        return await self._request(
            "POST",
            f"/api/v1/tasks/{task_id}/complete",
            tenant_id=tenant_id,
            json={"variables": variables or {}}
        )

    async def claim_task(
        self,
        tenant_id: str,
        task_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Claim a task for a user."""
        return await self._request(
            "POST",
            f"/api/v1/tasks/{task_id}/claim",
            tenant_id=tenant_id,
            json={"user_id": user_id}
        )

    async def unclaim_task(
        self,
        tenant_id: str,
        task_id: str
    ) -> Dict[str, Any]:
        """Unclaim a task."""
        return await self._request(
            "POST",
            f"/api/v1/tasks/{task_id}/unclaim",
            tenant_id=tenant_id
        )

    async def assign_task(
        self,
        tenant_id: str,
        task_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Assign a task to a user."""
        return await self._request(
            "POST",
            f"/api/v1/tasks/{task_id}/assign",
            tenant_id=tenant_id,
            json={"user_id": user_id}
        )

    # ============ Message Correlation ============

    async def correlate_message(
        self,
        tenant_id: str,
        message_name: str,
        business_key: Optional[str] = None,
        process_variables: Optional[Dict[str, Any]] = None,
        correlation_keys: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Correlate a message to running process instances."""
        return await self._request(
            "POST",
            "/api/v1/processes/message",
            tenant_id=tenant_id,
            json={
                "message_name": message_name,
                "business_key": business_key,
                "process_variables": process_variables or {},
                "correlation_keys": correlation_keys or {}
            }
        )

    # ============ Health Check ============

    async def health_check(self) -> Dict[str, Any]:
        """Check camunda service health."""
        client = await self._get_client()
        try:
            response = await client.get("/health")
            return response.json()
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}


# Service instance management
_workflow_service: Optional[WorkflowService] = None


def get_workflow_service() -> WorkflowService:
    """Get or create the global workflow service instance."""
    global _workflow_service
    if _workflow_service is None:
        _workflow_service = WorkflowService()
    return _workflow_service


async def close_workflow_service():
    """Close the global workflow service."""
    global _workflow_service
    if _workflow_service:
        await _workflow_service.close()
        _workflow_service = None
