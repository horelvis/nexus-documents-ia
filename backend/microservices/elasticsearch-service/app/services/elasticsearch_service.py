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
                        "metadata": {"type": "object"}
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
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        Index a document for hybrid search
        """
        try:
            doc = {
                "doc_id": doc_id,
                "title": title,
                "content": content,
                "description": description or "",
                "tenant_id": self.tenant_id,
                "file_type": metadata.get("file_type", "unknown"),
                "category": metadata.get("category"),
                "tags": metadata.get("tags", []),
                "created_at": metadata.get("created_at"),
                "updated_at": metadata.get("updated_at"),
                "file_size": metadata.get("file_size"),
                "metadata": metadata or {}
            }

            # Add vector if provided
            if content_vector:
                doc["content_vector"] = content_vector

            await self.async_client.index(
                index=self.index_name,
                id=doc_id,
                body=doc
            )

            logger.debug(f"✅ Indexed document {doc_id} in Elasticsearch")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to index document {doc_id}: {e}")
            return False

    async def hybrid_search(
        self,
        query: str,
        limit: int = 10,
        filters: Dict[str, Any] = None,
        boost_semantic: float = 1.0,
        boost_keyword: float = 1.0
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining keyword and semantic search
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

            # Add filters
            filter_clauses = [{"term": {"tenant_id": self.tenant_id}}]

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
                }
            }

            response = await self.async_client.search(
                index=self.index_name,
                body=search_body
            )

            results = []
            for hit in response["hits"]["hits"]:
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
                    "matches": [{"text": hit["_source"]["content"][:200] + "...", "score": hit["_score"]}]
                }
                results.append(result)

            logger.info(f"✅ Hybrid search returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"❌ Hybrid search failed: {e}")
            return []

    async def semantic_search_with_vector(
        self,
        query_vector: List[float],
        limit: int = 10,
        filters: Dict[str, Any] = None,
        min_score: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search using vector similarity
        """
        try:
            # Build filter clauses
            filter_clauses = [{"term": {"tenant_id": self.tenant_id}}]

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

        except Exception as e:
            logger.error(f"❌ Semantic search failed: {e}")
            return []

    async def get_facets(
        self,
        query: str = None,
        filters: Dict[str, Any] = None,
        facet_fields: List[str] = None,
        max_facet_values: int = 10
    ) -> Dict[str, Any]:
        """
        Get facets for search results with optional query and filters
        """
        try:
            # Build base query
            must_clauses = []
            filter_clauses = [{"term": {"tenant_id": self.tenant_id}}]

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

    async def get_analytics(self, date_from: str = None, date_to: str = None) -> Dict[str, Any]:
        """
        Get search and document analytics
        """
        try:
            # Build date filter
            date_filter = {}
            if date_from or date_to:
                date_filter = {"range": {"created_at": {}}}
                if date_from:
                    date_filter["range"]["created_at"]["gte"] = date_from
                if date_to:
                    date_filter["range"]["created_at"]["lte"] = date_to

            # Aggregation query
            agg_body = {
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"tenant_id": self.tenant_id}},
                            date_filter
                        ]
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

    async def close(self):
        """Close async client connections"""
        await self.async_client.close()