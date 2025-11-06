"""
Client for Signature AI operations using Ollama directly
Migrated from LangChain microservice to direct integration
"""
import logging
import httpx
from typing import List, Dict, Any, Optional
from uuid import UUID

from app.core.config import settings

logger = logging.getLogger(__name__)


class SignatureAIClient:
    """Client for AI signature operations via direct Ollama integration"""
    
    def __init__(self):
        self.ollama_base_url = settings.OLLAMA_BASE_URL
        self.default_model = "llama3.2:latest"
        self.timeout = httpx.Timeout(30.0)
    
    async def analyze_document_content(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze document content using LangChain service
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/analyze/document",
                    json={
                        "content": content,
                        "metadata": metadata or {},
                        "analysis_type": "signature_placement"
                    }
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error analyzing document: {str(e)}")
            return {
                "document_type": "unknown",
                "confidence": 0.0,
                "error": str(e)
            }
    
    async def detect_signature_zones(
        self,
        content: str,
        document_type: str
    ) -> List[Dict[str, Any]]:
        """
        Detect signature zones using LangChain service
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/analyze/signature-zones",
                    json={
                        "content": content,
                        "document_type": document_type
                    }
                )
                response.raise_for_status()
                return response.json().get("zones", [])
        except Exception as e:
            logger.error(f"Error detecting signature zones: {str(e)}")
            return []
    
    async def get_similar_documents(
        self,
        tenant_id: str,
        document_embedding: List[float],
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find similar documents using vector search
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/vectors/search",
                    json={
                        "tenant_id": tenant_id,
                        "embedding": document_embedding,
                        "limit": limit,
                        "collection_name": "documents"
                    }
                )
                response.raise_for_status()
                return response.json().get("results", [])
        except Exception as e:
            logger.error(f"Error searching similar documents: {str(e)}")
            return []


# Singleton instance
signature_ai_client = SignatureAIClient()