"""
YouSign API v3 implementation
"""
import httpx
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import base64

from app.services.provider_strategies.base import SignatureProviderStrategy
from app.core.config import settings

logger = logging.getLogger(__name__)

class YouSignStrategy(SignatureProviderStrategy):
    """Implementation for YouSign API v3"""
    
    def _get_base_url(self, environment: str) -> str:
        """Get base URL based on environment"""
        if environment == 'production':
            return settings.YOUSIGN_PRODUCTION_URL
        return settings.YOUSIGN_SANDBOX_URL
    
    def _get_headers(self, api_key: str) -> Dict[str, str]:
        """Get headers for requests"""
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    async def create_signature_request(
        self, 
        credentials: Dict[str, Any], 
        request_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a signature request in YouSign"""
        try:
            api_key = credentials.get('api_key')
            environment = credentials.get('environment', 'sandbox')
            base_url = self._get_base_url(environment)
            
            # Decode document content from base64
            document_content = base64.b64decode(request_data.get('document_content'))
            
            async with httpx.AsyncClient() as client:
                # 1. Upload document
                document_id = await self._upload_document(
                    client, base_url, api_key, 
                    document_content,
                    request_data.get('document_name', 'document.pdf')
                )
                
                # 2. Create signature request
                signature_request_data = {
                    "name": request_data.get('title', 'Signature Request'),
                    "delivery_mode": "email",
                    "timezone": "Europe/Paris",
                    "documents": [document_id],
                    "signers": []
                }
                
                # Add custom message if provided
                if request_data.get('message'):
                    signature_request_data["custom_experience"] = {
                        "custom_thank_you_message": request_data['message']
                    }
                
                # Add signers
                for i, signer in enumerate(request_data.get('signers', [])):
                    signer_data = {
                        "info": {
                            "first_name": signer.get('name', '').split()[0] if signer.get('name') else 'Signer',
                            "last_name": ' '.join(signer.get('name', '').split()[1:]) if signer.get('name') and len(signer.get('name', '').split()) > 1 else f'{i+1}',
                            "email": signer['email'],
                            "phone_number": signer.get('phone', ''),
                            "locale": "en"
                        },
                        "signature_level": "electronic_signature",
                        "signature_authentication_mode": "no_otp",
                        "fields": [
                            {
                                "type": "signature",
                                "document_id": document_id,
                                "page": 1,
                                "x": 100 + (i * 200),
                                "y": 400,
                                "width": 150,
                                "height": 75
                            }
                        ]
                    }
                    
                    # Add name field if approver
                    if signer.get('role') == 'approver':
                        signer_data["fields"].append({
                            "type": "text",
                            "document_id": document_id,
                            "page": 1,
                            "x": 100 + (i * 200),
                            "y": 350,
                            "width": 150,
                            "height": 30,
                            "question": "Name"
                        })
                    
                    signature_request_data["signers"].append(signer_data)
                
                # Add webhook URL if provided
                if request_data.get('webhook_url'):
                    signature_request_data["webhooks"] = [{
                        "url": request_data['webhook_url'],
                        "event_types": [
                            "signature_request.done",
                            "signature_request.expired",
                            "signer.done"
                        ]
                    }]
                
                # Create the request
                response = await client.post(
                    f"{base_url}/signature_requests",
                    headers=self._get_headers(api_key),
                    json=signature_request_data
                )
                
                if response.status_code not in [200, 201]:
                    logger.error(f"YouSign API error: {response.status_code} - {response.text}")
                    raise Exception(f"Failed to create signature request: {response.text}")
                
                result = response.json()
                signature_request_id = result['id']
                
                # 3. Activate (send) the request
                activate_response = await client.post(
                    f"{base_url}/signature_requests/{signature_request_id}/activate",
                    headers=self._get_headers(api_key)
                )
                
                if activate_response.status_code not in [200, 201]:
                    logger.error(f"Failed to activate signature request: {activate_response.text}")
                
                # Get signing URLs for each signer
                signers_info = []
                for i, signer in enumerate(result.get('signers', [])):
                    signers_info.append({
                        "email": request_data['signers'][i]['email'],
                        "name": request_data['signers'][i]['name'],
                        "external_id": signer['id'],
                        "signing_url": signer.get('signature_link', ''),
                        "status": "sent"
                    })
                
                return {
                    "external_id": signature_request_id,
                    "status": "sent",
                    "signers": signers_info,
                    "expires_at": result.get('expiration_date')
                }
                
        except Exception as e:
            logger.error(f"Error creating YouSign signature request: {str(e)}")
            raise
    
    async def _upload_document(
        self, 
        client: httpx.AsyncClient, 
        base_url: str, 
        api_key: str, 
        document_content: bytes, 
        filename: str
    ) -> str:
        """Upload a document to YouSign"""
        try:
            # YouSign v3 requires multipart/form-data
            files = {'file': (filename, document_content, 'application/pdf')}
            
            response = await client.post(
                f"{base_url}/documents",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json"
                },
                files=files
            )
            
            if response.status_code not in [200, 201]:
                raise Exception(f"Failed to upload document: {response.text}")
            
            return response.json()['id']
            
        except Exception as e:
            logger.error(f"Error uploading document to YouSign: {str(e)}")
            raise
    
    async def get_signature_status(
        self, 
        credentials: Dict[str, Any], 
        external_id: str
    ) -> Dict[str, Any]:
        """Get the status of a signature request"""
        try:
            api_key = credentials.get('api_key')
            environment = credentials.get('environment', 'sandbox')
            base_url = self._get_base_url(environment)
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{base_url}/signature_requests/{external_id}",
                    headers=self._get_headers(api_key)
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to get signature status: {response.text}")
                    raise Exception(f"Failed to get signature status: {response.text}")
                
                result = response.json()
                
                # Map YouSign status to our system
                status_mapping = {
                    'draft': 'draft',
                    'ongoing': 'sent',
                    'done': 'completed',
                    'expired': 'expired',
                    'canceled': 'cancelled'
                }
                
                # Calculate completion percentage
                total_signers = len(result.get('signers', []))
                signed_count = sum(1 for s in result.get('signers', []) if s.get('status') == 'signed')
                completion_percentage = (signed_count / total_signers * 100) if total_signers > 0 else 0
                
                # Map signer information
                signers = []
                for signer in result.get('signers', []):
                    signers.append({
                        "email": signer.get('info', {}).get('email'),
                        "name": f"{signer.get('info', {}).get('first_name', '')} {signer.get('info', {}).get('last_name', '')}".strip(),
                        "external_id": signer.get('id'),
                        "status": signer.get('status'),
                        "signed_at": signer.get('signed_on')
                    })
                
                return {
                    "external_id": external_id,
                    "status": status_mapping.get(result.get('status'), 'sent'),
                    "completion_percentage": int(completion_percentage),
                    "signers": signers,
                    "completed_at": result.get('completed_at')
                }
                
        except Exception as e:
            logger.error(f"Error getting YouSign signature status: {str(e)}")
            raise
    
    async def cancel_signature_request(
        self, 
        credentials: Dict[str, Any], 
        external_id: str,
        reason: str = "Cancelled by user"
    ) -> bool:
        """Cancel a signature request"""
        try:
            api_key = credentials.get('api_key')
            environment = credentials.get('environment', 'sandbox')
            base_url = self._get_base_url(environment)
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{base_url}/signature_requests/{external_id}/cancel",
                    headers=self._get_headers(api_key),
                    json={"reason": reason}
                )
                
                return response.status_code in [200, 201, 204]
                
        except Exception as e:
            logger.error(f"Error cancelling YouSign signature request: {str(e)}")
            return False
    
    async def download_signed_document(
        self, 
        credentials: Dict[str, Any], 
        external_id: str
    ) -> bytes:
        """Download the signed document"""
        try:
            api_key = credentials.get('api_key')
            environment = credentials.get('environment', 'sandbox')
            base_url = self._get_base_url(environment)
            
            async with httpx.AsyncClient() as client:
                # Get signed documents
                response = await client.get(
                    f"{base_url}/signature_requests/{external_id}/documents/download",
                    headers=self._get_headers(api_key)
                )
                
                if response.status_code != 200:
                    raise Exception(f"Failed to download document: {response.text}")
                
                return response.content
                
        except Exception as e:
            logger.error(f"Error downloading YouSign document: {str(e)}")
            raise
    
    async def test_connection(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Test the connection with YouSign"""
        try:
            api_key = credentials.get('api_key')
            environment = credentials.get('environment', 'sandbox')
            base_url = self._get_base_url(environment)
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{base_url}/workspaces",
                    headers=self._get_headers(api_key),
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "message": "YouSign connection successful"
                    }
                elif response.status_code == 401:
                    return {
                        "success": False,
                        "message": "Invalid API key"
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Connection failed: HTTP {response.status_code}"
                    }
            
        except httpx.TimeoutException:
            return {"success": False, "message": "Connection timeout"}
        except Exception as e:
            return {"success": False, "message": str(e)}