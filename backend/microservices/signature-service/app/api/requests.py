"""
Signature request endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Response
import base64

from app.core.security import verify_api_key
from app.models.schemas import (
    CreateSignatureRequest,
    SignatureRequestResponse,
    GetStatusRequest,
    StatusResponse,
    CancelRequest,
    DownloadRequest
)
from app.services.signature_service import signature_service

router = APIRouter(prefix="/requests", dependencies=[Depends(verify_api_key)])

@router.post("/create", response_model=SignatureRequestResponse)
async def create_signature_request(request: CreateSignatureRequest):
    """Create a new signature request"""
    try:
        result = await signature_service.create_signature_request(
            provider_type=request.provider_type,
            credentials=request.provider_credentials,
            title=request.title,
            document_content=request.document_content,
            document_name=request.document_name,
            signers=request.signers,
            message=request.message,
            expires_in_days=request.expires_in_days,
            webhook_url=request.webhook_url,
            metadata=request.metadata
        )
        
        return SignatureRequestResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/status", response_model=StatusResponse)
async def get_signature_status(request: GetStatusRequest):
    """Get the status of a signature request"""
    try:
        result = await signature_service.get_signature_status(
            provider_type=request.provider_type,
            credentials=request.provider_credentials,
            external_id=request.external_id
        )
        
        return StatusResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/cancel")
async def cancel_signature_request(request: CancelRequest):
    """Cancel a signature request"""
    try:
        success = await signature_service.cancel_signature_request(
            provider_type=request.provider_type,
            credentials=request.provider_credentials,
            external_id=request.external_id,
            reason=request.reason
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to cancel signature request")
        
        return {"success": True, "message": "Signature request cancelled"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/download")
async def download_signed_document(request: DownloadRequest):
    """Download a signed document"""
    try:
        document_bytes = await signature_service.download_signed_document(
            provider_type=request.provider_type,
            credentials=request.provider_credentials,
            external_id=request.external_id
        )
        
        # Return as base64 encoded string
        return {
            "document": base64.b64encode(document_bytes).decode('utf-8'),
            "filename": f"signed_document_{request.external_id}.pdf"
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))