"""
API endpoints for Digital Signature management
"""
import logging
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_current_active_user
from app.db.models import User
from app.services.signature_service import SignatureService
from app.schemas.signature import (
    SignatureProviderCreate, SignatureProviderUpdate, SignatureProvider,
    SignatureRequestCreate, SignatureRequestUpdate, SignatureRequest
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =====================================
# SIGNATURE PROVIDERS
# =====================================

@router.post("/providers", response_model=SignatureProvider)
async def create_signature_provider(
    provider_data: SignatureProviderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Crear un proveedor de firma digital (solo administradores)"""
    
    # TODO: Verificar que el usuario es administrador del tenant
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create signature providers"
        )
    
    try:
        signature_service = SignatureService(db)
        provider = signature_service.create_provider(
            provider_data,
            current_user.tenant_id
        )
        return provider
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating signature provider: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating signature provider"
        )


@router.get("/providers", response_model=List[SignatureProvider])
async def get_signature_providers(
    is_active: Optional[bool] = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtener proveedores de firma del tenant"""
    
    try:
        signature_service = SignatureService(db)
        providers = signature_service.get_providers(
            current_user.tenant_id,
            is_active=is_active
        )
        return providers
        
    except Exception as e:
        logger.error(f"Error getting signature providers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving signature providers"
        )


@router.get("/providers/{provider_id}", response_model=SignatureProvider)
async def get_signature_provider(
    provider_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtener un proveedor específico"""
    
    try:
        signature_service = SignatureService(db)
        provider = signature_service.get_provider(provider_id, current_user.tenant_id)
        
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Signature provider not found"
            )
        
        return provider
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting signature provider: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving signature provider"
        )


@router.get("/providers/default", response_model=SignatureProvider)
async def get_default_signature_provider(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtener el proveedor por defecto"""
    
    try:
        signature_service = SignatureService(db)
        provider = signature_service.get_default_provider(current_user.tenant_id)
        
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No default signature provider configured"
            )
        
        return provider
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting default provider: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving default provider"
        )


# =====================================
# SIGNATURE REQUESTS
# =====================================

@router.post("/requests", response_model=SignatureRequest)
async def create_signature_request(
    request_data: SignatureRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Crear una solicitud de firma"""
    
    try:
        signature_service = SignatureService(db)
        signature_request = signature_service.create_signature_request(
            request_data,
            current_user.tenant_id,
            current_user.id
        )
        return signature_request
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating signature request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating signature request"
        )


@router.post("/requests/{request_id}/send")
async def send_signature_request(
    request_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Enviar solicitud de firma a los firmantes"""
    
    try:
        signature_service = SignatureService(db)
        success = signature_service.send_signature_request(
            request_id,
            current_user.tenant_id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error sending signature request"
            )
        
        return {"message": "Signature request sent successfully"}
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error sending signature request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error sending signature request"
        )


@router.get("/requests", response_model=List[SignatureRequest])
async def get_signature_requests(
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtener solicitudes de firma del usuario"""
    
    try:
        signature_service = SignatureService(db)
        requests = signature_service.get_signature_requests(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            status=status_filter,
            limit=limit,
            offset=offset
        )
        return requests
        
    except Exception as e:
        logger.error(f"Error getting signature requests: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving signature requests"
        )


@router.get("/requests/{request_id}", response_model=SignatureRequest)
async def get_signature_request(
    request_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtener una solicitud de firma específica"""
    
    try:
        signature_service = SignatureService(db)
        request = signature_service.get_signature_request(
            request_id,
            current_user.tenant_id
        )
        
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Signature request not found"
            )
        
        return request
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting signature request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving signature request"
        )


