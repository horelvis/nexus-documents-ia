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
        """Create a signature request in YouSign following the correct v3 flow"""
        try:
            api_key = credentials.get('api_key')
            environment = credentials.get('environment', 'sandbox')
            base_url = self._get_base_url(environment)
            
            # Decode document content from base64
            document_content = base64.b64decode(request_data.get('document_content'))
            
            async with httpx.AsyncClient() as client:
                # Step 1: Create the signature request (initiate)
                logger.info(f"Step 1: Creating YouSign signature request")
                signature_request_payload = {
                    "name": request_data.get('title', 'Signature Request'),
                    "delivery_mode": "email",
                    "timezone": "Europe/Paris"
                }
                
                response = await client.post(
                    f"{base_url}/signature_requests",
                    headers=self._get_headers(api_key),
                    json=signature_request_payload
                )
                
                if response.status_code not in [200, 201]:
                    logger.error(f"Failed to create signature request: {response.status_code} - {response.text}")
                    raise Exception(f"Failed to create signature request: {response.text}")
                
                signature_request = response.json()
                signature_request_id = signature_request['id']
                logger.info(f"Created signature request with ID: {signature_request_id}")
                
                # Step 2: Upload document to the signature request
                logger.info(f"Step 2: Uploading document to signature request")
                document_id = await self._upload_document_to_request(
                    client, base_url, api_key,
                    signature_request_id,
                    document_content,
                    request_data.get('document_name', 'document.pdf')
                )
                
                # Step 3: Add signers one by one
                created_signers = []
                for i, signer in enumerate(request_data.get('signers', [])):
                    logger.info(f"Step 3.{i+1}: Adding signer {signer.get('email')}")
                    
                    # Parse name
                    name_parts = signer.get('name', '').split() if signer.get('name') else []
                    first_name = name_parts[0] if name_parts else 'Signer'
                    last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else f'{i+1}'
                    
                    signer_payload = {
                        "info": {
                            "first_name": first_name,
                            "last_name": last_name,
                            "email": signer['email'],
                            "phone_number": signer.get('phone', ''),
                            "locale": "fr"
                        },
                        "signature_level": "electronic_signature",
                        "signature_authentication_mode": "no_otp",
                        "fields": [
                            {
                                "document_id": document_id,
                                "type": "signature",
                                "page": 1,
                                "x": 77,  # Default position
                                "y": 581
                            }
                        ]
                    }
                    
                    signer_response = await client.post(
                        f"{base_url}/signature_requests/{signature_request_id}/signers",
                        headers=self._get_headers(api_key),
                        json=signer_payload
                    )
                    
                    if signer_response.status_code not in [200, 201]:
                        logger.error(f"Failed to add signer: {signer_response.status_code} - {signer_response.text}")
                        continue
                    
                    signer_result = signer_response.json()
                    created_signers.append({
                        "email": signer['email'],
                        "name": signer.get('name', ''),
                        "external_id": signer_result['id'],
                        "status": "pending"
                    })
                
                # Step 4: Activate the signature request
                logger.info(f"Step 4: Activating signature request")
                activate_response = await client.post(
                    f"{base_url}/signature_requests/{signature_request_id}/activate",
                    headers=self._get_headers(api_key)
                )
                
                if activate_response.status_code not in [200, 201, 204]:
                    logger.error(f"Failed to activate signature request: {activate_response.status_code} - {activate_response.text}")
                
                # Get the final signature request with signing links
                final_response = await client.get(
                    f"{base_url}/signature_requests/{signature_request_id}",
                    headers=self._get_headers(api_key)
                )
                
                if final_response.status_code == 200:
                    final_data = final_response.json()
                    # Update signers with their signing URLs
                    for i, signer in enumerate(created_signers):
                        if i < len(final_data.get('signers', [])):
                            signer["signing_url"] = final_data['signers'][i].get('signature_link', '')
                            signer["status"] = "sent"
                
                return {
                    "external_id": signature_request_id,
                    "status": "sent",
                    "signers": created_signers,
                    "expires_at": signature_request.get('expiration_date')
                }
                
        except Exception as e:
            logger.error(f"Error creating YouSign signature request: {str(e)}")
            raise
    
    async def _upload_document_to_request(
        self, 
        client: httpx.AsyncClient, 
        base_url: str, 
        api_key: str,
        signature_request_id: str,
        document_content: bytes, 
        filename: str
    ) -> str:
        """Upload a document to a specific YouSign signature request"""
        try:
            # YouSign v3 requires multipart/form-data
            files = {
                'file': (filename, document_content, 'application/pdf')
            }
            
            # Form data
            data = {
                'nature': 'signable_document',
                'parse_anchors': 'false'
            }
            
            # Headers without Content-Type (let httpx set it for multipart)
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json"
            }
            
            response = await client.post(
                f"{base_url}/signature_requests/{signature_request_id}/documents",
                headers=headers,
                files=files,
                data=data
            )
            
            if response.status_code not in [200, 201]:
                raise Exception(f"Failed to upload document: {response.text}")
            
            result = response.json()
            logger.info(f"Document uploaded with ID: {result['id']}")
            return result['id']
            
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