"""
API endpoints for Digital Signature management
"""
import logging
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.async_dependencies import get_async_db, get_current_active_user_async, get_current_active_superuser_async
from app.db.models import User
from app.services.async_signature_service import AsyncSignatureService
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
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Crear un proveedor de firma digital (solo administradores)"""
    
    # TODO: Verificar que el usuario es administrador del tenant
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create signature providers"
        )
    
    try:
        signature_service = AsyncSignatureService(db)
        provider = await signature_service.create_provider(
            provider_data,
            current_user.tenant_id,
            current_user.id
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
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Obtener proveedores de firma del tenant"""
    
    try:
        signature_service = AsyncSignatureService(db)
        providers = await signature_service.get_providers(
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
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Obtener un proveedor específico"""
    
    try:
        signature_service = AsyncSignatureService(db)
        provider = await signature_service.get_provider(provider_id, current_user.tenant_id)
        
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
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Obtener el proveedor por defecto"""
    
    try:
        signature_service = AsyncSignatureService(db)
        provider = await signature_service.get_default_provider(current_user.tenant_id)
        
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


@router.put("/providers/{provider_id}", response_model=SignatureProvider)
async def update_signature_provider(
    provider_id: UUID,
    provider_data: SignatureProviderCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """Actualizar un proveedor de firma (solo admin)"""
    
    try:
        signature_service = AsyncSignatureService(db)
        provider = await signature_service.update_provider(
            provider_id,
            provider_data,
            current_user.tenant_id,
            current_user.id
        )
        
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Signature provider not found"
            )
        
        return provider
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating signature provider: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating signature provider"
        )


