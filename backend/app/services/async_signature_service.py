"""
Async Digital Signature Service with Multi-Provider Support
"""
import logging
import json
import hmac
import hashlib
import httpx
import base64
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, func, desc, select, update
from sqlalchemy.orm import selectinload
from cryptography.fernet import Fernet

from app.db.models import (
    SignatureProvider, SignatureRequest, SignatureRequestSigner, 
    SignatureEvent, SignatureProviderAudit, Tenant, User, SignatureContact
)
from app.schemas.signature import (
    SignatureProviderCreate, SignatureProviderUpdate,
    SignatureRequestCreate, SignatureRequestUpdate,
    SignerCreate
)
from app.core.config import settings
from app.services.signature_microservice_client import signature_client

logger = logging.getLogger(__name__)


# Note: Provider strategies have been moved to the signature microservice
# The AsyncSignatureService now uses the microservice client for all provider operations


# All provider strategy implementations have been moved to the signature microservice


class AsyncSignatureService:
    """Async version of SignatureService"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.encryption_key = self._get_encryption_key()
        self.fernet = Fernet(self.encryption_key)
    
    def _get_encryption_key(self) -> bytes:
        """Obtener clave de encriptación"""
        # TODO: Usar una clave más segura desde variables de entorno
        key = getattr(settings, 'SIGNATURE_ENCRYPTION_KEY', None)
        if not key:
            # Generar clave temporal (usar solo en desarrollo)
            key = Fernet.generate_key()
            logger.warning("Using temporary encryption key - not suitable for production")
        return key if isinstance(key, bytes) else key.encode()
    
    def _encrypt_credentials(self, credentials: Dict[str, Any]) -> bytes:
        """Encriptar credenciales"""
        credentials_json = json.dumps(credentials)
        return self.fernet.encrypt(credentials_json.encode())
    
    def _decrypt_credentials(self, encrypted_credentials: bytes) -> Dict[str, Any]:
        """Desencriptar credenciales"""
        decrypted = self.fernet.decrypt(encrypted_credentials)
        return json.loads(decrypted.decode())
    
    # =====================================
    # PROVIDER MANAGEMENT
    # =====================================
    
    async def create_provider(
        self, 
        provider_data: SignatureProviderCreate, 
        tenant_id: UUID,
        created_by: UUID
    ) -> SignatureProvider:
        """Crear un proveedor de firma"""
        try:
            # Verificar que el proveedor no exista ya
            stmt = select(SignatureProvider).filter(
                and_(
                    SignatureProvider.tenant_id == tenant_id,
                    SignatureProvider.provider_name == provider_data.provider_name
                )
            )
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                raise ValueError(f"Provider {provider_data.provider_name} already exists for this tenant")
            
            # Encriptar credenciales
            encrypted_creds = self._encrypt_credentials(provider_data.credentials)
            
            # Si es el primer proveedor, marcarlo como default
            is_default = provider_data.is_default
            if not is_default:
                count_stmt = select(func.count()).select_from(SignatureProvider).filter(
                    SignatureProvider.tenant_id == tenant_id
                )
                result = await self.db.execute(count_stmt)
                existing_providers = result.scalar()
                is_default = existing_providers == 0
            
            provider = SignatureProvider(
                tenant_id=tenant_id,
                provider_name=provider_data.provider_name,
                display_name=provider_data.display_name,
                encrypted_credentials=encrypted_creds,
                configuration=provider_data.configuration,
                is_active=provider_data.is_active,
                is_default=is_default
            )
            
            self.db.add(provider)
            await self.db.flush()  # Flush to get the provider ID
            
            # Crear registro de auditoría
            audit = SignatureProviderAudit(
                provider_id=provider.id,
                tenant_id=tenant_id,
                action='created',
                changed_by=created_by,
                changes={
                    'provider_name': provider_data.provider_name,
                    'display_name': provider_data.display_name,
                    'is_active': provider_data.is_active,
                    'is_default': is_default
                }
            )
            self.db.add(audit)
            
            await self.db.commit()
            await self.db.refresh(provider)
            
            logger.info(f"Created signature provider {provider.id} for tenant {tenant_id}")
            return provider
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating signature provider: {str(e)}")
            raise
    
    async def get_provider(self, provider_id: UUID, tenant_id: UUID) -> Optional[SignatureProvider]:
        """Obtener un proveedor"""
        stmt = select(SignatureProvider).filter(
            and_(
                SignatureProvider.id == provider_id,
                SignatureProvider.tenant_id == tenant_id
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_providers(self, tenant_id: UUID, is_active: bool = True) -> List[SignatureProvider]:
        """Obtener proveedores del tenant"""
        stmt = select(SignatureProvider).filter(
            SignatureProvider.tenant_id == tenant_id
        )
        
        if is_active is not None:
            stmt = stmt.filter(SignatureProvider.is_active == is_active)
        
        stmt = stmt.order_by(desc(SignatureProvider.is_default))
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_default_provider(self, tenant_id: UUID) -> Optional[SignatureProvider]:
        """Obtener proveedor por defecto"""
        stmt = select(SignatureProvider).filter(
            and_(
                SignatureProvider.tenant_id == tenant_id,
                SignatureProvider.is_active == True,
                SignatureProvider.is_default == True
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    # =====================================
    # SIGNATURE REQUEST MANAGEMENT
    # =====================================
    
    async def create_signature_request(
        self, 
        request_data: SignatureRequestCreate, 
        tenant_id: UUID, 
        user_id: UUID
    ) -> SignatureRequest:
        """Crear solicitud de firma"""
        try:
            # Obtener proveedor
            provider = await self.get_provider(request_data.provider_id, tenant_id)
            if not provider or not provider.is_active:
                raise ValueError("Invalid or inactive signature provider")
            
            # Load document content if document_id is provided
            document_content = None
            document_name = request_data.document_name
            
            if request_data.document_id:
                # Import here to avoid circular imports
                from app.db.models import Document
                
                # Load document
                stmt = select(Document).filter(
                    and_(
                        Document.id == request_data.document_id,
                        Document.tenant_id == tenant_id
                    )
                )
                result = await self.db.execute(stmt)
                document = result.scalar_one_or_none()
                
                if not document:
                    raise ValueError("Document not found")
                
                # Get document content from storage if not in database
                if document.file_path:
                    # Import storage service
                    from app.services.async_storage_service import AsyncStorageService
                    
                    try:
                        # Create storage service instance
                        storage_service = AsyncStorageService(self.db)
                        
                        # Download document from storage
                        content = await storage_service.download_file(
                            file_path=document.file_path,
                            tenant_id=tenant_id
                        )
                        document_content = content  # This should be bytes
                        document_name = document.filename
                        logger.info(f"Loaded document content from storage: {len(content)} bytes")
                    except Exception as e:
                        logger.error(f"Failed to load document from storage: {e}")
                        raise ValueError(f"Failed to load document content: {e}")
                else:
                    raise ValueError("Document has no file path")
            
            # Crear solicitud en base de datos
            signature_request = SignatureRequest(
                tenant_id=tenant_id,
                provider_id=request_data.provider_id,
                created_by=user_id,
                title=request_data.title,
                message=request_data.message,
                document_name=document_name,
                document_content=document_content,  # Now properly loaded
                document_url=request_data.document_url,
                signature_type=request_data.signature_type,
                callback_url=request_data.callback_url,
                success_url=request_data.success_url,
                error_url=request_data.error_url,
                request_metadata=request_data.request_metadata,
                status='draft'
            )
            
            self.db.add(signature_request)
            await self.db.flush()  # Para obtener el ID
            
            # Crear firmantes y guardar como contactos
            for i, signer_data in enumerate(request_data.signers):
                signer = SignatureRequestSigner(
                    request_id=signature_request.id,
                    name=signer_data.name,
                    email=signer_data.email,
                    phone=signer_data.phone,
                    order=signer_data.order if signer_data.order else i + 1,
                    authentication_method=signer_data.authentication_method,
                    success_url=signer_data.success_url,
                    error_url=signer_data.error_url
                )
                self.db.add(signer)
                
                # Save or update signer as contact
                await self._save_signer_as_contact(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    name=signer_data.name,
                    email=signer_data.email,
                    phone=signer_data.phone
                )
            
            # Crear evento inicial
            await self._create_event(
                signature_request.id, 
                'created', 
                'Signature request created',
                {"user_id": str(user_id)}
            )
            
            await self.db.commit()
            
            # Reload with relationships
            stmt = select(SignatureRequest).options(
                selectinload(SignatureRequest.signers)
            ).filter(
                SignatureRequest.id == signature_request.id
            )
            result = await self.db.execute(stmt)
            signature_request = result.scalar_one()
            
            logger.info(f"Created signature request {signature_request.id}")
            return signature_request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating signature request: {str(e)}")
            raise
    
    async def send_signature_request(self, request_id: UUID, tenant_id: UUID) -> bool:
        """Enviar solicitud de firma al proveedor"""
        try:
            # Obtener solicitud con relaciones cargadas
            stmt = select(SignatureRequest).options(
                selectinload(SignatureRequest.provider),
                selectinload(SignatureRequest.signers)
            ).filter(
                and_(
                    SignatureRequest.id == request_id,
                    SignatureRequest.tenant_id == tenant_id
                )
            )
            result = await self.db.execute(stmt)
            request = result.scalar_one_or_none()
            
            if not request:
                raise ValueError("Signature request not found")
            
            if request.status != 'draft':
                raise ValueError("Only draft requests can be sent")
            
            # Obtener proveedor y credenciales
            provider = request.provider
            credentials = self._decrypt_credentials(provider.encrypted_credentials)
            
            # Preparar datos para el proveedor
            signers_data = [
                {
                    "name": signer.name,
                    "email": signer.email,
                    "phone": signer.phone,
                    "order": signer.order,
                    "role": "signer",  # Default role
                    "authentication_method": signer.authentication_method
                }
                for signer in request.signers
            ]
            
            # Construir URL de webhook
            webhook_url = f"{settings.API_BASE_URL}/api/v1/signatures/webhooks/{provider.provider_name}"
            
            # Enviar al microservicio
            result = await signature_client.create_signature_request(
                provider_type=provider.provider_name,
                provider_credentials=credentials,
                title=request.title,
                document_content=request.document_content,
                document_name=request.document_name,
                signers=signers_data,
                message=request.message,
                expires_in_days=30,
                webhook_url=webhook_url,
                metadata=request.request_metadata
            )
            
            # Actualizar solicitud con datos del proveedor
            request.external_id = result.get("external_id")
            request.status = result.get("status", "sent")
            request.sent_at = datetime.now()
            
            # Actualizar firmantes
            for signer, signer_result in zip(request.signers, result.get("signers", [])):
                signer.external_id = signer_result.get("external_id")
                signer.signing_url = signer_result.get("signing_url")
                signer.status = signer_result.get("status", "sent")
            
            # Crear evento
            await self._create_event(
                request.id, 
                'sent', 
                'Signature request sent to provider',
                {"external_id": request.external_id, "provider": provider.provider_name}
            )
            
            await self.db.commit()
            
            logger.info(f"Sent signature request {request_id} to {provider.provider_name}")
            return True
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error sending signature request: {str(e)}")
            raise
    
    async def get_signature_request(
        self, 
        request_id: UUID, 
        tenant_id: UUID
    ) -> Optional[SignatureRequest]:
        """Obtener solicitud de firma"""
        stmt = select(SignatureRequest).options(
            selectinload(SignatureRequest.signers),
            selectinload(SignatureRequest.provider)
        ).filter(
            and_(
                SignatureRequest.id == request_id,
                SignatureRequest.tenant_id == tenant_id
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_signature_requests(
        self, 
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[SignatureRequest]:
        """Obtener solicitudes de firma"""
        stmt = select(SignatureRequest).options(
            selectinload(SignatureRequest.signers),
            selectinload(SignatureRequest.provider)
        ).filter(
            SignatureRequest.tenant_id == tenant_id
        )
        
        if user_id:
            stmt = stmt.filter(SignatureRequest.created_by == user_id)
        
        if status:
            stmt = stmt.filter(SignatureRequest.status == status)
        
        stmt = stmt.order_by(desc(SignatureRequest.created_at)).offset(offset).limit(limit)
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def update_signature_status(
        self, 
        request_id: UUID, 
        tenant_id: UUID
    ) -> Optional[SignatureRequest]:
        """Actualizar estado desde el proveedor"""
        try:
            request = await self.get_signature_request(request_id, tenant_id)
            if not request or not request.external_id:
                return None
            
            # Obtener estado del proveedor
            provider = request.provider
            credentials = self._decrypt_credentials(provider.encrypted_credentials)
            
            # Llamar al microservicio
            status_data = await signature_client.get_signature_status(
                provider_type=provider.provider_name,
                provider_credentials=credentials,
                external_id=request.external_id
            )
            
            # Actualizar estado si cambió
            new_status = status_data.get("status")
            if new_status and new_status != request.status:
                old_status = request.status
                request.status = new_status
                
                if new_status == 'completed':
                    request.completed_at = datetime.now()
                
                # Crear evento
                await self._create_event(
                    request.id,
                    'status_changed',
                    f'Status changed from {old_status} to {new_status}',
                    status_data
                )
                
                await self.db.commit()
            
            return request
            
        except Exception as e:
            logger.error(f"Error updating signature status: {str(e)}")
            return request
    
    # =====================================
    # WEBHOOK HANDLING
    # =====================================
    
    async def handle_webhook(
        self, 
        provider_name: str, 
        payload: Dict[str, Any], 
        signature: str,
        tenant_id: UUID
    ) -> bool:
        """Manejar webhook de proveedor"""
        try:
            # Verificar firma del webhook
            if not await self._verify_webhook_signature(provider_name, payload, signature, tenant_id):
                logger.warning(f"Invalid webhook signature from {provider_name}")
                return False
            
            # Procesar evento según el proveedor
            external_id = payload.get("external_id") or payload.get("envelope_id") or payload.get("id")
            if not external_id:
                logger.warning("No external_id found in webhook payload")
                return False
            
            # Buscar solicitud
            stmt = select(SignatureRequest).filter(
                and_(
                    SignatureRequest.external_id == external_id,
                    SignatureRequest.tenant_id == tenant_id
                )
            )
            result = await self.db.execute(stmt)
            request = result.scalar_one_or_none()
            
            if not request:
                logger.warning(f"Signature request not found for external_id: {external_id}")
                return False
            
            # Procesar evento
            event_type = payload.get("event_type") or payload.get("status")
            
            # Crear evento
            await self._create_event(
                request.id,
                f'webhook_{event_type}',
                f'Webhook received: {event_type}',
                payload
            )
            
            # Actualizar estado si es necesario
            if event_type in ['completed', 'declined', 'expired']:
                request.status = event_type
                if event_type == 'completed':
                    request.completed_at = datetime.now()
            
            await self.db.commit()
            
            logger.info(f"Processed webhook for request {request.id}")
            return True
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error handling webhook: {str(e)}")
            return False
    
    async def _verify_webhook_signature(
        self, 
        provider_name: str, 
        payload: Dict[str, Any], 
        signature: str,
        tenant_id: UUID
    ) -> bool:
        """Verificar firma HMAC del webhook"""
        try:
            # Obtener proveedor
            stmt = select(SignatureProvider).filter(
                and_(
                    SignatureProvider.tenant_id == tenant_id,
                    SignatureProvider.provider_name == provider_name
                )
            )
            result = await self.db.execute(stmt)
            provider = result.scalar_one_or_none()
            
            if not provider:
                return False
            
            # Desencriptar credenciales
            credentials = self._decrypt_credentials(provider.encrypted_credentials)
            webhook_secret = credentials.get("webhook_secret")
            
            if not webhook_secret:
                logger.warning(f"No webhook secret configured for {provider_name}")
                return True  # Permitir si no hay secret configurado
            
            # Verificar firma
            payload_string = json.dumps(payload, sort_keys=True, separators=(',', ':'))
            expected_signature = hmac.new(
                webhook_secret.encode(),
                payload_string.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {str(e)}")
            return False
    
    # =====================================
    # UTILITIES
    # =====================================
    
    async def _create_event(
        self, 
        request_id: UUID, 
        event_type: str, 
        description: str,
        event_data: Dict[str, Any]
    ):
        """Crear evento de auditoría"""
        event = SignatureEvent(
            request_id=request_id,
            event_type=event_type,
            description=description,
            event_data=event_data
        )
        self.db.add(event)
    
    async def download_signed_document(
        self, 
        request_id: UUID, 
        tenant_id: UUID
    ) -> Optional[bytes]:
        """Descargar documento firmado"""
        try:
            request = await self.get_signature_request(request_id, tenant_id)
            if not request or request.status != 'completed':
                return None
            
            provider = request.provider
            credentials = self._decrypt_credentials(provider.encrypted_credentials)
            
            # Llamar al microservicio
            return await signature_client.download_signed_document(
                provider_type=provider.provider_name,
                provider_credentials=credentials,
                external_id=request.external_id
            )
            
        except Exception as e:
            logger.error(f"Error downloading signed document: {str(e)}")
            return None
    
    async def update_provider(
        self,
        provider_id: UUID,
        provider_data: SignatureProviderCreate,
        tenant_id: UUID,
        updated_by: UUID
    ) -> Optional[SignatureProvider]:
        """Actualizar un proveedor de firma"""
        try:
            # Obtener el proveedor existente
            query = select(SignatureProvider).where(
                SignatureProvider.id == provider_id,
                SignatureProvider.tenant_id == tenant_id
            )
            result = await self.db.execute(query)
            provider = result.scalar_one_or_none()
            
            if not provider:
                return None
            
            # Guardar cambios para auditoría
            changes = {}
            if provider.display_name != provider_data.display_name:
                changes['display_name'] = {'old': provider.display_name, 'new': provider_data.display_name}
            if provider.is_active != provider_data.is_active:
                changes['is_active'] = {'old': provider.is_active, 'new': provider_data.is_active}
            if provider.is_default != provider_data.is_default:
                changes['is_default'] = {'old': provider.is_default, 'new': provider_data.is_default}
            if provider_data.credentials:
                changes['credentials'] = 'updated'
            
            # Actualizar campos
            provider.display_name = provider_data.display_name
            provider.is_active = provider_data.is_active
            provider.is_default = provider_data.is_default
            
            # Si se proporcionan nuevas credenciales, encriptarlas
            if provider_data.credentials:
                provider.encrypted_credentials = self._encrypt_credentials(provider_data.credentials)
            
            # Si se está estableciendo como predeterminado, desactivar otros
            if provider_data.is_default:
                await self._unset_other_defaults(tenant_id, provider_id)
            
            # Crear registro de auditoría
            if changes:
                audit = SignatureProviderAudit(
                    provider_id=provider_id,
                    tenant_id=tenant_id,
                    action='updated',
                    changed_by=updated_by,
                    changes=changes
                )
                self.db.add(audit)
            
            await self.db.commit()
            await self.db.refresh(provider)
            
            return provider
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating provider: {str(e)}")
            raise
    
    async def delete_provider(
        self,
        provider_id: UUID,
        tenant_id: UUID,
        deleted_by: UUID
    ) -> bool:
        """Eliminar un proveedor de firma"""
        try:
            # Verificar que el proveedor existe y pertenece al tenant
            query = select(SignatureProvider).where(
                SignatureProvider.id == provider_id,
                SignatureProvider.tenant_id == tenant_id
            )
            result = await self.db.execute(query)
            provider = result.scalar_one_or_none()
            
            if not provider:
                return False
            
            # Verificar que no haya solicitudes activas usando este proveedor
            active_requests_query = select(SignatureRequest).where(
                SignatureRequest.provider_id == provider_id,
                SignatureRequest.status.in_(['pending', 'sent'])
            )
            active_result = await self.db.execute(active_requests_query)
            if active_result.scalar_one_or_none():
                raise ValueError("Cannot delete provider with active signature requests")
            
            # Crear registro de auditoría antes de eliminar
            audit = SignatureProviderAudit(
                provider_id=provider_id,
                tenant_id=tenant_id,
                action='deleted',
                changed_by=deleted_by,
                changes={
                    'provider_name': provider.provider_name,
                    'display_name': provider.display_name
                }
            )
            self.db.add(audit)
            
            await self.db.delete(provider)
            await self.db.commit()
            
            return True
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting provider: {str(e)}")
            raise
    
    async def set_default_provider(
        self,
        provider_id: UUID,
        tenant_id: UUID,
        set_by: UUID
    ) -> Optional[SignatureProvider]:
        """Establecer un proveedor como predeterminado"""
        try:
            # Obtener el proveedor
            query = select(SignatureProvider).where(
                SignatureProvider.id == provider_id,
                SignatureProvider.tenant_id == tenant_id
            )
            result = await self.db.execute(query)
            provider = result.scalar_one_or_none()
            
            if not provider:
                return None
            
            # Desactivar todos los demás como predeterminados
            await self._unset_other_defaults(tenant_id, provider_id)
            
            # Establecer este como predeterminado
            provider.is_default = True
            provider.is_active = True  # Asegurar que esté activo
            
            # Crear registro de auditoría
            audit = SignatureProviderAudit(
                provider_id=provider_id,
                tenant_id=tenant_id,
                action='set_default',
                changed_by=set_by,
                changes={
                    'display_name': provider.display_name,
                    'previous_default': 'unset'  # Se registrará qué proveedor era el anterior
                }
            )
            self.db.add(audit)
            
            await self.db.commit()
            await self.db.refresh(provider)
            
            return provider
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error setting default provider: {str(e)}")
            raise
    
    async def _unset_other_defaults(self, tenant_id: UUID, except_provider_id: UUID):
        """Desactivar otros proveedores como predeterminados"""
        query = update(SignatureProvider).where(
            SignatureProvider.tenant_id == tenant_id,
            SignatureProvider.id != except_provider_id,
            SignatureProvider.is_default == True
        ).values(is_default=False)
        
        await self.db.execute(query)
    
    async def test_provider_connection(
        self,
        provider_id: UUID,
        tenant_id: UUID
    ) -> Dict[str, Any]:
        """Probar la conexión con un proveedor"""
        try:
            # Obtener el proveedor
            query = select(SignatureProvider).where(
                SignatureProvider.id == provider_id,
                SignatureProvider.tenant_id == tenant_id
            )
            result = await self.db.execute(query)
            provider = result.scalar_one_or_none()
            
            if not provider:
                raise ValueError("Provider not found")
            
            # Desencriptar credenciales
            credentials = self._decrypt_credentials(provider.encrypted_credentials)
            
            # Llamar al microservicio para probar la conexión
            return await signature_client.test_provider_connection(
                provider_type=provider.provider_name,
                provider_credentials=credentials
            )
                
        except Exception as e:
            logger.error(f"Error testing provider connection: {str(e)}")
            return {"success": False, "message": str(e)}
    
    # Provider test connection methods have been moved to the signature microservice
    
    
    
    async def update_request_status_by_external_id(
        self,
        external_id: str,
        status: str
    ):
        """Actualizar estado de solicitud por ID externo"""
        try:
            query = select(SignatureRequest).where(
                SignatureRequest.external_id == external_id
            )
            result = await self.db.execute(query)
            request = result.scalar_one_or_none()
            
            if request:
                request.status = status
                if status == 'completed':
                    request.completed_at = datetime.now()
                
                await self._create_event(
                    request.id,
                    'status_updated',
                    f'Status updated to {status} via webhook',
                    {'status': status}
                )
                
                await self.db.commit()
                
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating request status: {str(e)}")
    
    async def update_signer_status_by_external_id(
        self,
        external_id: str,
        status: str,
        signed_at: Optional[datetime] = None
    ):
        """Actualizar estado de firmante por ID externo"""
        try:
            query = select(SignatureRequestSigner).where(
                SignatureRequestSigner.external_id == external_id
            )
            result = await self.db.execute(query)
            signer = result.scalar_one_or_none()
            
            if signer:
                signer.status = status
                if signed_at:
                    signer.signed_at = signed_at
                
                # Crear evento
                request_query = select(SignatureRequest).where(
                    SignatureRequest.id == signer.request_id
                )
                request_result = await self.db.execute(request_query)
                request = request_result.scalar_one_or_none()
                
                if request:
                    await self._create_event(
                        request.id,
                        'signer_updated',
                        f'Signer {signer.email} status updated to {status}',
                        {'signer_id': str(signer.id), 'status': status}
                    )
                
                await self.db.commit()
                
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating signer status: {str(e)}")
    
    async def _save_signer_as_contact(
        self,
        tenant_id: UUID,
        user_id: UUID,
        name: str,
        email: str,
        phone: Optional[str] = None
    ):
        """Save or update a signer as a contact"""
        try:
            # Check if contact already exists
            query = select(SignatureContact).where(
                and_(
                    SignatureContact.tenant_id == tenant_id,
                    SignatureContact.email == email
                )
            )
            result = await self.db.execute(query)
            contact = result.scalar_one_or_none()
            
            if contact:
                # Update existing contact
                contact.usage_count += 1
                contact.last_used_at = datetime.now(timezone.utc)
                # Update name if different (in case of name changes)
                if contact.name != name:
                    contact.name = name
                # Update phone if provided and different
                if phone and contact.phone != phone:
                    contact.phone = phone
            else:
                # Create new contact
                contact = SignatureContact(
                    tenant_id=tenant_id,
                    created_by=user_id,
                    name=name,
                    email=email,
                    phone=phone,
                    usage_count=1,
                    last_used_at=datetime.now(timezone.utc)
                )
                self.db.add(contact)
                
        except Exception as e:
            logger.warning(f"Failed to save signer as contact: {str(e)}")
            # Don't fail the signature request if contact saving fails