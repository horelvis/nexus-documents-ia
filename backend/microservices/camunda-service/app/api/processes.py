"""Process definition and instance management endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any

from app.core.camunda_client import get_camunda_client

router = APIRouter(prefix="/processes", tags=["processes"])


class ProcessDefinitionResponse(BaseModel):
    id: str
    key: str
    name: Optional[str] = None
    version: int
    tenant_id: Optional[str] = None
    deployment_id: Optional[str] = None


class StartProcessRequest(BaseModel):
    process_key: str
    tenant_id: Optional[str] = None
    variables: Optional[dict[str, Any]] = None
    business_key: Optional[str] = None


class ProcessInstanceResponse(BaseModel):
    id: str
    definition_id: Optional[str] = None
    business_key: Optional[str] = None
    tenant_id: Optional[str] = None
    ended: bool = False


class ProcessInstanceListResponse(BaseModel):
    instances: list[dict]
    total: int


@router.get("/definitions", response_model=list[ProcessDefinitionResponse])
async def list_process_definitions(
    tenant_id: Optional[str] = None,
    key: Optional[str] = None,
    latest_version: bool = True
):
    """List available process definitions."""
    client = get_camunda_client()

    try:
        definitions = await client.get_process_definitions(
            tenant_id=tenant_id,
            key=key,
            latest_version=latest_version
        )

        return [
            ProcessDefinitionResponse(
                id=d.get("id"),
                key=d.get("key"),
                name=d.get("name"),
                version=d.get("version"),
                tenant_id=d.get("tenantId"),
                deployment_id=d.get("deploymentId")
            )
            for d in definitions
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list definitions: {str(e)}")


@router.get("/definitions/{key}/xml")
async def get_process_definition_xml(
    key: str,
    tenant_id: Optional[str] = None
):
    """Get BPMN XML for a process definition."""
    client = get_camunda_client()

    try:
        result = await client.get_process_definition_xml(key=key, tenant_id=tenant_id)
        return {
            "id": result.get("id"),
            "bpmn20Xml": result.get("bpmn20Xml")
        }

    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Process definition not found: {str(e)}")


@router.post("/start", response_model=ProcessInstanceResponse)
async def start_process(request: StartProcessRequest):
    """
    Start a new process instance.

    Args:
        process_key: Key of the process definition to start
        tenant_id: Tenant ID for multi-tenant environments
        variables: Initial process variables
        business_key: Business key for correlation (e.g., document ID)
    """
    client = get_camunda_client()

    try:
        result = await client.start_process(
            process_key=request.process_key,
            tenant_id=request.tenant_id,
            variables=request.variables,
            business_key=request.business_key
        )

        return ProcessInstanceResponse(
            id=result.get("id"),
            definition_id=result.get("definitionId"),
            business_key=result.get("businessKey"),
            tenant_id=result.get("tenantId"),
            ended=result.get("ended", False)
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to start process: {str(e)}")


@router.get("/instances", response_model=ProcessInstanceListResponse)
async def list_process_instances(
    tenant_id: Optional[str] = None,
    process_definition_key: Optional[str] = None,
    business_key: Optional[str] = None,
    active: Optional[bool] = None
):
    """List process instances."""
    client = get_camunda_client()

    try:
        instances = await client.get_process_instances(
            tenant_id=tenant_id,
            process_definition_key=process_definition_key,
            business_key=business_key,
            active=active
        )

        return ProcessInstanceListResponse(
            instances=instances,
            total=len(instances)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list instances: {str(e)}")


@router.get("/instances/{instance_id}")
async def get_process_instance(instance_id: str):
    """Get a specific process instance."""
    client = get_camunda_client()

    try:
        return await client.get_process_instance(instance_id)

    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Process instance not found: {str(e)}")


@router.get("/instances/{instance_id}/variables")
async def get_process_variables(instance_id: str):
    """Get all variables for a process instance."""
    client = get_camunda_client()

    try:
        return await client.get_process_instance_variables(instance_id)

    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Failed to get variables: {str(e)}")


@router.delete("/instances/{instance_id}")
async def cancel_process_instance(instance_id: str):
    """Cancel (delete) a running process instance."""
    client = get_camunda_client()

    try:
        await client.delete_process_instance(instance_id)
        return {"message": f"Process instance {instance_id} cancelled successfully"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to cancel instance: {str(e)}")


class MessageCorrelationRequest(BaseModel):
    message_name: str
    business_key: Optional[str] = None
    tenant_id: Optional[str] = None
    process_variables: Optional[dict[str, Any]] = None
    correlation_keys: Optional[dict[str, Any]] = None


@router.post("/message")
async def correlate_message(request: MessageCorrelationRequest):
    """
    Correlate a message to trigger message events.

    Used to send signals/messages to running process instances
    or to start processes with message start events.
    """
    client = get_camunda_client()

    try:
        result = await client.correlate_message(
            message_name=request.message_name,
            business_key=request.business_key,
            tenant_id=request.tenant_id,
            process_variables=request.process_variables,
            correlation_keys=request.correlation_keys
        )

        return {"correlated": result}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Message correlation failed: {str(e)}")
