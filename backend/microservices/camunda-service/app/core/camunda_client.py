"""
Camunda 7 REST API Client

Wrapper for interacting with Camunda BPM Platform REST API.
Supports multi-tenant deployments via tenant-id parameter.
"""

import httpx
from typing import Any, Optional
from datetime import datetime

from app.core.config import get_settings


class CamundaClient:
    """Async client for Camunda 7 REST API."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.camunda_rest_url
        self.timeout = self.settings.CAMUNDA_TIMEOUT

    async def _request(
        self,
        method: str,
        endpoint: str,
        json: dict = None,
        params: dict = None,
        files: dict = None,
        data: dict = None
    ) -> dict | list | None:
        """Make HTTP request to Camunda REST API."""
        url = f"{self.base_url}{endpoint}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(
                method=method,
                url=url,
                json=json,
                params=params,
                files=files,
                data=data
            )

            if response.status_code == 204:
                return None

            response.raise_for_status()
            return response.json() if response.content else None

    # ==================== Engine ====================

    async def get_engine_info(self) -> list[dict]:
        """Get information about registered process engines."""
        return await self._request("GET", "/engine")

    # ==================== Deployments ====================

    async def create_deployment(
        self,
        name: str,
        bpmn_xml: str,
        tenant_id: str = None,
        source: str = "NouxCubeIA"
    ) -> dict:
        """
        Deploy a BPMN process definition.

        Args:
            name: Deployment name
            bpmn_xml: BPMN 2.0 XML content
            tenant_id: Tenant identifier for multi-tenant deployment
            source: Deployment source identifier

        Returns:
            Deployment information including deployed process definitions
        """
        files = {
            "deployment-name": (None, name),
            "enable-duplicate-filtering": (None, "true"),
            "deploy-changed-only": (None, "true"),
            "deployment-source": (None, source),
        }

        if tenant_id:
            files["tenant-id"] = (None, tenant_id)

        # Add BPMN file
        files["data"] = (f"{name}.bpmn", bpmn_xml, "application/octet-stream")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/deployment/create",
                files=files
            )
            response.raise_for_status()
            return response.json()

    async def get_deployments(
        self,
        tenant_id: str = None,
        name: str = None,
        first_result: int = 0,
        max_results: int = 100
    ) -> list[dict]:
        """List deployments, optionally filtered by tenant."""
        params = {
            "firstResult": first_result,
            "maxResults": max_results,
            "sortBy": "deploymentTime",
            "sortOrder": "desc"
        }

        if tenant_id:
            params["tenantIdIn"] = tenant_id
        if name:
            params["nameLike"] = f"%{name}%"

        return await self._request("GET", "/deployment", params=params)

    async def delete_deployment(
        self,
        deployment_id: str,
        cascade: bool = True,
        skip_custom_listeners: bool = True
    ) -> None:
        """Delete a deployment and optionally all related instances."""
        params = {
            "cascade": str(cascade).lower(),
            "skipCustomListeners": str(skip_custom_listeners).lower()
        }
        await self._request("DELETE", f"/deployment/{deployment_id}", params=params)

    # ==================== Process Definitions ====================

    async def get_process_definitions(
        self,
        tenant_id: str = None,
        key: str = None,
        latest_version: bool = True
    ) -> list[dict]:
        """List process definitions."""
        params = {"latestVersion": str(latest_version).lower()}

        if tenant_id:
            params["tenantIdIn"] = tenant_id
        if key:
            params["key"] = key

        return await self._request("GET", "/process-definition", params=params)

    async def get_process_definition_xml(
        self,
        process_definition_id: str = None,
        key: str = None,
        tenant_id: str = None
    ) -> dict:
        """Get BPMN XML for a process definition."""
        if process_definition_id:
            endpoint = f"/process-definition/{process_definition_id}/xml"
        elif key and tenant_id:
            endpoint = f"/process-definition/key/{key}/tenant-id/{tenant_id}/xml"
        elif key:
            endpoint = f"/process-definition/key/{key}/xml"
        else:
            raise ValueError("Must provide process_definition_id or key")

        return await self._request("GET", endpoint)

    # ==================== Process Instances ====================

    async def start_process(
        self,
        process_key: str,
        tenant_id: str = None,
        variables: dict = None,
        business_key: str = None
    ) -> dict:
        """
        Start a new process instance.

        Args:
            process_key: Process definition key
            tenant_id: Tenant identifier
            variables: Process variables
            business_key: Business key for correlation

        Returns:
            Process instance information
        """
        if tenant_id:
            endpoint = f"/process-definition/key/{process_key}/tenant-id/{tenant_id}/start"
        else:
            endpoint = f"/process-definition/key/{process_key}/start"

        body = {}
        if variables:
            body["variables"] = self._format_variables(variables)
        if business_key:
            body["businessKey"] = business_key

        return await self._request("POST", endpoint, json=body)

    async def get_process_instances(
        self,
        tenant_id: str = None,
        process_definition_key: str = None,
        business_key: str = None,
        active: bool = None
    ) -> list[dict]:
        """List process instances."""
        params = {}

        if tenant_id:
            params["tenantIdIn"] = tenant_id
        if process_definition_key:
            params["processDefinitionKey"] = process_definition_key
        if business_key:
            params["businessKey"] = business_key
        if active is not None:
            params["active"] = str(active).lower()

        return await self._request("GET", "/process-instance", params=params)

    async def get_process_instance(self, process_instance_id: str) -> dict:
        """Get a specific process instance."""
        return await self._request("GET", f"/process-instance/{process_instance_id}")

    async def delete_process_instance(
        self,
        process_instance_id: str,
        skip_custom_listeners: bool = True
    ) -> None:
        """Delete (cancel) a process instance."""
        params = {"skipCustomListeners": str(skip_custom_listeners).lower()}
        await self._request("DELETE", f"/process-instance/{process_instance_id}", params=params)

    # ==================== Tasks ====================

    async def get_tasks(
        self,
        tenant_id: str = None,
        assignee: str = None,
        candidate_user: str = None,
        process_instance_id: str = None,
        process_definition_key: str = None,
        unassigned: bool = None,
        first_result: int = 0,
        max_results: int = 100
    ) -> list[dict]:
        """List user tasks."""
        params = {
            "firstResult": first_result,
            "maxResults": max_results,
            "sortBy": "created",
            "sortOrder": "desc"
        }

        if tenant_id:
            params["tenantIdIn"] = tenant_id
        if assignee:
            params["assignee"] = assignee
        if candidate_user:
            params["candidateUser"] = candidate_user
        if process_instance_id:
            params["processInstanceId"] = process_instance_id
        if process_definition_key:
            params["processDefinitionKey"] = process_definition_key
        if unassigned is not None:
            params["unassigned"] = str(unassigned).lower()

        return await self._request("GET", "/task", params=params)

    async def get_task(self, task_id: str) -> dict:
        """Get a specific task."""
        return await self._request("GET", f"/task/{task_id}")

    async def get_task_variables(self, task_id: str) -> dict:
        """Get variables for a task."""
        return await self._request("GET", f"/task/{task_id}/variables")

    async def complete_task(
        self,
        task_id: str,
        variables: dict = None
    ) -> None:
        """
        Complete a user task.

        Args:
            task_id: Task identifier
            variables: Variables to set when completing
        """
        body = {}
        if variables:
            body["variables"] = self._format_variables(variables)

        await self._request("POST", f"/task/{task_id}/complete", json=body)

    async def claim_task(self, task_id: str, user_id: str) -> None:
        """Claim a task for a user."""
        await self._request("POST", f"/task/{task_id}/claim", json={"userId": user_id})

    async def unclaim_task(self, task_id: str) -> None:
        """Unclaim a task."""
        await self._request("POST", f"/task/{task_id}/unclaim")

    async def assign_task(self, task_id: str, user_id: str) -> None:
        """Assign a task to a user."""
        await self._request("POST", f"/task/{task_id}/assignee", json={"userId": user_id})

    # ==================== Variables ====================

    async def get_process_instance_variables(self, process_instance_id: str) -> dict:
        """Get all variables for a process instance."""
        return await self._request("GET", f"/process-instance/{process_instance_id}/variables")

    async def set_process_instance_variable(
        self,
        process_instance_id: str,
        variable_name: str,
        value: Any,
        value_type: str = None
    ) -> None:
        """Set a variable on a process instance."""
        body = {"value": value}
        if value_type:
            body["type"] = value_type

        await self._request(
            "PUT",
            f"/process-instance/{process_instance_id}/variables/{variable_name}",
            json=body
        )

    # ==================== Messages ====================

    async def correlate_message(
        self,
        message_name: str,
        business_key: str = None,
        tenant_id: str = None,
        process_variables: dict = None,
        correlation_keys: dict = None
    ) -> list[dict]:
        """
        Correlate a message to trigger message events.

        Used for message start events and intermediate message catch events.
        """
        body = {"messageName": message_name, "all": True}

        if business_key:
            body["businessKey"] = business_key
        if tenant_id:
            body["tenantId"] = tenant_id
        if process_variables:
            body["processVariables"] = self._format_variables(process_variables)
        if correlation_keys:
            body["correlationKeys"] = self._format_variables(correlation_keys)

        return await self._request("POST", "/message", json=body)

    # ==================== Helpers ====================

    def _format_variables(self, variables: dict) -> dict:
        """Format variables for Camunda REST API."""
        formatted = {}
        for key, value in variables.items():
            if isinstance(value, bool):
                formatted[key] = {"value": value, "type": "Boolean"}
            elif isinstance(value, int):
                formatted[key] = {"value": value, "type": "Integer"}
            elif isinstance(value, float):
                formatted[key] = {"value": value, "type": "Double"}
            elif isinstance(value, datetime):
                formatted[key] = {"value": value.isoformat(), "type": "Date"}
            elif isinstance(value, dict):
                formatted[key] = {"value": value, "type": "Json"}
            else:
                formatted[key] = {"value": str(value), "type": "String"}
        return formatted

    def _parse_variables(self, variables: dict) -> dict:
        """Parse variables from Camunda REST API response."""
        parsed = {}
        for key, var_data in variables.items():
            parsed[key] = var_data.get("value")
        return parsed


# Global client instance
_client: Optional[CamundaClient] = None


def get_camunda_client() -> CamundaClient:
    """Get or create Camunda client instance."""
    global _client
    if _client is None:
        _client = CamundaClient()
    return _client
