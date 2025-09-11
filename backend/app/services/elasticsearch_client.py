"""
Elasticsearch Microservice Client
HTTP client for communicating with elasticsearch-service
"""
import httpx
import logging
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class ElasticsearchClient:
    """Client for Elasticsearch microservice operations"""

    def __init__(self):
        self.base_url = settings.ELASTICSEARCH_SERVICE_URL or "http://elasticsearch-service:8008"
        self.api_key = settings.MICROSERVICES_API_KEY
        self.timeout = 30.0

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to elasticsearch service"""
        url = f"{self.base_url}/api/v1/elasticsearch{endpoint}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.request(method, url, headers=headers, **kwargs)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Elasticsearch service error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Elasticsearch service request failed: {e}")
                raise

    async def index_document(
        self,
        tenant_id: str,
        doc_id: str,
        title: str,
        content: str,
        description: str = None,
        content_vector: List[float] = None,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """Index a document via microservice"""
        try:
            payload = {
                "doc_id": doc_id,
                "title": title,
                "content": content,
                "description": description,
                "content_vector": content_vector,
                "metadata": metadata
            }

            response = await self._make_request(
                "POST",
                f"/index/{tenant_id}",
                json=payload
            )

            return response.get("status") == "success"

        except Exception as e:
            logger.error(f"Failed to index document via microservice: {e}")
            return False

    async def hybrid_search(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
        filters: Dict[str, Any] = None,
        boost_semantic: float = 1.0,
        boost_keyword: float = 1.0
    ) -> List[Dict[str, Any]]:
        """Perform hybrid search via microservice"""
        try:
            payload = {
                "query": query,
                "limit": limit,
                "filters": filters,
                "boost_semantic": boost_semantic,
                "boost_keyword": boost_keyword
            }

            response = await self._make_request(
                "POST",
                f"/search/hybrid/{tenant_id}",
                json=payload
            )

            return response.get("results", [])

        except Exception as e:
            logger.error(f"Failed to perform hybrid search via microservice: {e}")
            return []

    async def semantic_search(
        self,
        tenant_id: str,
        query_vector: List[float],
        limit: int = 10,
        filters: Dict[str, Any] = None,
        min_score: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Perform semantic search via microservice"""
        try:
            payload = {
                "query_vector": query_vector,
                "limit": limit,
                "filters": filters,
                "min_score": min_score
            }

            response = await self._make_request(
                "POST",
                f"/search/semantic/{tenant_id}",
                json=payload
            )

            return response.get("results", [])

        except Exception as e:
            logger.error(f"Failed to perform semantic search via microservice: {e}")
            return []

    async def get_analytics(
        self,
        tenant_id: str,
        date_from: str = None,
        date_to: str = None
    ) -> Dict[str, Any]:
        """Get analytics via microservice"""
        try:
            payload = {
                "date_from": date_from,
                "date_to": date_to
            }

            response = await self._make_request(
                "POST",
                f"/analytics/{tenant_id}",
                json=payload
            )

            return response

        except Exception as e:
            logger.error(f"Failed to get analytics via microservice: {e}")
            return {}

    async def delete_document(self, tenant_id: str, doc_id: str) -> bool:
        """Delete document via microservice"""
        try:
            response = await self._make_request(
                "DELETE",
                f"/document/{tenant_id}/{doc_id}"
            )

            return response.get("status") == "success"

        except Exception as e:
            logger.error(f"Failed to delete document via microservice: {e}")
            return False

    async def create_index(self, tenant_id: str) -> bool:
        """Create index via microservice"""
        try:
            response = await self._make_request(
                "POST",
                f"/index/create/{tenant_id}"
            )

            return response.get("status") == "success"

        except Exception as e:
            logger.error(f"Failed to create index via microservice: {e}")
            return False


# Global client instance
elasticsearch_client = ElasticsearchClient()