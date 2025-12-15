"""
Client for Signature Microservice
"""
import logging
import base64
from typing import Dict, Any, List, Optional

from app.core.config import settings
from app.clients.base import BaseHTTPClient
from app.clients.exceptions import HTTPClientError

logger = logging.getLogger(__name__)

class SignatureMicroserviceClient(BaseHTTPClient):
    """Client to communicate with the signature microservice"""
    
    def __init__(self):
        super().__init__(
            service_name="signature",
            base_url="http://signature-service:8006/api/v1",
            timeout_type="default",
        )
    
    async def create_signature_request(
        self,
        provider_type: str,
        provider_credentials: Dict[str, Any],
        title: str,
        document_content: Optional[bytes],
        document_name: str,
        signers: List[Dict[str, Any]],
        message: Optional[str] = None,
        expires_in_days: int = 30,
        webhook_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a signature request via the microservice"""
        try:
            # Check if document content is provided
            if document_content is None:
                raise ValueError("Document content is required but was not provided")
            
            # Encode document content to base64
            document_b64 = base64.b64encode(document_content).decode('utf-8')
            
            # Prepare request data
            request_data = {
                "provider_type": provider_type,
                "provider_credentials": provider_credentials,
                "title": title,
                "document_content": document_b64,
                "document_name": document_name,
                "signers": signers,
                "message": message,
                "expires_in_days": expires_in_days,
                "webhook_url": webhook_url,
                "metadata": metadata or {}
            }
            
            return await self.post_json("/requests/create", json=request_data)
        except HTTPClientError as exc:
            logger.error("Signature service upstream error: %s", exc)
            raise Exception(f"Signature service error: {exc.message}") from exc
        except Exception as exc:
            logger.error("Error calling signature service: %s", str(exc))
            raise
    
    async def get_signature_status(
        self,
        provider_type: str,
        provider_credentials: Dict[str, Any],
        external_id: str
    ) -> Dict[str, Any]:
        """Get signature request status"""
        try:
            request_data = {
                "provider_type": provider_type,
                "provider_credentials": provider_credentials,
                "external_id": external_id
            }
            
            return await self.post_json("/requests/status", json=request_data)
        except HTTPClientError as exc:
            logger.error("Error getting signature status: %s", exc)
            raise Exception(f"Failed to get signature status: {exc.message}") from exc
        except Exception as exc:
            logger.error("Error getting signature status: %s", str(exc))
            raise
    
    async def cancel_signature_request(
        self,
        provider_type: str,
        provider_credentials: Dict[str, Any],
        external_id: str,
        reason: str = "Cancelled by user"
    ) -> bool:
        """Cancel a signature request"""
        try:
            request_data = {
                "provider_type": provider_type,
                "provider_credentials": provider_credentials,
                "external_id": external_id,
                "reason": reason
            }
            
            response = await self.post("/requests/cancel", json=request_data)
            return response.status_code == 200
        except HTTPClientError as exc:
            logger.error("Error cancelling signature request: %s", exc)
            return False
        except Exception as exc:
            logger.error("Error cancelling signature request: %s", str(exc))
            return False
    
    async def download_signed_document(
        self,
        provider_type: str,
        provider_credentials: Dict[str, Any],
        external_id: str
    ) -> bytes:
        """Download signed document"""
        try:
            request_data = {
                "provider_type": provider_type,
                "provider_credentials": provider_credentials,
                "external_id": external_id
            }
            
            result = await self.post_json("/requests/download", json=request_data)
            return base64.b64decode(result["document"])
        except HTTPClientError as exc:
            logger.error("Error downloading document: %s", exc)
            raise Exception(f"Failed to download document: {exc.message}") from exc
        except Exception as exc:
            logger.error("Error downloading document: %s", str(exc))
            raise
    
    async def test_provider_connection(
        self,
        provider_type: str,
        provider_credentials: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Test provider connection"""
        try:
            request_data = {
                "provider_type": provider_type,
                "provider_credentials": provider_credentials
            }
            
            return await self.post_json("/providers/test", json=request_data)
        except HTTPClientError as exc:
            logger.error("Error testing provider: %s", exc)
            return {
                "success": False,
                "message": exc.message
            }
    
    async def get_supported_providers(self) -> List[Dict[str, Any]]:
        """Get list of supported providers"""
        try:
            response = await self.get("/providers/supported")
            return response.json()
        except HTTPClientError as exc:
            logger.error("Error getting supported providers: %s", exc)
            raise Exception(f"Failed to get providers: {exc.message}") from exc
        except Exception as exc:
            logger.error("Error getting supported providers: %s", str(exc))
            raise

# Global client instance
signature_client = SignatureMicroserviceClient()