@router.put("/requests/{request_id}", response_model=SignatureRequest)
async def update_signature_request(
    request_id: UUID,
    request_data: SignatureRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Actualizar una solicitud de firma (solo en estado draft)"""
    
    try:
        signature_service = SignatureService(db)
        request = signature_service.get_signature_request(
            request_id,
            current_user.tenant_id
        )
        
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Signature request not found"
            )
        
        if request.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied"
            )
        
        if request.status != 'draft':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only draft requests can be updated"
            )
        
        # Actualizar campos
        update_data = request_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(request, field, value)
        
        db.commit()
        db.refresh(request)
        
        return request
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating signature request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating signature request"
        )


@router.post("/requests/{request_id}/refresh-status")
async def refresh_signature_status(
    request_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Actualizar estado de la solicitud desde el proveedor"""
    
    try:
        signature_service = SignatureService(db)
        updated_request = signature_service.update_signature_status(
            request_id,
            current_user.tenant_id
        )
        
        if not updated_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Signature request not found"
            )
        
        return {
            "message": "Status updated successfully",
            "status": updated_request.status
        }
        
    except Exception as e:
        logger.error(f"Error refreshing signature status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error refreshing signature status"
        )


@router.get("/requests/{request_id}/download")
async def download_signed_document(
    request_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Descargar documento firmado"""
    
    try:
        signature_service = SignatureService(db)
        
        # Verificar que la solicitud existe y pertenece al usuario
        request = signature_service.get_signature_request(
            request_id,
            current_user.tenant_id
        )
        
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Signature request not found"
            )
        
        if request.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied"
            )
        
        if request.status != 'completed':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document is not yet signed"
            )
        
        # Descargar documento
        document_bytes = signature_service.download_signed_document(
            request_id,
            current_user.tenant_id
        )
        
        if not document_bytes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Signed document not available"
            )
        
        return Response(
            content=document_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={request.document_name}_signed.pdf"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error downloading document"
        )


# =====================================
# WEBHOOKS
# =====================================

@router.post("/webhooks/{provider_name}")
async def handle_signature_webhook(
    provider_name: str,
    request: Request,
    tenant_id: UUID,  # Debe venir como query parameter
    db: Session = Depends(get_db)
):
    """Manejar webhooks de proveedores de firma"""
    
    try:
        # Obtener payload y signature
        payload = await request.json()
        signature = request.headers.get("X-Signature") or request.headers.get("Authorization", "")
        
        signature_service = SignatureService(db)
        success = signature_service.handle_webhook(
            provider_name,
            payload,
            signature,
            tenant_id
        )
        
        if success:
            return {"message": "Webhook processed successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook"
            )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error handling webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing webhook"
        )


# =====================================
# UTILITIES
# =====================================

@router.get("/providers/supported")
async def get_supported_providers():
    """Obtener lista de proveedores soportados"""
    
    return {
        "providers": [
            {
                "name": "docusign",
                "display_name": "DocuSign",
                "description": "Líder mundial en firma electrónica",
                "features": ["sequential", "parallel", "authentication", "templates"]
            },
            {
                "name": "yousign",
                "display_name": "YouSign",
                "description": "Solución europea de firma electrónica",
                "features": ["sequential", "parallel", "authentication", "embedded"]
            },
            {
                "name": "signaturit",
                "display_name": "Signaturit",
                "description": "Plataforma avanzada de firma digital",
                "features": ["sequential", "parallel", "authentication", "bulk_signing"]
            }
        ]
    }


@router.get("/status-definitions")
async def get_status_definitions():
    """Obtener definiciones de estados de firma"""
    
    return {
        "request_statuses": {
            "draft": "Borrador - Solicitud creada pero no enviada",
            "sent": "Enviada - Solicitud enviada a firmantes",
            "in_progress": "En progreso - Algunos firmantes han firmado",
            "completed": "Completada - Todos han firmado",
            "declined": "Rechazada - Algún firmante rechazó",
            "expired": "Expirada - Tiempo límite excedido"
        },
        "signer_statuses": {
            "pending": "Pendiente - Esperando envío",
            "sent": "Enviada - Invitación enviada",
            "opened": "Abierta - Firmante vio el documento",
            "signed": "Firmada - Firmante completó la firma",
            "declined": "Rechazada - Firmante rechazó firmar"
        }
    }