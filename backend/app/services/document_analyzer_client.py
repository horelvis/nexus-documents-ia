"""
Document Analyzer Client - Interface to the Document Analyzer service
"""
import logging
import httpx
from typing import Dict, Any, List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class DocumentAnalyzerClient:
    """Client for Document Analyzer service in LangGraph"""
    
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
    
    async def analyze_document(
        self,
        document_id: Optional[str] = None,
        content: Optional[str] = None,
        analysis_type: str = "comprehensive",
        language: str = "auto",
        options: Optional[Dict[str, Any]] = None,
        tenant_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """Analyze a document using CAG-based analysis"""
        
        if not document_id and not content:
            raise ValueError("Either document_id or content must be provided")
        
        try:
            payload = {
                "document_id": document_id,
                "content": content,
                "analysis_type": analysis_type,
                "language": language,
                "options": options or {}
            }
            
            headers = self._get_auth_headers(tenant_id, user_id)
            
            response = await self.http_client.post(
                f"{self.base_url}/api/v1/analyzer/analyze",
                json=payload,
                headers=headers,
                timeout=60.0  # Longer timeout for analysis
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error analyzing document: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error analyzing document: {str(e)}")
            raise
    
    async def analyze_file(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        analysis_type: str = "comprehensive",
        tenant_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """Analyze a file"""
        
        try:
            headers = self._get_auth_headers(tenant_id, user_id)
            
            files = {
                "file": (filename, file_content, content_type)
            }
            
            data = {
                "analysis_type": analysis_type
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/api/v1/analyzer/analyze-file",
                files=files,
                data=data,
                headers=headers,
                timeout=90.0  # Longer timeout for file processing
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error analyzing file: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error analyzing file: {str(e)}")
            raise
    
    async def compare_documents(
        self,
        document_ids: List[str],
        comparison_type: str = "similarity",
        tenant_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """Compare multiple documents"""
        
        if len(document_ids) < 2:
            raise ValueError("At least 2 documents required for comparison")
        
        try:
            headers = self._get_auth_headers(tenant_id, user_id)
            
            params = {
                "document_ids": document_ids,
                "comparison_type": comparison_type
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/api/v1/analyzer/compare",
                params=params,
                headers=headers,
                timeout=120.0  # Longer timeout for comparison
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error comparing documents: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error comparing documents: {str(e)}")
            raise
    
    async def get_analysis_types(self) -> Dict[str, Any]:
        """Get available analysis types"""
        
        try:
            response = await self.http_client.get(
                f"{self.base_url}/api/v1/analyzer/analysis-types"
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting analysis types: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting analysis types: {str(e)}")
            raise