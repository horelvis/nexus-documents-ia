"""
Contract Intelligence Client - Interface to the Contract Intelligence service
"""
import logging
import httpx
from typing import Dict, Any, List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class ContractIntelligenceClient:
    """Client for Contract Intelligence service in LangGraph"""
    
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
    
    async def analyze_contract(
        self,
        contract_id: Optional[str] = None,
        content: Optional[str] = None,
        analysis_type: str = "full_analysis",
        industry: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        party_perspective: Optional[str] = None,
        custom_concerns: Optional[List[str]] = None,
        tenant_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """Analyze a contract using CAG-based intelligence"""
        
        if not contract_id and not content:
            raise ValueError("Either contract_id or content must be provided")
        
        try:
            payload = {
                "contract_id": contract_id,
                "content": content,
                "analysis_type": analysis_type,
                "industry": industry,
                "jurisdiction": jurisdiction,
                "party_perspective": party_perspective,
                "custom_concerns": custom_concerns
            }
            
            headers = self._get_auth_headers(tenant_id, user_id)
            
            response = await self.http_client.post(
                f"{self.base_url}/api/v1/contracts/analyze",
                json=payload,
                headers=headers,
                timeout=120.0  # Longer timeout for contract analysis
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error analyzing contract: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error analyzing contract: {str(e)}")
            raise
    
    async def analyze_file(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        analysis_type: str = "full_analysis",
        industry: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        party_perspective: Optional[str] = None,
        tenant_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """Analyze a contract file"""
        
        try:
            headers = self._get_auth_headers(tenant_id, user_id)
            
            files = {
                "file": (filename, file_content, content_type)
            }
            
            data = {
                "analysis_type": analysis_type,
                "industry": industry,
                "jurisdiction": jurisdiction,
                "party_perspective": party_perspective
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/api/v1/contracts/analyze-file",
                files=files,
                data=data,
                headers=headers,
                timeout=120.0
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error analyzing contract file: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error analyzing contract file: {str(e)}")
            raise
    
    async def compare_contracts(
        self,
        contract_ids: List[str],
        comparison_type: str = "clause_comparison",
        focus_areas: Optional[List[str]] = None,
        tenant_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """Compare multiple contracts"""
        
        try:
            headers = self._get_auth_headers(tenant_id, user_id)
            
            payload = {
                "contract_ids": contract_ids,
                "comparison_type": comparison_type,
                "focus_areas": focus_areas
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/api/v1/contracts/compare",
                json=payload,
                headers=headers,
                timeout=180.0  # Longer timeout for comparison
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error comparing contracts: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error comparing contracts: {str(e)}")
            raise
    
    async def get_industry_templates(
        self,
        industry: str,
        tenant_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """Get industry-specific contract templates"""
        
        try:
            headers = self._get_auth_headers(tenant_id, user_id)
            
            response = await self.http_client.get(
                f"{self.base_url}/api/v1/contracts/templates/{industry}",
                headers=headers,
                timeout=30.0
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting templates: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting templates: {str(e)}")
            raise
    
    async def validate_contract(
        self,
        contract_id: str,
        validation_rules: Optional[List[str]] = None,
        tenant_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """Validate a contract against rules"""
        
        try:
            headers = self._get_auth_headers(tenant_id, user_id)
            
            params = {}
            if validation_rules:
                params["validation_rules"] = validation_rules
            
            response = await self.http_client.post(
                f"{self.base_url}/api/v1/contracts/validate",
                params={"contract_id": contract_id},
                json={"validation_rules": validation_rules} if validation_rules else {},
                headers=headers,
                timeout=60.0
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error validating contract: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error validating contract: {str(e)}")
            raise