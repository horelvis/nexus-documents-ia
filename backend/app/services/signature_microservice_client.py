"""
Client for Signature Microservice
"""
import httpx
import logging
import base64
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)

class SignatureMicroserviceClient:
    """Client to communicate with the signature microservice"""
    
    def __init__(self):
        self.base_url = "http://signature-service:8006/api/v1"
        self.headers = {
            "X-API-Key": settings.MICROSERVICES_API_KEY,
            "Content-Type": "application/json"
        }
        self.timeout = httpx.Timeout(30.0, connect=5.0)
    
    async def create_signature_request(
        self,
        provider_type: str,
        provider_credentials: Dict[str, Any],
        title: str,
        document_content: bytes,
        document_name: str,
        signers: List[Dict[str, Any]],
        message: Optional[str] = None,
        expires_in_days: int = 30,
        webhook_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a signature request via the microservice"""
        try:
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
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/requests/create",
                    json=request_data,
                    headers=self.headers,
                    timeout=self.timeout
                )
                
                if response.status_code != 200:
                    logger.error(f"Signature service error: {response.status_code} - {response.text}")
                    raise Exception(f"Failed to create signature request: {response.text}")
                
                return response.json()
                
        except httpx.TimeoutException:
            logger.error("Timeout calling signature service")
            raise Exception("Signature service timeout")
        except Exception as e:
            logger.error(f"Error calling signature service: {str(e)}")
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
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/requests/status",
                    json=request_data,
                    headers=self.headers,
                    timeout=self.timeout
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to get status: {response.text}")
                    raise Exception(f"Failed to get signature status: {response.text}")
                
                return response.json()
                
        except Exception as e:
            logger.error(f"Error getting signature status: {str(e)}")
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
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/requests/cancel",
                    json=request_data,
                    headers=self.headers,
                    timeout=self.timeout
                )
                
                return response.status_code == 200
                
        except Exception as e:
            logger.error(f"Error cancelling signature request: {str(e)}")
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
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/requests/download",
                    json=request_data,
                    headers=self.headers,
                    timeout=self.timeout
                )
                
                if response.status_code != 200:
                    raise Exception(f"Failed to download document: {response.text}")
                
                result = response.json()
                # Decode from base64
                return base64.b64decode(result['document'])
                
        except Exception as e:
            logger.error(f"Error downloading document: {str(e)}")
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
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/providers/test",
                    json=request_data,
                    headers=self.headers,
                    timeout=self.timeout
                )
                
                if response.status_code != 200:
                    return {
                        "success": False,
                        "message": f"Test failed: {response.text}"
                    }
                
                return response.json()
                
        except Exception as e:
            logger.error(f"Error testing provider: {str(e)}")
            return {
                "success": False,
                "message": str(e)
            }
    
    async def get_supported_providers(self) -> List[Dict[str, Any]]:
        """Get list of supported providers"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/providers/supported",
                    headers=self.headers,
                    timeout=self.timeout
                )
                
                if response.status_code != 200:
                    raise Exception(f"Failed to get providers: {response.text}")
                
                return response.json()
                
        except Exception as e:
            logger.error(f"Error getting supported providers: {str(e)}")
            raise

# Global client instance
signature_client = SignatureMicroserviceClient()