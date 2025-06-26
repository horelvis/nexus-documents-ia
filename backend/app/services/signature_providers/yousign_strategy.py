"""
YouSign signature provider implementation
"""
import httpx
import logging
from typing import Dict, Any, List
from datetime import datetime
import base64

from ..signature_service import SignatureProviderStrategy

logger = logging.getLogger(__name__)


class YouSignStrategy(SignatureProviderStrategy):
    """Implementación para YouSign API v3"""
    
    def __init__(self):
        self.base_url = "https://api.yousign.app/v3"
        self.sandbox_url = "https://api-sandbox.yousign.app/v3"
    
    def _get_headers(self, api_key: str) -> Dict[str, str]:
        """Get headers with API key for YouSign"""
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def _get_base_url(self, config: Dict[str, Any]) -> str:
        """Get base URL based on environment"""
        environment = config.get("environment", "sandbox")
        return self.sandbox_url if environment == "sandbox" else self.base_url
    
    def create_signature_request(
        self, 
        credentials: Dict[str, Any], 
        config: Dict[str, Any], 
        request_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a signature request in YouSign"""
        try:
            api_key = credentials.get("api_key")
            if not api_key:
                raise ValueError("API key not found in credentials")
            
            base_url = self._get_base_url(config)
            headers = self._get_headers(api_key)
            
            # Prepare signature request payload for YouSign v3
            payload = {
                "name": request_data.get("title", "Signature Request"),
                "delivery_mode": "email",
                "timezone": "Europe/Paris",
                "documents": []
            }
            
            # Add document
            if request_data.get("document_content"):
                # If we have base64 content, we need to upload it first
                document_response = self._upload_document(
                    base_url,
                    headers,
                    request_data.get("document_name", "document.pdf"),
                    request_data.get("document_content")
                )
                if document_response:
                    payload["documents"].append({
                        "id": document_response["id"],
                        "nature": "signable_document"
                    })
            elif request_data.get("document_url"):
                # For URL documents, YouSign may need different handling
                logger.warning("Document URL not yet supported for YouSign")
            
            # Add signers
            payload["signers"] = []
            for i, signer in enumerate(request_data.get("signers", [])):
                signer_data = {
                    "info": {
                        "first_name": signer.get("name", "").split()[0] if signer.get("name") else "Signer",
                        "last_name": " ".join(signer.get("name", "").split()[1:]) if signer.get("name") and len(signer.get("name", "").split()) > 1 else f"{i+1}",
                        "email": signer.get("email"),
                        "phone_number": signer.get("phone", ""),
                        "locale": "fr"
                    },
                    "signature_level": "electronic_signature",
                    "signature_authentication_mode": signer.get("authentication_method", "no_otp")
                }
                
                # Add custom success/error URLs if provided
                if signer.get("success_url"):
                    signer_data["redirect_urls"] = {
                        "success": signer.get("success_url"),
                        "error": signer.get("error_url", signer.get("success_url"))
                    }
                
                payload["signers"].append(signer_data)
            
            # Add webhook if callback URL is provided
            if request_data.get("callback_url"):
                payload["webhooks"] = [{
                    "url": request_data.get("callback_url"),
                    "headers": {},
                    "events": ["signature_request.done", "signature_request.expired"]
                }]
            
            # Make the API request
            logger.info(f"Creating YouSign signature request: {payload.get('name')}")
            
            with httpx.Client() as client:
                response = client.post(
                    f"{base_url}/signature_requests",
                    json=payload,
                    headers=headers,
                    timeout=30.0
                )
                
                if response.status_code not in [200, 201]:
                    logger.error(f"YouSign API error: {response.status_code} - {response.text}")
                    raise Exception(f"YouSign API error: {response.status_code} - {response.text}")
                
                result = response.json()
                
                # Activate the signature request
                activate_response = client.post(
                    f"{base_url}/signature_requests/{result['id']}/activate",
                    headers=headers
                )
                
                if activate_response.status_code not in [200, 201]:
                    logger.error(f"Failed to activate signature request: {activate_response.text}")
                
                # Format response
                return {
                    "external_id": result.get("id"),
                    "status": "sent",
                    "signers": [
                        {
                            "email": signer["info"]["email"],
                            "external_id": signer.get("id"),
                            "signing_url": signer.get("signature_link"),
                            "status": "sent"
                        }
                        for signer in result.get("signers", [])
                    ]
                }
                
        except Exception as e:
            logger.error(f"Error creating YouSign signature request: {str(e)}")
            raise
    
    def _upload_document(
        self, 
        base_url: str, 
        headers: Dict[str, str], 
        filename: str, 
        base64_content: str
    ) -> Dict[str, Any]:
        """Upload a document to YouSign"""
        try:
            # Decode base64 content
            document_bytes = base64.b64decode(base64_content)
            
            # YouSign v3 requires multipart upload
            files = {
                'file': (filename, document_bytes, 'application/pdf'),
                'nature': (None, 'signable_document')
            }
            
            # Remove Content-Type for multipart
            upload_headers = headers.copy()
            upload_headers.pop('Content-Type', None)
            
            with httpx.Client() as client:
                response = client.post(
                    f"{base_url}/documents",
                    files=files,
                    headers=upload_headers,
                    timeout=60.0
                )
                
                if response.status_code not in [200, 201]:
                    logger.error(f"Failed to upload document: {response.status_code} - {response.text}")
                    return None
                
                return response.json()
                
        except Exception as e:
            logger.error(f"Error uploading document to YouSign: {str(e)}")
            return None
    
    def get_signature_status(
        self, 
        credentials: Dict[str, Any], 
        external_id: str
    ) -> Dict[str, Any]:
        """Get signature request status from YouSign"""
        try:
            api_key = credentials.get("api_key")
            if not api_key:
                raise ValueError("API key not found in credentials")
            
            base_url = self._get_base_url(credentials)
            headers = self._get_headers(api_key)
            
            with httpx.Client() as client:
                response = client.get(
                    f"{base_url}/signature_requests/{external_id}",
                    headers=headers
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to get signature status: {response.status_code}")
                    return {"status": "error", "completion_percentage": 0}
                
                result = response.json()
                
                # Map YouSign status to our status
                status_map = {
                    "draft": "draft",
                    "ongoing": "in_progress",
                    "done": "completed",
                    "expired": "expired",
                    "canceled": "cancelled"
                }
                
                yousign_status = result.get("status", "draft")
                
                # Calculate completion percentage
                total_signers = len(result.get("signers", []))
                signed_count = sum(1 for s in result.get("signers", []) if s.get("status") == "signed")
                completion = int((signed_count / total_signers * 100) if total_signers > 0 else 0)
                
                return {
                    "status": status_map.get(yousign_status, "in_progress"),
                    "completion_percentage": completion,
                    "signers": [
                        {
                            "email": signer.get("info", {}).get("email"),
                            "status": signer.get("status"),
                            "signed_at": signer.get("signed_on")
                        }
                        for signer in result.get("signers", [])
                    ]
                }
                
        except Exception as e:
            logger.error(f"Error getting YouSign signature status: {str(e)}")
            return {"status": "error", "completion_percentage": 0}
    
    def cancel_signature_request(
        self, 
        credentials: Dict[str, Any], 
        external_id: str
    ) -> bool:
        """Cancel a signature request in YouSign"""
        try:
            api_key = credentials.get("api_key")
            if not api_key:
                raise ValueError("API key not found in credentials")
            
            base_url = self._get_base_url(credentials)
            headers = self._get_headers(api_key)
            
            with httpx.Client() as client:
                response = client.patch(
                    f"{base_url}/signature_requests/{external_id}/cancel",
                    headers=headers,
                    json={"reason": "Cancelled by user"}
                )
                
                return response.status_code in [200, 201, 204]
                
        except Exception as e:
            logger.error(f"Error cancelling YouSign signature request: {str(e)}")
            return False
    
    def download_signed_document(
        self, 
        credentials: Dict[str, Any], 
        external_id: str
    ) -> bytes:
        """Download signed document from YouSign"""
        try:
            api_key = credentials.get("api_key")
            if not api_key:
                raise ValueError("API key not found in credentials")
            
            base_url = self._get_base_url(credentials)
            headers = self._get_headers(api_key)
            
            # First get the signature request to find the document
            with httpx.Client() as client:
                # Get signature request details
                sr_response = client.get(
                    f"{base_url}/signature_requests/{external_id}",
                    headers=headers
                )
                
                if sr_response.status_code != 200:
                    logger.error(f"Failed to get signature request: {sr_response.status_code}")
                    return b""
                
                sr_data = sr_response.json()
                
                # Get the first document (assuming single document)
                if sr_data.get("documents"):
                    document_id = sr_data["documents"][0]["id"]
                    
                    # Download the signed document
                    doc_response = client.get(
                        f"{base_url}/signature_requests/{external_id}/documents/{document_id}/download",
                        headers=headers
                    )
                    
                    if doc_response.status_code == 200:
                        return doc_response.content
                    else:
                        logger.error(f"Failed to download document: {doc_response.status_code}")
                
                return b""
                
        except Exception as e:
            logger.error(f"Error downloading YouSign document: {str(e)}")
            return b""