@router.delete("/providers/{provider_id}")
async def delete_signature_provider(
    provider_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """Eliminar un proveedor de firma (solo admin)"""
    
    try:
        signature_service = AsyncSignatureService(db)
        success = await signature_service.delete_provider(
            provider_id,
            current_user.tenant_id,
            current_user.id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Signature provider not found"
            )
        
        return {"message": "Provider deleted successfully"}
        
    except Exception as e:
        logger.error(f"Error deleting signature provider: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting signature provider"
        )


@router.put("/providers/{provider_id}/set-default", response_model=SignatureProvider)
async def set_default_signature_provider(
    provider_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """Establecer un proveedor como predeterminado (solo admin)"""
    
    try:
        signature_service = AsyncSignatureService(db)
        provider = await signature_service.set_default_provider(
            provider_id,
            current_user.tenant_id,
            current_user.id
        )
        
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Signature provider not found"
            )
        
        return provider
        
    except Exception as e:
        logger.error(f"Error setting default provider: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error setting default provider"
        )


@router.post("/providers/{provider_id}/test")
async def test_signature_provider(
    provider_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """Probar la conexión con un proveedor (solo admin)"""
    
    try:
        signature_service = AsyncSignatureService(db)
        result = await signature_service.test_provider_connection(
            provider_id,
            current_user.tenant_id
        )
        
        return {
            "success": result["success"],
            "message": result.get("message", "Connection test completed")
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error testing provider: {str(e)}")
        return {
            "success": False,
            "message": f"Connection test failed: {str(e)}"
        }


@router.get("/providers/supported")
async def get_supported_providers(
    current_user: User = Depends(get_current_active_user_async)
):
    """Obtener lista de proveedores soportados y sus campos requeridos"""
    
    return [
        {
            "name": "docusign",
            "display_name": "DocuSign",
            "required_fields": ["integration_key", "secret_key", "account_id", "base_url"],
            "optional_fields": []
        },
        {
            "name": "yousign",
            "display_name": "YouSign",
            "required_fields": ["api_key", "environment"],
            "optional_fields": []
        },
        {
            "name": "signaturit",
            "display_name": "Signaturit",
            "required_fields": ["access_token", "environment"],
            "optional_fields": []
        }
    ]


# =====================================
# WEBHOOKS
# =====================================

@router.post("/webhooks/yousign")
async def yousign_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """Webhook para recibir actualizaciones de YouSign"""
    try:
        # Obtener el body como bytes para la verificación
        body = await request.body()
        
        # Verificar la firma del webhook (si YouSign lo proporciona)
        # headers = request.headers
        # signature = headers.get("X-YouSign-Signature")
        
        # Parsear el body
        data = await request.json()
        
        logger.info(f"YouSign webhook received: {data.get('event_name', 'unknown')}")
        
        # Procesar según el tipo de evento
        event_name = data.get('event_name')
        if not event_name:
            return {"status": "ignored", "reason": "no event_name"}
        
        signature_service = AsyncSignatureService(db)
        
        if event_name == 'signature_request.done':
            # Solicitud completada
            signature_request_id = data.get('data', {}).get('id')
            if signature_request_id:
                await signature_service.update_request_status_by_external_id(
                    signature_request_id,
                    'completed'
                )
        
        elif event_name == 'signature_request.expired':
            # Solicitud expirada
            signature_request_id = data.get('data', {}).get('id')
            if signature_request_id:
                await signature_service.update_request_status_by_external_id(
                    signature_request_id,
                    'expired'
                )
        
        elif event_name == 'signer.done':
            # Un firmante ha firmado
            signer_id = data.get('data', {}).get('id')
            if signer_id:
                await signature_service.update_signer_status_by_external_id(
                    signer_id,
                    'signed',
                    signed_at=datetime.now()
                )
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error processing YouSign webhook: {str(e)}")
        # No devolver error para evitar reintentos
        return {"status": "error", "message": str(e)}


@router.post("/webhooks/docusign")
async def docusign_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """Webhook para recibir actualizaciones de DocuSign"""
    try:
        data = await request.json()
        logger.info(f"DocuSign webhook received: {data.get('event', 'unknown')}")
        
        # TODO: Implementar procesamiento de webhook de DocuSign
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error processing DocuSign webhook: {str(e)}")
        return {"status": "error", "message": str(e)}


@router.post("/webhooks/signaturit")
async def signaturit_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """Webhook para recibir actualizaciones de Signaturit"""
    try:
        data = await request.json()
        logger.info(f"Signaturit webhook received: {data.get('event_type', 'unknown')}")
        
        # TODO: Implementar procesamiento de webhook de Signaturit
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error processing Signaturit webhook: {str(e)}")
        return {"status": "error", "message": str(e)}


# =====================================
# SIGNATURE REQUESTS
# ====================================

@router.post("/requests", response_model=SignatureRequest)
async def create_signature_request(
    request_data: SignatureRequestCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Crear una solicitud de firma"""
    
    try:
        signature_service = AsyncSignatureService(db)
        signature_request = await signature_service.create_signature_request(
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
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Enviar solicitud de firma a los firmantes"""
    
    try:
        signature_service = AsyncSignatureService(db)
        success = await signature_service.send_signature_request(
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
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Obtener solicitudes de firma del usuario"""
    
    try:
        signature_service = AsyncSignatureService(db)
        requests = await signature_service.get_signature_requests(
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
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Obtener una solicitud de firma específica"""
    
    try:
        signature_service = AsyncSignatureService(db)
        request = await signature_service.get_signature_request(
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
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Actualizar una solicitud de firma (solo en estado draft)"""
    
    try:
        signature_service = AsyncSignatureService(db)
        request = await signature_service.get_signature_request(
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
        
        await db.commit()
        await db.refresh(request)
        
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
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Actualizar estado de la solicitud desde el proveedor"""
    
    try:
        signature_service = AsyncSignatureService(db)
        updated_request = await signature_service.update_signature_status(
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
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Descargar documento firmado"""
    
    try:
        signature_service = AsyncSignatureService(db)
        
        # Verificar que la solicitud existe y pertenece al usuario
        request = await signature_service.get_signature_request(
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
        document_bytes = await signature_service.download_signed_document(
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
    db: AsyncSession = Depends(get_async_db)
):
    """Manejar webhooks de proveedores de firma"""
    
    try:
        # Obtener payload y signature
        payload = await request.json()
        signature = request.headers.get("X-Signature") or request.headers.get("Authorization", "")
        
        signature_service = AsyncSignatureService(db)
        success = await signature_service.handle_webhook(
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