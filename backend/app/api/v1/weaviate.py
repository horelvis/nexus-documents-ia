"""Weaviate API endpoints as gateway to Weaviate microservice"""
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Dict, Any, Optional
import logging
import httpx

from app.api.dependencies import get_current_tenant
from app.core.config import settings
from app.db.models import Tenant

logger = logging.getLogger(__name__)
router = APIRouter()

# Weaviate service configuration
WEAVIATE_SERVICE_URL = settings.WEAVIATE_SERVICE_URL

@router.post("/elysia/query")
async def elysia_query(
    request: Request,
    current_tenant: Tenant = Depends(get_current_tenant)
):
    """Proxy Elysia queries to Weaviate service"""
    try:
        # Get request body
        body = await request.json()
        
        # Ensure tenant_id is set to current tenant
        body["tenant_id"] = str(current_tenant.id)
        
        # Get microservice API key from settings
        microservice_key = settings.microservices_api_key
        
        # Forward to Weaviate service
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{WEAVIATE_SERVICE_URL}/elysia/query",
                json=body,
                headers={
                    "Authorization": f"Bearer {microservice_key}",
                    "Content-Type": "application/json"
                },
                timeout=120.0  # Extended timeout for Elysia processing
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"❌ Elysia service error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Elysia service error: {response.text}"
                )
                
    except httpx.TimeoutException:
        logger.error("⏱️ Elysia service timeout")
        raise HTTPException(status_code=504, detail="Elysia service timeout")
    except Exception as e:
        logger.error(f"❌ Elysia proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/elysia/health")
async def elysia_health():
    """Check Elysia service health"""
    try:
        microservice_key = settings.microservices_api_key
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/elysia/health",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=30.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "status": "unhealthy",
                    "service": "elysia",
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
                
    except Exception as e:
        logger.error(f"❌ Elysia health check failed: {e}")
        return {
            "status": "unhealthy",
            "service": "elysia",
            "error": str(e)
        }

@router.get("/elysia/tools")
async def elysia_list_tools():
    """List available Elysia tools"""
    try:
        microservice_key = settings.microservices_api_key
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/elysia/tools",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=30.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Tools listing error: {response.text}"
                )
                
    except Exception as e:
        logger.error(f"❌ Failed to list Elysia tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/elysia/feedback")
async def elysia_feedback(
    request: Request,
    current_tenant: Tenant = Depends(get_current_tenant)
):
    """Submit feedback to Elysia for learning"""
    try:
        body = await request.json()
        body["tenant_id"] = str(current_tenant.id)
        
        microservice_key = settings.microservices_api_key
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{WEAVIATE_SERVICE_URL}/elysia/feedback",
                json=body,
                headers={
                    "Authorization": f"Bearer {microservice_key}",
                    "Content-Type": "application/json"
                },
                timeout=30.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Feedback submission error: {response.text}"
                )
                
    except Exception as e:
        logger.error(f"❌ Elysia feedback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# PUBLIC KNOWLEDGE BASE ENDPOINTS
# ============================================================================

@router.get("/public-knowledge/health")
async def public_knowledge_health():
    """Check public knowledge base health"""
    try:
        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/public-knowledge/health",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=15.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "status": "unhealthy",
                    "error": f"HTTP {response.status_code}: {response.text}"
                }

    except Exception as e:
        logger.error(f"Public knowledge health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}


@router.get("/public-knowledge/stats")
async def public_knowledge_stats():
    """Get public knowledge base statistics"""
    try:
        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/public-knowledge/stats",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=30.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Stats error: {response.text}"
                )

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Service timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Public knowledge stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/public-knowledge/categories")
async def public_knowledge_categories():
    """Get available categories"""
    try:
        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/public-knowledge/categories",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=15.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Categories error: {response.text}"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Public knowledge categories error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/public-knowledge/jurisdictions")
async def public_knowledge_jurisdictions():
    """Get available jurisdictions"""
    try:
        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/public-knowledge/jurisdictions",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=15.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Jurisdictions error: {response.text}"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Public knowledge jurisdictions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/public-knowledge/search")
async def public_knowledge_search(request: Request):
    """Search public knowledge base"""
    try:
        body = await request.json()
        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{WEAVIATE_SERVICE_URL}/public-knowledge/search",
                json=body,
                headers={
                    "Authorization": f"Bearer {microservice_key}",
                    "Content-Type": "application/json"
                },
                timeout=60.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Search error: {response.text}"
                )

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Search timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Public knowledge search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/public-knowledge/documents/{doc_id}")
async def public_knowledge_get_document(doc_id: str):
    """Get a specific document from public knowledge base"""
    try:
        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/public-knowledge/documents/{doc_id}",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=30.0
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                raise HTTPException(status_code=404, detail="Document not found")
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Get document error: {response.text}"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Public knowledge get document error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def weaviate_service_health():
    """Overall Weaviate service health including Elysia"""
    try:
        microservice_key = settings.microservices_api_key
        
        async with httpx.AsyncClient() as client:
            # Check Weaviate service health
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/health",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=15.0
            )
            
            weaviate_health = response.json() if response.status_code == 200 else {
                "status": "unhealthy", "error": f"HTTP {response.status_code}"
            }
            
            # Check Elysia health
            elysia_response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/elysia/health",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=15.0
            )
            
            elysia_health = elysia_response.json() if elysia_response.status_code == 200 else {
                "status": "unhealthy", "error": f"HTTP {elysia_response.status_code}"
            }
            
            return {
                "weaviate_service": weaviate_health,
                "elysia": elysia_health,
                "overall_status": "healthy" if (
                    weaviate_health.get("status") == "healthy" and
                    elysia_health.get("status") == "healthy"
                ) else "unhealthy"
            }
                
    except Exception as e:
        logger.error(f"❌ Weaviate service health check failed: {e}")
        return {
            "overall_status": "unhealthy",
            "error": str(e)
        }