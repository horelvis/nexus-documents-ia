"""
Compliance Checker Client - Interface to the Compliance Checker service
"""
import logging
import httpx
from typing import Dict, Any, List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class ComplianceCheckerClient:
    """Client for Compliance Checker service in LangGraph"""
    
    def __init__(self, http_client: httpx.AsyncClient, tenant_id: str = None, user_id: str = None):
        self.http_client = http_client
        self.base_url = settings.LANGGRAPH_SERVICE_URL
        self.tenant_id = tenant_id
        self.user_id = user_id
    
    def _get_auth_headers(self, tenant_id: str = None, user_id: str = None) -> dict:
        """Get authentication headers for microservice requests"""
        headers = {
            "X-API-Key": settings.MICROSERVICES_API_KEY,
            "X-Tenant-ID": tenant_id or self.tenant_id or settings.DEFAULT_TENANT
        }
        
        user_id_to_use = user_id or self.user_id
        if user_id_to_use:
            headers["X-User-ID"] = user_id_to_use
            
        return headers
    
    async def check_compliance(
        self,
        document_id: Optional[str] = None,
        content: Optional[str] = None,
        frameworks: List[str] = None,
        check_type: str = "full_audit",
        industry: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        custom_policies: Optional[List[str]] = None,
        tenant_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """Check document compliance"""
        
        if not document_id and not content:
            raise ValueError("Either document_id or content must be provided")
        
        try:
            payload = {
                "document_id": document_id,
                "content": content,
                "frameworks": frameworks or ["gdpr"],
                "check_type": check_type,
                "industry": industry,
                "jurisdiction": jurisdiction,
                "custom_policies": custom_policies
            }
            
            headers = self._get_auth_headers(tenant_id, user_id)
            
            response = await self.http_client.post(
                f"{self.base_url}/api/v1/compliance/check",
                json=payload,
                headers=headers,
                timeout=180.0  # Longer timeout for compliance checks
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error checking compliance: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error checking compliance: {str(e)}")
            raise
    
    async def check_file(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        frameworks: List[str] = None,
        check_type: str = "full_audit",
        industry: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        tenant_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """Check file compliance"""
        
        try:
            headers = self._get_auth_headers(tenant_id, user_id)
            
            files = {
                "file": (filename, file_content, content_type)
            }
            
            data = {
                "frameworks": ",".join(frameworks) if frameworks else "gdpr",
                "check_type": check_type,
                "industry": industry,
                "jurisdiction": jurisdiction
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/api/v1/compliance/check-file",
                files=files,
                data=data,
                headers=headers,
                timeout=180.0
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error checking file compliance: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error checking file compliance: {str(e)}")
            raise
    
    async def scan_sensitive_data(
        self,
        document_ids: List[str],
        deep_scan: bool = False,
        tenant_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """Scan documents for sensitive data"""
        
        try:
            headers = self._get_auth_headers(tenant_id, user_id)
            
            payload = {
                "document_ids": document_ids,
                "deep_scan": deep_scan
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/api/v1/compliance/scan-sensitive-data",
                json=payload,
                headers=headers,
                timeout=120.0
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error scanning sensitive data: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error scanning sensitive data: {str(e)}")
            raise
    
    async def create_data_mapping(
        self,
        document_ids: List[str],
        deep_scan: bool = False,
        tenant_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """Create data mapping and classification"""
        
        try:
            headers = self._get_auth_headers(tenant_id, user_id)
            
            payload = {
                "document_ids": document_ids,
                "deep_scan": deep_scan
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/api/v1/compliance/data-mapping",
                json=payload,
                headers=headers,
                timeout=180.0
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error creating data mapping: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error creating data mapping: {str(e)}")
            raise
    
    async def generate_report(
        self,
        document_ids: List[str],
        frameworks: List[str],
        include_remediation: bool = True,
        tenant_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """Generate compliance report"""
        
        try:
            headers = self._get_auth_headers(tenant_id, user_id)
            
            payload = {
                "document_ids": document_ids,
                "frameworks": frameworks,
                "include_remediation": include_remediation
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/api/v1/compliance/generate-report",
                json=payload,
                headers=headers,
                timeout=240.0  # Longer timeout for report generation
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error generating report: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error generating report: {str(e)}")
            raise
    
    async def create_custom_policy(
        self,
        name: str,
        description: str,
        rules: List[str],
        frameworks: List[str],
        tenant_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """Create custom compliance policy"""
        
        try:
            headers = self._get_auth_headers(tenant_id, user_id)
            
            payload = {
                "name": name,
                "description": description,
                "rules": rules,
                "frameworks": frameworks,
                "active": True
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/api/v1/compliance/policies",
                json=payload,
                headers=headers,
                timeout=30.0
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error creating policy: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error creating policy: {str(e)}")
            raise