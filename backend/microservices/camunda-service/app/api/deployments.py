"""Deployment management endpoints."""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional

from app.core.camunda_client import get_camunda_client

router = APIRouter(prefix="/deployments", tags=["deployments"])


class DeploymentResponse(BaseModel):
    id: str
    name: str
    source: Optional[str] = None
    tenant_id: Optional[str] = None
    deployment_time: Optional[str] = None
    deployed_process_definitions: Optional[list[dict]] = None


class DeploymentListResponse(BaseModel):
    deployments: list[dict]
    total: int


@router.post("", response_model=DeploymentResponse)
async def create_deployment(
    name: str = Form(..., description="Deployment name"),
    tenant_id: str = Form(None, description="Tenant ID for multi-tenant deployment"),
    bpmn_file: UploadFile = File(..., description="BPMN 2.0 XML file")
):
    """
    Deploy a BPMN process definition.

    The BPMN file should be a valid BPMN 2.0 XML document.
    Use tenant_id for multi-tenant deployments.
    """
    client = get_camunda_client()

    try:
        bpmn_content = await bpmn_file.read()
        bpmn_xml = bpmn_content.decode("utf-8")

        result = await client.create_deployment(
            name=name,
            bpmn_xml=bpmn_xml,
            tenant_id=tenant_id
        )

        return DeploymentResponse(
            id=result.get("id"),
            name=result.get("name"),
            source=result.get("source"),
            tenant_id=result.get("tenantId"),
            deployment_time=result.get("deploymentTime"),
            deployed_process_definitions=result.get("deployedProcessDefinitions")
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Deployment failed: {str(e)}")


@router.post("/xml", response_model=DeploymentResponse)
async def create_deployment_from_xml(
    name: str,
    bpmn_xml: str,
    tenant_id: Optional[str] = None
):
    """
    Deploy a BPMN process from XML string.

    Alternative to file upload for programmatic deployments.
    """
    client = get_camunda_client()

    try:
        result = await client.create_deployment(
            name=name,
            bpmn_xml=bpmn_xml,
            tenant_id=tenant_id
        )

        return DeploymentResponse(
            id=result.get("id"),
            name=result.get("name"),
            source=result.get("source"),
            tenant_id=result.get("tenantId"),
            deployment_time=result.get("deploymentTime"),
            deployed_process_definitions=result.get("deployedProcessDefinitions")
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Deployment failed: {str(e)}")


@router.get("", response_model=DeploymentListResponse)
async def list_deployments(
    tenant_id: Optional[str] = None,
    name: Optional[str] = None,
    first_result: int = 0,
    max_results: int = 100
):
    """List deployments, optionally filtered by tenant."""
    client = get_camunda_client()

    try:
        deployments = await client.get_deployments(
            tenant_id=tenant_id,
            name=name,
            first_result=first_result,
            max_results=max_results
        )

        return DeploymentListResponse(
            deployments=deployments,
            total=len(deployments)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list deployments: {str(e)}")


@router.delete("/{deployment_id}")
async def delete_deployment(
    deployment_id: str,
    cascade: bool = True
):
    """
    Delete a deployment.

    If cascade=True, also deletes all process instances and history.
    """
    client = get_camunda_client()

    try:
        await client.delete_deployment(deployment_id, cascade=cascade)
        return {"message": f"Deployment {deployment_id} deleted successfully"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to delete deployment: {str(e)}")
