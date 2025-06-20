"""
Webhook endpoints for signature providers
"""
from fastapi import APIRouter, Request, Response
import logging
import httpx
from datetime import datetime

from app.core.config import settings
from app.models.schemas import WebhookEvent, ProviderType

router = APIRouter(prefix="/webhooks")
logger = logging.getLogger(__name__)

async def forward_webhook_to_main_api(provider: str, data: dict):
    """Forward webhook data to main API"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.MAIN_API_URL}/api/v1/signatures/webhooks/{provider}",
                json=data,
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
                timeout=settings.WEBHOOK_TIMEOUT
            )
            
            if response.status_code >= 400:
                logger.error(f"Failed to forward webhook to main API: {response.status_code}")
                
    except Exception as e:
        logger.error(f"Error forwarding webhook: {str(e)}")

@router.post("/yousign")
async def yousign_webhook(request: Request):
    """Receive webhooks from YouSign"""
    try:
        body = await request.body()
        data = await request.json()
        
        logger.info(f"YouSign webhook received: {data.get('event_name', 'unknown')}")
        
        # Forward to main API
        await forward_webhook_to_main_api("yousign", data)
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error processing YouSign webhook: {str(e)}")
        return {"status": "error", "message": str(e)}

@router.post("/docusign")
async def docusign_webhook(request: Request):
    """Receive webhooks from DocuSign"""
    try:
        data = await request.json()
        
        logger.info(f"DocuSign webhook received: {data.get('event', 'unknown')}")
        
        # Forward to main API
        await forward_webhook_to_main_api("docusign", data)
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error processing DocuSign webhook: {str(e)}")
        return {"status": "error", "message": str(e)}

@router.post("/signaturit")
async def signaturit_webhook(request: Request):
    """Receive webhooks from Signaturit"""
    try:
        data = await request.json()
        
        logger.info(f"Signaturit webhook received: {data.get('event_type', 'unknown')}")
        
        # Forward to main API
        await forward_webhook_to_main_api("signaturit", data)
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error processing Signaturit webhook: {str(e)}")
        return {"status": "error", "message": str(e)}