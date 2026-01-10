"""
Elasticsearch Service for hybrid search and analytics
Microservice version - independent of main API
"""
import logging
import json
from typing import List, Dict, Any, Optional, Union
from elasticsearch import Elasticsearch, AsyncElasticsearch
from elasticsearch.exceptions import NotFoundError, RequestError

from app.core.config import settings

logger = logging.getLogger(__name__)


class ElasticsearchService:
    """Service for Elasticsearch hybrid search and analytics"""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.index_name = f"nexus_{tenant_id}_documents".lower().replace("-", "_")

        # Initialize both sync and async clients
        self.client = Elasticsearch([settings.ELASTICSEARCH_URL])
        self.async_client = AsyncElasticsearch([settings.ELASTICSEARCH_URL])

        logger.info(f"ElasticsearchService initialized for tenant: {tenant_id}")
        logger.info(f"Using index: {self.index_name}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def close(self):
        """Ensure HTTP connections are closed to avoid asyncio warnings."""
        try:
            if self.async_client:
                await self.async_client.close()
        finally:
            if self.client:
                self.client.close()

    def create_index_if_not_exists(self) -> bool:
        """
        Create index with optimized mapping for hybrid search
        """
        try:
            if self.client.indices.exists(index=self.index_name):
                logger.info(f"Index {self.index_name} already exists")
                return True

            # Optimized mapping for hybrid search
            mapping = {
                "mappings": {
                    "properties": {
                        "doc_id": {"type": "keyword"},
                        "title": {
                            "type": "text",
                            "analyzer": "filename_analyzer",
                            "fields": {
                                "keyword": {"type": "keyword"}
                            }
                        },
                        "content": {
                            "type": "text",
                            "analyzer": "content_analyzer"
                        },
                        "description": {
                            "type": "text",
                            "analyzer": "content_analyzer"
                        },
                        "content_vector": {
                            "type": "dense_vector",
                            "dims": 384,  # nomic-embed-text dimensions
                            "index": True,
                            "similarity": "cosine"
                        },
                        "file_type": {"type": "keyword"},
                        "category": {"type": "keyword"},
                        "tags": {"type": "keyword"},
                        "tenant_id": {"type": "keyword"},
                        "created_at": {"type": "date"},
                        "updated_at": {"type": "date"},
                        "file_size": {"type": "long"},
                        "metadata": {"type": "object"},
                        # ACL fields for document-level access control
                        "created_by": {"type": "keyword"},
                        "acl_user_ids": {"type": "keyword"},
                        "acl_role_ids": {"type": "keyword"},
                        "acl_everyone": {"type": "boolean"}
                    }
                },
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0,  # Single node setup
                    "index.mapping.total_fields.limit": 2000,
                    "analysis": {
                        "analyzer": {
                            "filename_analyzer": {
                                "type": "custom",
                                "tokenizer": "keyword",
                                "filter": ["lowercase", "filename_filter"]
                            },
                            "content_analyzer": {
                                "type": "custom",
                                "tokenizer": "standard",
                                "filter": ["lowercase", "stop"]
                            }
                        },
                        "filter": {
                            "filename_filter": {
                                "type": "pattern_replace",
                                "pattern": "[_.-]",
                                "replacement": " "
                            }
                        }
                    }
                }
            }

            self.client.indices.create(index=self.index_name, body=mapping)
            logger.info(f"✅ Created Elasticsearch index: {self.index_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to create index {self.index_name}: {e}")
            return False

    async def index_document(
        self,
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
        """
        Index a document for hybrid search with ACL support.

        ACL fields enable document-level access control:
        - created_by: Owner user ID (always has access)
        - acl_user_ids: List of user IDs with explicit access
        - acl_role_ids: List of role IDs with access
        - acl_everyone: If True, all tenant users have access
        """
        try:
            doc = {
                "doc_id": doc_id,
                "title": title,
                "content": content,
                "description": description or "",
                "tenant_id": self.tenant_id,
                "file_type": metadata.get("file_type", "unknown") if metadata else "unknown",
                "category": metadata.get("category") if metadata else None,
                "tags": metadata.get("tags", []) if metadata else [],
                "created_at": metadata.get("created_at") if metadata else None,
                "updated_at": metadata.get("updated_at") if metadata else None,
                "file_size": metadata.get("file_size") if metadata else None,
                "metadata": metadata or {},
                # ACL fields
                "created_by": created_by or "",
                "acl_user_ids": acl_user_ids or [],
                "acl_role_ids": acl_role_ids or [],
                "acl_everyone": acl_everyone
            }

            # Add vector if provided
            if content_vector:
                doc["content_vector"] = content_vector

            await self.async_client.index(
                index=self.index_name,
                id=doc_id,
                body=doc
            )

            logger.debug(f"✅ Indexed document {doc_id} in Elasticsearch (ACL: users={len(acl_user_ids or [])}, roles={len(acl_role_ids or [])}, everyone={acl_everyone})")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to index document {doc_id}: {e}")
            return False

    def _build_acl_filter(
        self,
        user_id: str,
        role_ids: List[str] = None,
        is_admin: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Build Elasticsearch filter clause for ACL-based access control.

        Access is granted if ANY of these conditions is true:
        1. User is admin (sees all documents in tenant)
        2. User is the document owner (created_by = user_id)
        3. User has explicit ACL (user_id in acl_user_ids)
        4. User has role-based ACL (any role_id in acl_role_ids)
        5. Document has 'everyone' ACL (acl_everyone = true)
        6. Document has no ACL configured (legacy/migration - created_by is empty)

        Returns:
            Filter clause dict or None if admin (no filtering needed beyond tenant)
        """
        if is_admin:
            # Admins see all documents in tenant
            return None

        should_clauses = [
            # User is the owner
            {"term": {"created_by": user_id}},
            # User has explicit ACL
            {"term": {"acl_user_ids": user_id}},
            # Everyone has access
            {"term": {"acl_everyone": True}},
            # Legacy documents without ACL (created_by is empty string)
            {"term": {"created_by": ""}}
        ]

        # Add role-based access if user has roles
        if role_ids:
            for role_id in role_ids:
                should_clauses.append({"term": {"acl_role_ids": role_id}})

        return {
            "bool": {
                "should": should_clauses,
                "minimum_should_match": 1
            }
        }

    async def hybrid_search(
        self,
        query: str,
        limit: int = 10,
        filters: Dict[str, Any] = None,
        boost_semantic: float = 1.0,
        boost_keyword: float = 1.0,
        # ACL parameters
        user_id: str = None,
        role_ids: List[str] = None,
        is_admin: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining keyword and semantic search with ACL filtering.

        If user_id is provided, results are filtered based on document-level ACL.
        If user_id is None (backward compatibility), no ACL filtering is applied.
        """
        try:
            # Build the search query
            must_clauses = []

            # Keyword search with wildcard support
            if query:
                # Check if query contains wildcards
                if '*' in query or '?' in query:
                    # Use wildcard query for patterns with * or ?
                    must_clauses.append({
                        "bool": {
                            "should": [
                                {
                                    "wildcard": {
                                        "title": {
                                            "value": query.lower(),
                                            "boost": boost_keyword * 2
                                        }
                                    }
                                },
                                {
                                    "wildcard": {
                                        "description": {
                                            "value": query.lower(),
                                            "boost": boost_keyword * 1.5
                                        }
                                    }
                                },
                                {
                                    "wildcard": {
                                        "content": {
                                            "value": query.lower(),
                                            "boost": boost_keyword
                                        }
                                    }
                                }
                            ],
                            "minimum_should_match": 1
                        }
                    })
                else:
                    # Use normal multi_match for regular queries
                    must_clauses.append({
                        "multi_match": {
                            "query": query,
                            "fields": ["title^2", "description^1.5", "content"],
                            "type": "best_fields",
                            "boost": boost_keyword
                        }
                    })

            # Add filters - always filter by tenant
            filter_clauses = [{"term": {"tenant_id": self.tenant_id}}]

            # Add ACL filter if user context is provided
            if user_id:
                acl_filter = self._build_acl_filter(user_id, role_ids, is_admin)
                if acl_filter:
                    filter_clauses.append(acl_filter)
                logger.debug(f"🔐 ACL filter applied: user={user_id}, roles={role_ids}, admin={is_admin}")

            if filters:
                if filters.get("file_type"):
                    filter_clauses.append({"term": {"file_type": filters["file_type"]}})
                if filters.get("category"):
                    filter_clauses.append({"term": {"category": filters["category"]}})
                if filters.get("tags"):
                    filter_clauses.append({"terms": {"tags": filters["tags"]}})
                if filters.get("date_from") or filters.get("date_to"):
                    date_filter = {"range": {"created_at": {}}}
                    if filters.get("date_from"):
                        date_filter["range"]["created_at"]["gte"] = filters["date_from"]
                    if filters.get("date_to"):
                        date_filter["range"]["created_at"]["lte"] = filters["date_to"]
                    filter_clauses.append(date_filter)
                # File Size Filter
                if filters.get("file_size_min") is not None or filters.get("file_size_max") is not None:
                    size_filter = {"range": {"file_size": {}}}
                    if filters.get("file_size_min") is not None:
                        size_filter["range"]["file_size"]["gte"] = filters["file_size_min"]
                    if filters.get("file_size_max") is not None:
                        size_filter["range"]["file_size"]["lte"] = filters["file_size_max"]
                    filter_clauses.append(size_filter)

            search_body = {
                "query": {
                    "bool": {
                        "must": must_clauses,
                        "filter": filter_clauses
                    }
                },
                "size": limit,
                "sort": ["_score"],
                "_source": {
                    "excludes": ["content_vector"]  # Don't return vectors
                },
                "highlight": {
                    "fields": {
                        "content": {"fragment_size": 150, "number_of_fragments": 3},
                        "title": {"number_of_fragments": 0},
                        "description": {"number_of_fragments": 0}
                    },
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"]
                }
            }

            response = await self.async_client.search(
                index=self.index_name,
                body=search_body
            )

            results = []
            for hit in response["hits"]["hits"]:
                # Extract highlights
                highlights = hit.get("highlight", {})
                
                # Prepare matches from content highlights or fallback to start of content
                matches = []
                if "content" in highlights:
                    for fragment in highlights["content"]:
                        matches.append({"text": fragment, "score": hit["_score"]})
                else:
                    matches.append({"text": hit["_source"]["content"][:200] + "...", "score": hit["_score"]})

                result = {
                    "document": {
                        "id": hit["_source"]["doc_id"],
                        "title": hit["_source"]["title"],
                        "content": hit["_source"]["content"][:500] + "...",  # Truncate
                        "file_type": hit["_source"]["file_type"],
                        "category": hit["_source"].get("category"),
                        "tags": hit["_source"].get("tags", []),
                        "created_at": hit["_source"].get("created_at"),
                        "tenant_id": hit["_source"]["tenant_id"]
                    },
                    "score": hit["_score"],
                    "matches": matches,
                    "highlights": highlights # Return full highlights for frontend flexibility
                }
                results.append(result)

            logger.info(f"✅ Hybrid search returned {len(results)} results")
            return results

        except NotFoundError:
            logger.info(f"ℹ️ Index {self.index_name} not found (no documents yet). Returning empty results.")
            return []
        except Exception as e:
            logger.error(f"❌ Hybrid search failed: {e}")
            return []

    async def semantic_search_with_vector(
        self,
        query_vector: List[float],
        limit: int = 10,
        filters: Dict[str, Any] = None,
        min_score: float = 0.7,
        # ACL parameters
        user_id: str = None,
        role_ids: List[str] = None,
        is_admin: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search using vector similarity with ACL filtering.

        If user_id is provided, results are filtered based on document-level ACL.
        """
        try:
            # Build filter clauses
            filter_clauses = [{"term": {"tenant_id": self.tenant_id}}]

            # Add ACL filter if user context is provided
            if user_id:
                acl_filter = self._build_acl_filter(user_id, role_ids, is_admin)
                if acl_filter:
                    filter_clauses.append(acl_filter)
                logger.debug(f"🔐 ACL filter applied to semantic search: user={user_id}")

            if filters:
                if filters.get("file_type"):
                    filter_clauses.append({"term": {"file_type": filters["file_type"]}})
                if filters.get("tags"):
                    filter_clauses.append({"terms": {"tags": filters["tags"]}})

            search_body = {
                "query": {
                    "script_score": {
                        "query": {
                            "bool": {
                                "filter": filter_clauses
                            }
                        },
                        "script": {
                            "source": "cosineSimilarity(params.query_vector, 'content_vector') + 1.0",
                            "params": {"query_vector": query_vector}
                        }
                    }
                },
                "size": limit,
                "min_score": min_score,
                "_source": {
                    "excludes": ["content_vector"]
                }
            }

            response = await self.async_client.search(
                index=self.index_name,
                body=search_body
            )

            results = []
            for hit in response["hits"]["hits"]:
                result = {
                    "document": hit["_source"],
                    "score": hit["_score"],
                    "matches": [{"text": hit["_source"]["content"][:200] + "...", "score": hit["_score"]}]
                }
                results.append(result)

            return results

        except NotFoundError:
            return []
        except Exception as e:
            logger.error(f"❌ Semantic search failed: {e}")
            return []

    async def get_facets(
        self,
        query: str = None,
        filters: Dict[str, Any] = None,
        facet_fields: List[str] = None,
        max_facet_values: int = 10,
        # ACL parameters
        user_id: str = None,
        role_ids: List[str] = None,
        is_admin: bool = False
    ) -> Dict[str, Any]:
        """
        Get facets for search results with optional query and filters.

        SECURITY: If user_id is provided, facets are filtered by ACL.
        Only documents the user can access are counted in facet aggregations.
        """
        try:
            # Build base query
            must_clauses = []
            filter_clauses = [{"term": {"tenant_id": self.tenant_id}}]

            # Add ACL filter if user context is provided
            if user_id:
                acl_filter = self._build_acl_filter(user_id, role_ids, is_admin)
                if acl_filter:
                    filter_clauses.append(acl_filter)
                logger.debug(f"🔐 ACL filter applied to facets: user={user_id}, roles={role_ids}, admin={is_admin}")

            # Add search query if provided
            if query:
                must_clauses.append({
                    "multi_match": {
                        "query": query,
                        "fields": ["title^2", "description^1.5", "content"],
                        "type": "best_fields"
                    }
                })

            # Add filters
            if filters:
                if filters.get("file_type"):
                    filter_clauses.append({"term": {"file_type": filters["file_type"]}})
                if filters.get("category"):
                    filter_clauses.append({"term": {"category": filters["category"]}})
                if filters.get("tags"):
                    filter_clauses.append({"terms": {"tags": filters["tags"]}})
                if filters.get("date_from") or filters.get("date_to"):
                    date_filter = {"range": {"created_at": {}}}
                    if filters.get("date_from"):
                        date_filter["range"]["created_at"]["gte"] = filters["date_from"]
                    if filters.get("date_to"):
                        date_filter["range"]["created_at"]["lte"] = filters["date_to"]
                    filter_clauses.append(date_filter)
                # File Size Filter
                if filters.get("file_size_min") is not None or filters.get("file_size_max") is not None:
                    size_filter = {"range": {"file_size": {}}}
                    if filters.get("file_size_min") is not None:
                        size_filter["range"]["file_size"]["gte"] = filters["file_size_min"]
                    if filters.get("file_size_max") is not None:
                        size_filter["range"]["file_size"]["lte"] = filters["file_size_max"]
                    filter_clauses.append(size_filter)

            # Default facet fields if not specified
            if not facet_fields:
                facet_fields = ["file_type", "category", "tags"]

            # Build aggregations
            aggs = {}
            for field in facet_fields:
                if field == "tags":
                    aggs[f"facet_{field}"] = {
                        "terms": {
                            "field": field,
                            "size": max_facet_values
                        }
                    }
                else:
                    aggs[f"facet_{field}"] = {
                        "terms": {
                            "field": field,
                            "size": max_facet_values
                        }
                    }

            # Add total count aggregation
            aggs["total_count"] = {"value_count": {"field": "doc_id"}}

            search_body = {
                "query": {
                    "bool": {
                        "must": must_clauses,
                        "filter": filter_clauses
                    }
                },
                "size": 0,
                "aggs": aggs
            }

            response = await self.async_client.search(
                index=self.index_name,
                body=search_body
            )

            # Process facet results
            facets = []
            for field in facet_fields:
                agg_key = f"facet_{field}"
                if agg_key in response["aggregations"]:
                    buckets = []
                    for bucket in response["aggregations"][agg_key]["buckets"]:
                        buckets.append({
                            "key": bucket["key"],
                            "count": bucket["doc_count"],
                            "selected": False  # Will be set by frontend based on current filters
                        })

                    facets.append({
                        "field": field,
                        "buckets": buckets,
                        "total_count": len(buckets)
                    })

            return {
                "facets": facets,
                "total_documents": response["aggregations"]["total_count"]["value"]
            }

        except Exception as e:
            logger.error(f"❌ Facets query failed: {e}")
            return {"facets": [], "total_documents": 0}

    async def get_analytics(
        self,
        date_from: str = None,
        date_to: str = None,
        # ACL parameters
        user_id: str = None,
        role_ids: List[str] = None,
        is_admin: bool = False
    ) -> Dict[str, Any]:
        """
        Get search and document analytics.

        SECURITY: If user_id is provided, analytics are filtered by ACL.
        Only documents the user can access are counted in analytics.
        """
        try:
            # Build filter clauses
            filter_clauses = [{"term": {"tenant_id": self.tenant_id}}]

            # Add ACL filter if user context is provided
            if user_id:
                acl_filter = self._build_acl_filter(user_id, role_ids, is_admin)
                if acl_filter:
                    filter_clauses.append(acl_filter)
                logger.debug(f"🔐 ACL filter applied to analytics: user={user_id}, roles={role_ids}, admin={is_admin}")

            # Build date filter
            if date_from or date_to:
                date_filter = {"range": {"created_at": {}}}
                if date_from:
                    date_filter["range"]["created_at"]["gte"] = date_from
                if date_to:
                    date_filter["range"]["created_at"]["lte"] = date_to
                filter_clauses.append(date_filter)

            # Aggregation query
            agg_body = {
                "query": {
                    "bool": {
                        "filter": filter_clauses
                    }
                },
                "size": 0,
                "aggs": {
                    "total_documents": {"value_count": {"field": "doc_id"}},
                    "by_file_type": {"terms": {"field": "file_type"}},
                    "by_category": {"terms": {"field": "category"}},
                    "by_tags": {"terms": {"field": "tags", "size": 20}},
                    "documents_over_time": {
                        "date_histogram": {
                            "field": "created_at",
                            "calendar_interval": "day"
                        }
                    }
                }
            }

            response = await self.async_client.search(
                index=self.index_name,
                body=agg_body
            )

            analytics = {
                "total_documents": response["aggregations"]["total_documents"]["value"],
                "by_file_type": [
                    {"key": bucket["key"], "count": bucket["doc_count"]}
                    for bucket in response["aggregations"]["by_file_type"]["buckets"]
                ],
                "by_category": [
                    {"key": bucket["key"], "count": bucket["doc_count"]}
                    for bucket in response["aggregations"]["by_category"]["buckets"]
                ],
                "popular_tags": [
                    {"tag": bucket["key"], "count": bucket["doc_count"]}
                    for bucket in response["aggregations"]["by_tags"]["buckets"]
                ],
                "documents_timeline": [
                    {"date": bucket["key_as_string"], "count": bucket["doc_count"]}
                    for bucket in response["aggregations"]["documents_over_time"]["buckets"]
                ]
            }

            return analytics

        except Exception as e:
            logger.error(f"❌ Analytics query failed: {e}")
            return {}

    async def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document from the index
        """
        try:
            await self.async_client.delete(index=self.index_name, id=doc_id)
            logger.info(f"✅ Deleted document {doc_id} from Elasticsearch")
            return True
        except NotFoundError:
            logger.warning(f"Document {doc_id} not found in Elasticsearch")
            return True  # Consider as success
        except Exception as e:
            logger.error(f"❌ Failed to delete document {doc_id}: {e}")
            return False

    async def update_document_acl(
        self,
        doc_id: str,
        acl_user_ids: List[str],
        acl_role_ids: List[str],
        acl_everyone: bool,
        created_by: str = None
    ) -> bool:
        """
        Update ACL fields for an existing document.

        This method is called when document permissions change to keep
        Elasticsearch in sync with the source of truth (PostgreSQL).

        Args:
            doc_id: Document ID to update
            acl_user_ids: List of user IDs with view permission
            acl_role_ids: List of role IDs with view permission
            acl_everyone: Whether everyone in tenant has access
            created_by: Document owner (optional, only updated if provided)

        Returns:
            True if update succeeded, False otherwise
        """
        try:
            # Build update body - only update ACL fields
            update_body = {
                "acl_user_ids": acl_user_ids,
                "acl_role_ids": acl_role_ids,
                "acl_everyone": acl_everyone
            }

            # Optionally update created_by if provided
            if created_by is not None:
                update_body["created_by"] = created_by

            await self.async_client.update(
                index=self.index_name,
                id=doc_id,
                body={"doc": update_body}
            )

            logger.info(
                f"✅ Updated ACL for document {doc_id}: "
                f"users={len(acl_user_ids)}, roles={len(acl_role_ids)}, everyone={acl_everyone}"
            )
            return True

        except NotFoundError:
            logger.warning(f"Document {doc_id} not found in Elasticsearch for ACL update")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to update ACL for document {doc_id}: {e}")
            return False

    async def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single document by ID.

        Returns:
            Document data or None if not found
        """
        try:
            response = await self.async_client.get(
                index=self.index_name,
                id=doc_id,
                _source_excludes=["content_vector"]
            )
            return response["_source"]
        except NotFoundError:
            return None
        except Exception as e:
            logger.error(f"❌ Failed to get document {doc_id}: {e}")
            return None

    async def close(self):
        """Close async client connections"""
        await self.async_client.close()
