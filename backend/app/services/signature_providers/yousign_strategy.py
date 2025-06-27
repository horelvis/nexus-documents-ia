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
        """Create a signature request in YouSign following the correct flow"""
        try:
            api_key = credentials.get("api_key")
            if not api_key:
                raise ValueError("API key not found in credentials")
            
            base_url = self._get_base_url(config)
            headers = self._get_headers(api_key)
            
            with httpx.Client() as client:
                # Get metadata for language and timezone
                metadata = request_data.get("metadata", {})
                language = metadata.get("language", "en")
                timezone = metadata.get("timezone", "Europe/Paris")
                
                # Step 1: Create the signature request (initiate)
                signature_request_payload = {
                    "name": request_data.get("title", "Signature Request"),
                    "delivery_mode": "email",
                    "timezone": timezone
                }
                
                # Add custom message if provided
                if request_data.get("message"):
                    signature_request_payload["custom_experience"] = {
                        "custom_thank_you_message": request_data.get("message")
                    }
                
                logger.info(f"Step 1: Creating YouSign signature request: {signature_request_payload.get('name')}")
                
                sr_response = client.post(
                    f"{base_url}/signature_requests",
                    json=signature_request_payload,
                    headers=headers,
                    timeout=30.0
                )
                
                if sr_response.status_code not in [200, 201]:
                    logger.error(f"Failed to create signature request: {sr_response.status_code} - {sr_response.text}")
                    raise Exception(f"Failed to create signature request: {sr_response.status_code} - {sr_response.text}")
                
                signature_request = sr_response.json()
                signature_request_id = signature_request["id"]
                logger.info(f"Created signature request with ID: {signature_request_id}")
                
                # Step 2: Upload document
                document_id = None
                if request_data.get("document_content"):
                    logger.info("Step 2: Uploading document to signature request")
                    document_response = self._upload_document_v3(
                        client,
                        base_url,
                        headers,
                        signature_request_id,
                        request_data.get("document_name", "document.pdf"),
                        request_data.get("document_content")
                    )
                    if document_response:
                        document_id = document_response.get("id")
                        logger.info(f"Document uploaded with ID: {document_id}")
                    else:
                        raise Exception("Failed to upload document")
                
                # Step 3: Add signers one by one
                created_signers = []
                
                # Get signature fields from metadata (already retrieved above)
                signature_fields = metadata.get("signature_fields", [])
                logger.info(f"Found {len(signature_fields)} signature fields in metadata")
                if signature_fields:
                    logger.info(f"Signature fields details: {signature_fields}")
                
                # Get language from metadata or use default
                language = metadata.get("language", "en")
                # Map common language codes to YouSign locale format
                locale_map = {
                    "en": "en",
                    "es": "es",
                    "fr": "fr",
                    "de": "de",
                    "it": "it",
                    "pt": "pt",
                    "nl": "nl"
                }
                locale = locale_map.get(language, "en")
                logger.info(f"Using locale: {locale} for language: {language}")
                
                for i, signer in enumerate(request_data.get("signers", [])):
                    logger.info(f"Step 3.{i+1}: Adding signer {signer.get('email')}")
                    
                    # Parse name
                    name_parts = signer.get("name", "").split() if signer.get("name") else []
                    first_name = name_parts[0] if name_parts else "Signer"
                    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else f"{i+1}"
                    
                    # Get signer-specific language if provided
                    signer_language = signer.get("language", language)
                    signer_locale = locale_map.get(signer_language, locale)
                    
                    signer_payload = {
                        "info": {
                            "first_name": first_name,
                            "last_name": last_name,
                            "email": signer.get("email"),
                            "phone_number": signer.get("phone", ""),
                            "locale": signer_locale
                        },
                        "signature_level": "electronic_signature",
                        "signature_authentication_mode": "no_otp"
                    }
                    
                    # Add signature fields for this signer
                    if document_id:
                        signer_id = f"signer-{i}"
                        # Find all fields for this signer
                        signer_fields = [f for f in signature_fields if f.get("signer") == signer_id]
                        logger.info(f"Found {len(signer_fields)} fields for signer {signer_id}")
                        
                        if signer_fields:
                            # Use the actual field placements
                            signer_payload["fields"] = []
                            for field in signer_fields:
                                # Note: YouSign API uses standard PDF coordinates (origin at bottom-left)
                                # Frontend uses top-left origin, so we might need to convert
                                field_data = {
                                    "document_id": document_id,
                                    "type": "signature",
                                    "page": field.get("page", 1),
                                    "x": int(field.get("x", 77)),
                                    "y": int(field.get("y", 581)),
                                    "width": int(field.get("width", 200)),
                                    "height": int(field.get("height", 50))
                                }
                                logger.info(f"Adding field: page={field_data['page']}, x={field_data['x']}, y={field_data['y']}, width={field_data['width']}, height={field_data['height']}")
                                signer_payload["fields"].append(field_data)
                        else:
                            # Default fallback if no fields specified
                            signer_payload["fields"] = [{
                                "document_id": document_id,
                                "type": "signature",
                                "page": 1,
                                "x": 77,
                                "y": 581
                            }]
                    
                    signer_response = client.post(
                        f"{base_url}/signature_requests/{signature_request_id}/signers",
                        json=signer_payload,
                        headers=headers,
                        timeout=30.0
                    )
                    
                    if signer_response.status_code not in [200, 201]:
                        logger.error(f"Failed to add signer: {signer_response.status_code} - {signer_response.text}")
                        continue
                    
                    signer_result = signer_response.json()
                    created_signers.append({
                        "email": signer.get("email"),
                        "role": signer.get("role", "signer"),
                        "external_id": signer_result.get("id"),
                        "status": "pending"
                    })
                
                # Step 4: Activate the signature request
                logger.info("Step 4: Activating signature request")
                activate_response = client.post(
                    f"{base_url}/signature_requests/{signature_request_id}/activate",
                    headers=headers,
                    timeout=30.0
                )
                
                if activate_response.status_code not in [200, 201, 204]:
                    logger.error(f"Failed to activate signature request: {activate_response.status_code} - {activate_response.text}")
                    # Don't fail here, the request was created
                
                # Get the updated signature request with signing links
                final_response = client.get(
                    f"{base_url}/signature_requests/{signature_request_id}",
                    headers=headers
                )
                
                if final_response.status_code == 200:
                    final_data = final_response.json()
                    # Update signers with their signing URLs
                    for i, signer in enumerate(created_signers):
                        if i < len(final_data.get("signers", [])):
                            signer["signing_url"] = final_data["signers"][i].get("signature_link")
                            signer["status"] = "sent"
                
                # Format response
                return {
                    "external_id": signature_request_id,
                    "status": "sent",
                    "signers": created_signers
                }
                
        except Exception as e:
            logger.error(f"Error creating YouSign signature request: {str(e)}")
            raise
    
    def _upload_document_v3(
        self, 
        client: httpx.Client,
        base_url: str, 
        headers: Dict[str, str], 
        signature_request_id: str,
        filename: str, 
        base64_content: str
    ) -> Dict[str, Any]:
        """Upload a document to YouSign v3 for a specific signature request"""
        try:
            # Decode base64 content
            document_bytes = base64.b64decode(base64_content)
            
            # YouSign v3 requires multipart upload with specific fields
            files = {
                'file': (filename, document_bytes, 'application/pdf')
            }
            
            # Form data for the upload
            data = {
                'nature': 'signable_document',
                'parse_anchors': 'false'  # We're not using anchor-based positioning
            }
            
            # Remove Content-Type for multipart
            upload_headers = headers.copy()
            upload_headers.pop('Content-Type', None)
            
            response = client.post(
                f"{base_url}/signature_requests/{signature_request_id}/documents",
                files=files,
                data=data,
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