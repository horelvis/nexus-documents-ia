"""
Async Digital Signature Service with Multi-Provider Support
"""
import logging
import json
import hmac
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, func, desc, select
from sqlalchemy.orm import selectinload
from cryptography.fernet import Fernet

from app.db.models import (
    SignatureProvider, SignatureRequest, SignatureRequestSigner, 
    SignatureEvent, Tenant, User
)
from app.schemas.signature import (
    SignatureProviderCreate, SignatureProviderUpdate,
    SignatureRequestCreate, SignatureRequestUpdate,
    SignerCreate
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class SignatureProviderStrategy(ABC):
    """Estrategia base para proveedores de firma digital"""
    
    @abstractmethod
    async def create_signature_request(
        self, 
        credentials: Dict[str, Any], 
        config: Dict[str, Any], 
        request_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Crear solicitud de firma en el proveedor"""
        pass
    
    @abstractmethod
    async def get_signature_status(
        self, 
        credentials: Dict[str, Any], 
        external_id: str
    ) -> Dict[str, Any]:
        """Obtener estado de firma del proveedor"""
        pass
    
    @abstractmethod
    async def cancel_signature_request(
        self, 
        credentials: Dict[str, Any], 
        external_id: str
    ) -> bool:
        """Cancelar solicitud de firma"""
        pass
    
    @abstractmethod
    async def download_signed_document(
        self, 
        credentials: Dict[str, Any], 
        external_id: str
    ) -> bytes:
        """Descargar documento firmado"""
        pass


class DocuSignStrategy(SignatureProviderStrategy):
    """Implementación para DocuSign"""
    
    async def create_signature_request(self, credentials: Dict[str, Any], config: Dict[str, Any], request_data: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: Implementar integración real con DocuSign API
        logger.info("Creating DocuSign signature request")
        
        # Simulación de respuesta
        return {
            "external_id": f"docusign_{datetime.now().timestamp()}",
            "status": "sent",
            "signers": [
                {
                    "email": signer["email"],
                    "external_id": f"signer_{i}",
                    "signing_url": f"https://demo.docusign.net/signing/{i}",
                    "status": "sent"
                }
                for i, signer in enumerate(request_data.get("signers", []))
            ]
        }
    
    async def get_signature_status(self, credentials: Dict[str, Any], external_id: str) -> Dict[str, Any]:
        # TODO: Implementar consulta real a DocuSign
        return {"status": "in_progress", "completion_percentage": 50}
    
    async def cancel_signature_request(self, credentials: Dict[str, Any], external_id: str) -> bool:
        # TODO: Implementar cancelación real
        return True
    
    async def download_signed_document(self, credentials: Dict[str, Any], external_id: str) -> bytes:
        # TODO: Implementar descarga real
        return b"PDF content placeholder"


class YouSignStrategy(SignatureProviderStrategy):
    """Implementación para YouSign"""
    
    async def create_signature_request(self, credentials: Dict[str, Any], config: Dict[str, Any], request_data: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: Implementar integración real con YouSign API
        logger.info("Creating YouSign signature request")
        
        return {
            "external_id": f"yousign_{datetime.now().timestamp()}",
            "status": "sent",
            "signers": [
                {
                    "email": signer["email"],
                    "external_id": f"yousign_signer_{i}",
                    "signing_url": f"https://webapp.yousign.com/procedure/{i}",
                    "status": "sent"
                }
                for i, signer in enumerate(request_data.get("signers", []))
            ]
        }
    
    async def get_signature_status(self, credentials: Dict[str, Any], external_id: str) -> Dict[str, Any]:
        return {"status": "in_progress", "completion_percentage": 75}
    
    async def cancel_signature_request(self, credentials: Dict[str, Any], external_id: str) -> bool:
        return True
    
    async def download_signed_document(self, credentials: Dict[str, Any], external_id: str) -> bytes:
        return b"PDF content placeholder"


class SignaturitStrategy(SignatureProviderStrategy):
    """Implementación para Signaturit"""
    
    async def create_signature_request(self, credentials: Dict[str, Any], config: Dict[str, Any], request_data: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: Implementar integración real con Signaturit API
        logger.info("Creating Signaturit signature request")
        
        return {
            "external_id": f"signaturit_{datetime.now().timestamp()}",
            "status": "sent",
            "signers": [
                {
                    "email": signer["email"],
                    "external_id": f"signaturit_signer_{i}",
                    "signing_url": f"https://dashboard.signaturit.com/document/{i}",
                    "status": "sent"
                }
                for i, signer in enumerate(request_data.get("signers", []))
            ]
        }
    
    async def get_signature_status(self, credentials: Dict[str, Any], external_id: str) -> Dict[str, Any]:
        return {"status": "completed", "completion_percentage": 100}
    
    async def cancel_signature_request(self, credentials: Dict[str, Any], external_id: str) -> bool:
        return True
    
    async def download_signed_document(self, credentials: Dict[str, Any], external_id: str) -> bytes:
        return b"PDF content placeholder"


class AsyncSignatureService:
    """Async version of SignatureService"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.encryption_key = self._get_encryption_key()
        self.fernet = Fernet(self.encryption_key)
        
        # Estrategias disponibles
        self.strategies = {
            'docusign': DocuSignStrategy(),
            'yousign': YouSignStrategy(),
            'signaturit': SignaturitStrategy()
        }
    
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
        tenant_id: UUID
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
            
            # Crear solicitud en base de datos
            signature_request = SignatureRequest(
                tenant_id=tenant_id,
                provider_id=request_data.provider_id,
                created_by=user_id,
                title=request_data.title,
                message=request_data.message,
                document_name=request_data.document_name,
                document_content=request_data.document_content,
                document_url=request_data.document_url,
                signature_type=request_data.signature_type,
                callback_url=request_data.callback_url,
                success_url=request_data.success_url,
                error_url=request_data.error_url,
                request_metadata=request_data.metadata,
                status='draft'
            )
            
            self.db.add(signature_request)
            await self.db.flush()  # Para obtener el ID
            
            # Crear firmantes
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
            
            # Crear evento inicial
            await self._create_event(
                signature_request.id, 
                'created', 
                'Signature request created',
                {"user_id": str(user_id)}
            )
            
            await self.db.commit()
            await self.db.refresh(signature_request)
            
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
            
            # Obtener estrategia
            strategy = self.strategies.get(provider.provider_name)
            if not strategy:
                raise ValueError(f"Unsupported provider: {provider.provider_name}")
            
            # Preparar datos para el proveedor
            signers_data = [
                {
                    "name": signer.name,
                    "email": signer.email,
                    "phone": signer.phone,
                    "order": signer.order,
                    "authentication_method": signer.authentication_method
                }
                for signer in request.signers
            ]
            
            provider_request_data = {
                "title": request.title,
                "message": request.message,
                "document_name": request.document_name,
                "document_content": request.document_content,
                "document_url": request.document_url,
                "signature_type": request.signature_type,
                "callback_url": request.callback_url,
                "success_url": request.success_url,
                "error_url": request.error_url,
                "signers": signers_data,
                "metadata": request.request_metadata
            }
            
            # Enviar al proveedor
            result = await strategy.create_signature_request(
                credentials, 
                provider.configuration, 
                provider_request_data
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
        stmt = select(SignatureRequest).filter(
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
        stmt = select(SignatureRequest).filter(
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
            strategy = self.strategies.get(provider.provider_name)
            
            if not strategy:
                return request
            
            status_data = await strategy.get_signature_status(credentials, request.external_id)
            
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
            strategy = self.strategies.get(provider.provider_name)
            
            if not strategy:
                return None
            
            return await strategy.download_signed_document(credentials, request.external_id)
            
        except Exception as e:
            logger.error(f"Error downloading signed document: {str(e)}")
            return None