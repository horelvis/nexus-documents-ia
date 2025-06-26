"""
Main signature service that coordinates provider strategies
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from app.services.provider_strategies.base import SignatureProviderStrategy
from app.services.provider_strategies.docusign import DocuSignStrategy
from app.services.provider_strategies.yousign import YouSignStrategy
from app.services.provider_strategies.signaturit import SignaturitStrategy
from app.models.schemas import ProviderType, SignatureStatus

logger = logging.getLogger(__name__)

class SignatureService:
    """Main service for handling signature operations"""
    
    def __init__(self):
        self.strategies: Dict[ProviderType, SignatureProviderStrategy] = {
            ProviderType.DOCUSIGN: DocuSignStrategy(),
            ProviderType.YOUSIGN: YouSignStrategy(),
            ProviderType.SIGNATURIT: SignaturitStrategy()
        }
    
    def _get_strategy(self, provider_type: ProviderType) -> SignatureProviderStrategy:
        """Get the appropriate strategy for the provider"""
        # Ensure provider_type is a ProviderType enum
        if isinstance(provider_type, str):
            try:
                provider_type = ProviderType(provider_type.lower())
            except ValueError:
                raise ValueError(f"Unsupported provider: {provider_type}")
        
        strategy = self.strategies.get(provider_type)
        if not strategy:
            raise ValueError(f"Unsupported provider: {provider_type}")
        return strategy
    
    async def create_signature_request(
        self,
        provider_type: ProviderType,
        credentials: Dict[str, Any],
        title: str,
        document_content: str,
        document_name: str,
        signers: list,
        message: Optional[str] = None,
        expires_in_days: int = 30,
        webhook_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a new signature request"""
        try:
            logger.info(f"Creating signature request with provider: {provider_type} (type: {type(provider_type)})")
            strategy = self._get_strategy(provider_type)
            
            # Prepare request data
            # Handle signers - they might be objects or dictionaries
            processed_signers = []
            for idx, s in enumerate(signers):
                if hasattr(s, 'email'):  # It's an object
                    signer_data = {
                        "email": s.email,
                        "name": s.name,
                        "phone": getattr(s, 'phone', None),
                        "role": s.role.value if hasattr(s, 'role') else "signer",
                        "order": getattr(s, 'order', idx + 1)
                    }
                else:  # It's a dictionary
                    signer_data = {
                        "email": s.get('email'),
                        "name": s.get('name'),
                        "phone": s.get('phone'),
                        "role": s.get('role', 'signer'),
                        "order": s.get('order', idx + 1)
                    }
                processed_signers.append(signer_data)
            
            request_data = {
                "title": title,
                "message": message,
                "document_content": document_content,
                "document_name": document_name,
                "signers": processed_signers,
                "expires_in_days": expires_in_days,
                "webhook_url": webhook_url,
                "metadata": metadata or {}
            }
            
            # Create request with provider
            result = await strategy.create_signature_request(credentials, request_data)
            
            # Add provider type to response
            result["provider_type"] = provider_type.value
            
            # Calculate expiration date
            if expires_in_days and not result.get("expires_at"):
                result["expires_at"] = (datetime.now() + timedelta(days=expires_in_days)).isoformat()
            
            logger.info(f"Created signature request with {provider_type}: {result.get('external_id')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error creating signature request: {str(e)}")
            raise
    
    async def get_signature_status(
        self,
        provider_type: ProviderType,
        credentials: Dict[str, Any],
        external_id: str
    ) -> Dict[str, Any]:
        """Get the status of a signature request"""
        try:
            strategy = self._get_strategy(provider_type)
            result = await strategy.get_signature_status(credentials, external_id)
            
            logger.info(f"Got status for {provider_type} request {external_id}: {result.get('status')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting signature status: {str(e)}")
            raise
    
    async def cancel_signature_request(
        self,
        provider_type: ProviderType,
        credentials: Dict[str, Any],
        external_id: str,
        reason: str = "Cancelled by user"
    ) -> bool:
        """Cancel a signature request"""
        try:
            strategy = self._get_strategy(provider_type)
            success = await strategy.cancel_signature_request(credentials, external_id, reason)
            
            if success:
                logger.info(f"Cancelled {provider_type} request {external_id}")
            else:
                logger.warning(f"Failed to cancel {provider_type} request {external_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error cancelling signature request: {str(e)}")
            return False
    
    async def download_signed_document(
        self,
        provider_type: ProviderType,
        credentials: Dict[str, Any],
        external_id: str
    ) -> bytes:
        """Download a signed document"""
        try:
            strategy = self._get_strategy(provider_type)
            document = await strategy.download_signed_document(credentials, external_id)
            
            logger.info(f"Downloaded document for {provider_type} request {external_id}")
            
            return document
            
        except Exception as e:
            logger.error(f"Error downloading signed document: {str(e)}")
            raise
    
    async def test_connection(
        self,
        provider_type: ProviderType,
        credentials: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Test connection to a provider"""
        try:
            strategy = self._get_strategy(provider_type)
            result = await strategy.test_connection(credentials)
            
            logger.info(f"Tested connection to {provider_type}: {result.get('success')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error testing connection: {str(e)}")
            return {
                "success": False,
                "message": f"Connection test failed: {str(e)}"
            }

# Global instance
signature_service = SignatureService()