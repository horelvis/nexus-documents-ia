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
        
        # Log request details for debugging
        payload_preview = "No payload"
        if "json" in kwargs:
            import json
            try:
                # Create a safe preview of the payload (truncate content)
                safe_payload = kwargs["json"].copy()
                if "content" in safe_payload:
                    safe_payload["content"] = safe_payload["content"][:50] + "..."
                if "content_vector" in safe_payload:
                    safe_payload["content_vector"] = "[VECTOR]"
                payload_preview = json.dumps(safe_payload)
            except:
                payload_preview = "Payload parsing error"
                
        logger.info(f"📡 ES Client Request: {method} {url} | Payload: {payload_preview}")

        headers = {
            "X-API-Key": self.api_key,
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
        logger.info(f"📝 Indexing document {doc_id} for tenant {tenant_id} via microservice")
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
        """Perform hybrid search via microservice with fallback to direct ES"""
        logger.info(f"🔍 Searching tenant {tenant_id} query='{query}' via microservice")
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
            logger.warning(f"Microservice unavailable, falling back to direct Elasticsearch: {e}")

            # Fallback to direct Elasticsearch search
            try:
                from elasticsearch import Elasticsearch
                from app.core.config import settings

                client = Elasticsearch([settings.ELASTICSEARCH_URL])

                # Enhanced search query with better matching
                search_body = {
                    "query": {
                        "bool": {
                            "should": [
                                # Exact match with boost
                                {
                                    "multi_match": {
                                        "query": query,
                                        "fields": ["title^3", "description^2", "content"],
                                        "type": "best_fields",
                                        "boost": 2
                                    }
                                },
                                # Wildcard match for partial matches (like propuesta in propuesta_signed.pdf)
                                {
                                    "wildcard": {
                                        "title": {
                                            "value": f"*{query}*",
                                            "boost": 1.5
                                        }
                                    }
                                },
                                {
                                    "wildcard": {
                                        "content": {
                                            "value": f"*{query}*",
                                            "boost": 1.0
                                        }
                                    }
                                }
                            ],
                            "minimum_should_match": 1,
                            "filter": {
                                "term": {"tenant_id": tenant_id}
                            }
                        }
                    },
                    "size": limit,
                    "sort": ["_score"]
                }

                # Format index name (replace hyphens with underscores)
                index_name = f"nexus_{tenant_id.replace('-', '_')}_documents"

                response = client.search(
                    index=index_name,
                    body=search_body
                )

                results = []
                for hit in response["hits"]["hits"]:
                    result = {
                        "document": {
                            "id": hit["_source"]["doc_id"],
                            "title": hit["_source"]["title"],
                            "content": hit["_source"]["content"][:500] + "..." if hit["_source"].get("content") else "",
                            "file_type": hit["_source"]["file_type"],
                            "category": hit["_source"].get("category"),
                            "tags": hit["_source"].get("tags", []),
                            "created_at": hit["_source"].get("created_at"),
                            "tenant_id": hit["_source"]["tenant_id"]
                        },
                        "score": hit["_score"],
                        "matches": [{"text": hit["_source"]["content"][:200] + "..." if hit["_source"].get("content") else "", "score": hit["_score"]}]
                    }
                    results.append(result)

                logger.info(f"✅ Direct Elasticsearch fallback returned {len(results)} results")
                return results

            except Exception as fallback_error:
                logger.error(f"❌ Direct Elasticsearch fallback also failed: {fallback_error}")
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

    async def get_facets(
        self,
        tenant_id: str,
        query: str = None,
        filters: Dict[str, Any] = None,
        facet_fields: List[str] = None,
        max_facet_values: int = 10
    ) -> Dict[str, Any]:
        """Get facets via microservice"""
        try:
            payload = {
                "query": query,
                "filters": filters,
                "facet_fields": facet_fields or ["file_type", "category", "tags"],
                "max_facet_values": max_facet_values
            }

            response = await self._make_request(
                "POST",
                f"/facets/{tenant_id}",
                json=payload
            )

            return response

        except Exception as e:
            logger.error(f"Failed to get facets via microservice: {e}")
            return {"facets": [], "total_documents": 0}

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

    async def get_document(self, tenant_id: str, doc_id: str) -> Dict[str, Any]:
        """Get a single document by ID via microservice"""
        try:
            response = await self._make_request(
                "GET",
                f"/document/{tenant_id}/{doc_id}"
            )

            return response

        except Exception as e:
            logger.error(f"Failed to get document via microservice: {e}")
            return {}


# Global client instance
elasticsearch_client = ElasticsearchClient()