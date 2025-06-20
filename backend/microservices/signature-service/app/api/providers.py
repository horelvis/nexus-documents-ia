"""
Provider management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List

from app.core.security import verify_api_key
from app.models.schemas import (
    TestConnectionRequest, 
    TestConnectionResponse,
    ProviderType
)
from app.services.signature_service import signature_service

router = APIRouter(prefix="/providers", dependencies=[Depends(verify_api_key)])

@router.post("/test", response_model=TestConnectionResponse)
async def test_provider_connection(request: TestConnectionRequest):
    """Test connection to a signature provider"""
    try:
        result = await signature_service.test_connection(
            request.provider_type,
            request.provider_credentials
        )
        return TestConnectionResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/supported")
async def get_supported_providers():
    """Get list of supported providers and their required fields"""
    return [
        {
            "name": ProviderType.DOCUSIGN,
            "display_name": "DocuSign",
            "required_fields": ["integration_key", "secret_key", "account_id", "base_url"],
            "optional_fields": []
        },
        {
            "name": ProviderType.YOUSIGN,
            "display_name": "YouSign",
            "required_fields": ["api_key", "environment"],
            "optional_fields": []
        },
        {
            "name": ProviderType.SIGNATURIT,
            "display_name": "Signaturit",
            "required_fields": ["access_token", "environment"],
            "optional_fields": []
        }
    ]