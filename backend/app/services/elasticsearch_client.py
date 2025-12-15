"""
Elasticsearch Microservice Client
HTTP client for communicating with elasticsearch-service

Supports ACL-based filtering for document-level access control.
"""
import logging
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.clients.base import BaseHTTPClient
from app.clients.exceptions import HTTPClientError

logger = logging.getLogger(__name__)


class SearchUserContext:
    """User context for ACL-filtered searches"""
    def __init__(self, user_id: str, role_ids: List[str] = None, is_admin: bool = False):
        self.user_id = user_id
        self.role_ids = role_ids or []
        self.is_admin = is_admin

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "role_ids": self.role_ids,
            "is_admin": self.is_admin
        }


class ElasticsearchClient(BaseHTTPClient):
    """Client for Elasticsearch microservice operations"""

    def __init__(self):
        super().__init__(
            service_name="elasticsearch",
            base_url=(settings.ELASTICSEARCH_SERVICE_URL or "http://elasticsearch-service:8008"),
            timeout_type="default",
        )

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
        try:
            response = await self.request(method, f"/api/v1/elasticsearch{endpoint}", **kwargs)
            return response.json()
        except HTTPClientError as exc:
            logger.error("Elasticsearch service error: %s", exc)
            raise
        except Exception as exc:
            logger.error("Elasticsearch service request failed: %s", exc)
            raise

    async def index_document(
        self,
        tenant_id: str,
        doc_id: str,
        title: str,
        content: str,
        description: str = None,
        content_vector: List[float] = None,
        metadata: Dict[str, Any] = None,
        # ACL fields
        created_by: str = None,
        acl_user_ids: List[str] = None,
        acl_role_ids: List[str] = None,
        acl_everyone: bool = False
    ) -> bool:
        """Index a document via microservice with ACL support"""
        logger.info(f"📝 Indexing document {doc_id} for tenant {tenant_id} via microservice")
        try:
            payload = {
                "doc_id": doc_id,
                "title": title,
                "content": content,
                "description": description,
                "content_vector": content_vector,
                "metadata": metadata,
                # ACL fields
                "created_by": created_by,
                "acl_user_ids": acl_user_ids or [],
                "acl_role_ids": acl_role_ids or [],
                "acl_everyone": acl_everyone
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
        boost_keyword: float = 1.0,
        # ACL context
        user_context: Optional[SearchUserContext] = None
    ) -> List[Dict[str, Any]]:
        """Perform hybrid search via microservice with ACL filtering"""
        logger.info(f"🔍 Searching tenant {tenant_id} query='{query}' via microservice")
        try:
            payload = {
                "query": query,
                "limit": limit,
                "filters": filters,
                "boost_semantic": boost_semantic,
                "boost_keyword": boost_keyword
            }

            # Add user context for ACL filtering if provided
            if user_context:
                payload["user_context"] = user_context.to_dict()
                logger.debug(f"🔐 Search with ACL: user={user_context.user_id}, admin={user_context.is_admin}")

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
        min_score: float = 0.7,
        # ACL context
        user_context: Optional[SearchUserContext] = None
    ) -> List[Dict[str, Any]]:
        """Perform semantic search via microservice with ACL filtering"""
        try:
            payload = {
                "query_vector": query_vector,
                "limit": limit,
                "filters": filters,
                "min_score": min_score
            }

            # Add user context for ACL filtering if provided
            if user_context:
                payload["user_context"] = user_context.to_dict()

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

    async def sync_document_acl(
        self,
        document_id: str,
        collection_name: str,
        acl_user_ids: List[str],
        acl_role_ids: List[str],
        acl_everyone: bool,
        created_by: str = None
    ) -> bool:
        """
        Synchronize document ACL to Elasticsearch.

        Called by DocumentACLService when document permissions change.
        This keeps Elasticsearch in sync with PostgreSQL (source of truth).

        Args:
            document_id: Document UUID
            collection_name: Elasticsearch index name (format: Nexus_{tenant_id}_documents)
            acl_user_ids: List of user UUIDs with view permission
            acl_role_ids: List of role UUIDs with view permission
            acl_everyone: Whether everyone in tenant has access
            created_by: Document owner UUID

        Returns:
            True if sync succeeded or document not found (not an error)
        """
        try:
            payload = {
                "collection_name": collection_name,
                "acl_user_ids": acl_user_ids,
                "acl_role_ids": acl_role_ids,
                "acl_everyone": acl_everyone,
                "created_by": created_by
            }

            response = await self._make_request(
                "PUT",
                f"/documents/{document_id}/acl",
                json=payload
            )

            status = response.get("status")
            if status == "success":
                logger.info(
                    f"✅ Synced ACL to Elasticsearch for document {document_id}: "
                    f"users={len(acl_user_ids)}, roles={len(acl_role_ids)}, everyone={acl_everyone}"
                )
                return True
            elif status == "not_found":
                logger.warning(f"Document {document_id} not found in Elasticsearch (may not be indexed yet)")
                return True  # Not an error - document may not be indexed yet
            else:
                logger.error(f"Unexpected response from Elasticsearch ACL sync: {response}")
                return False

        except Exception as e:
            logger.error(f"Failed to sync ACL to Elasticsearch: {e}")
            return False


# Global client instance
elasticsearch_client = ElasticsearchClient()
