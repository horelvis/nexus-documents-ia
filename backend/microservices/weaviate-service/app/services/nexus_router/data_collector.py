"""
NexusRouter Data Collector

Collects training data from multiple sources via APIs (no direct DB access):
1. Historical user queries via Main API
2. Document metadata from Weaviate (local collection)
3. Entity information via Main API
4. Existing SIL structural data from Weaviate

The collector uses HTTP APIs to communicate with other services,
following microservice architecture principles.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class DataCollector:
    """
    Collects training data via APIs (no direct DB access).

    Sources:
    1. Main API - Historical queries, entities
    2. Weaviate - Document metadata, structural data
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize the data collector.

        Args:
            api_url: Main API URL (uses settings if not provided)
            api_key: API key for authentication
        """
        self._api_url = api_url or settings.api_url
        self._api_key = api_key or settings.MICROSERVICES_API_KEY
        self._initialized = False
        self._http_client: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> None:
        """Initialize HTTP client."""
        if self._initialized:
            return

        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={
                "X-API-Key": self._api_key,
                "Content-Type": "application/json",
            }
        )
        self._initialized = True
        logger.info("DataCollector initialized (API-based, no direct DB access)")

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._initialized = False

    # =========================================================================
    # Historical Queries Collection (via Main API)
    # =========================================================================

    async def collect_historical_queries(
        self,
        tenant_ids: Optional[List[str]] = None,
        limit: int = 1000,
        min_rating: Optional[float] = None,
        days_back: int = 90,
    ) -> List[Dict[str, Any]]:
        """
        Collect historical user queries via Main API.

        This calls the Main API which has access to user_interaction_history.

        Args:
            tenant_ids: Filter by specific tenants (None = all tenants)
            limit: Maximum number of queries to collect
            min_rating: Minimum feedback rating to include (0-5)
            days_back: Only include queries from last N days

        Returns:
            List of dicts with query_text, intent, feedback_rating
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Call Main API endpoint for training data
            # This endpoint should be created in the Main API
            params = {
                "limit": limit,
                "days_back": days_back,
            }
            if tenant_ids:
                params["tenant_ids"] = ",".join(tenant_ids)
            if min_rating is not None:
                params["min_rating"] = min_rating

            response = await self._http_client.get(
                f"{self._api_url}/api/v1/internal/training-data/queries",
                params=params,
            )

            if response.status_code == 200:
                return response.json().get("queries", [])
            elif response.status_code == 404:
                # Endpoint doesn't exist yet - return empty
                logger.warning(
                    "Training data API not available. "
                    "Using synthetic data only."
                )
                return []
            else:
                logger.warning(f"Failed to fetch historical queries: {response.status_code}")
                return []

        except httpx.ConnectError:
            logger.warning("Main API not reachable. Using synthetic data only.")
            return []
        except Exception as e:
            logger.warning(f"Could not collect historical queries: {e}")
            return []

    # =========================================================================
    # Document Metadata Collection (from Weaviate)
    # =========================================================================

    async def collect_document_metadata(
        self,
        tenant_ids: Optional[List[str]] = None,
        limit: int = 5000,
    ) -> List[Dict[str, Any]]:
        """
        Collect document metadata from Weaviate collections.

        Uses the local Weaviate service to get document types and metadata.

        Args:
            tenant_ids: Filter by specific tenants
            limit: Maximum documents to sample

        Returns:
            List of dicts with title, mime_type, file_extension, doc_type
        """
        if not self._initialized:
            await self.initialize()

        try:
            from app.services.weaviate_service import weaviate_service

            documents = []

            # Get documents from Weaviate collections
            collections_to_query = []

            if tenant_ids:
                for tenant_id in tenant_ids:
                    collections_to_query.append(f"Nouxcube_{tenant_id}_documents")
            else:
                # Query default collection
                collections_to_query.append("Nouxcube_documents")

            for collection_name in collections_to_query:
                try:
                    # Use Weaviate aggregate to get document types
                    results = await weaviate_service.get_collection_stats(collection_name)

                    if results:
                        # Extract unique document types from stats
                        for doc_type, count in results.get("doc_types", {}).items():
                            documents.append({
                                "doc_type": doc_type,
                                "count": count,
                                "collection": collection_name,
                            })
                except Exception as e:
                    logger.debug(f"Could not query collection {collection_name}: {e}")

            return documents[:limit]

        except Exception as e:
            logger.warning(f"Could not collect document metadata: {e}")
            return []

    async def get_document_type_distribution(
        self,
        tenant_ids: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        """
        Get distribution of document types from Weaviate.

        Returns:
            Dict mapping doc_type -> count
        """
        documents = await self.collect_document_metadata(tenant_ids)

        distribution = {}
        for doc in documents:
            doc_type = doc.get("doc_type", "unknown")
            count = doc.get("count", 1)
            distribution[doc_type] = distribution.get(doc_type, 0) + count

        return distribution

    # =========================================================================
    # Entity Collection (via Main API or Weaviate)
    # =========================================================================

    async def collect_entities(
        self,
        tenant_ids: Optional[List[str]] = None,
        limit: int = 2000,
    ) -> List[Dict[str, Any]]:
        """
        Collect extracted entities via Main API.

        Args:
            tenant_ids: Filter by specific tenants
            limit: Maximum entities to collect

        Returns:
            List of dicts with entity_type, entity_value, domain
        """
        if not self._initialized:
            await self.initialize()

        try:
            params = {"limit": limit}
            if tenant_ids:
                params["tenant_ids"] = ",".join(tenant_ids)

            response = await self._http_client.get(
                f"{self._api_url}/api/v1/internal/training-data/entities",
                params=params,
            )

            if response.status_code == 200:
                return response.json().get("entities", [])
            elif response.status_code == 404:
                logger.warning("Entities API not available. Using defaults.")
                return self._get_default_entities()
            else:
                logger.warning(f"Failed to fetch entities: {response.status_code}")
                return self._get_default_entities()

        except httpx.ConnectError:
            logger.warning("Main API not reachable. Using default entities.")
            return self._get_default_entities()
        except Exception as e:
            logger.warning(f"Could not collect entities: {e}")
            return self._get_default_entities()

    def _get_default_entities(self) -> List[Dict[str, Any]]:
        """Return default entities for synthetic data generation."""
        return [
            {"entity_type": "organization", "entity_value": "ACME Corp"},
            {"entity_type": "organization", "entity_value": "TechCorp"},
            {"entity_type": "organization", "entity_value": "GlobalServices"},
            {"entity_type": "person", "entity_value": "Juan García"},
            {"entity_type": "person", "entity_value": "María López"},
            {"entity_type": "date", "entity_value": "2024"},
            {"entity_type": "date", "entity_value": "enero"},
            {"entity_type": "date", "entity_value": "este mes"},
        ]

    async def get_entity_type_distribution(
        self,
        tenant_ids: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        """
        Get distribution of entity types.

        Returns:
            Dict mapping entity_type -> count
        """
        entities = await self.collect_entities(tenant_ids)

        distribution = {}
        for entity in entities:
            entity_type = entity.get("entity_type", "unknown")
            distribution[entity_type] = distribution.get(entity_type, 0) + 1

        return distribution

    # =========================================================================
    # SIL Structural Data Collection (from Weaviate)
    # =========================================================================

    async def collect_structural_metadata(
        self,
        tenant_ids: Optional[List[str]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Collect structural metadata from SIL Weaviate collection.

        Args:
            tenant_ids: Filter by specific tenants
            limit: Maximum items to collect

        Returns:
            List of structural metadata dicts
        """
        try:
            from app.services.sil import structural_collection

            results = []

            # Query SIL structural documents collection
            # This is already in Weaviate, no external API needed
            for tenant_id in (tenant_ids or [None]):
                try:
                    docs = await structural_collection.search_structural(
                        tenant_id=tenant_id,
                        query="*",
                        limit=limit // (len(tenant_ids) if tenant_ids else 1),
                    )
                    results.extend(docs)
                except Exception as e:
                    logger.debug(f"Could not collect structural data for {tenant_id}: {e}")

            return results

        except ImportError:
            logger.debug("SIL not available")
            return []
        except Exception as e:
            logger.warning(f"Could not collect structural metadata: {e}")
            return []

    # =========================================================================
    # Aggregation Methods
    # =========================================================================

    async def collect_all(
        self,
        tenant_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Collect all available training data.

        Aggregates data from all sources into a single dict
        that can be passed to DatasetBuilder.

        Args:
            tenant_ids: Filter by specific tenants

        Returns:
            Dict with all collected data and statistics
        """
        if not self._initialized:
            await self.initialize()

        logger.info(f"Collecting training data for tenants: {tenant_ids or 'all'}")

        # Collect from all sources in parallel
        historical_task = self.collect_historical_queries(tenant_ids)
        documents_task = self.collect_document_metadata(tenant_ids)
        entities_task = self.collect_entities(tenant_ids)
        doc_types_task = self.get_document_type_distribution(tenant_ids)
        entity_types_task = self.get_entity_type_distribution(tenant_ids)

        results = await asyncio.gather(
            historical_task,
            documents_task,
            entities_task,
            doc_types_task,
            entity_types_task,
            return_exceptions=True,
        )

        historical_queries = results[0] if not isinstance(results[0], Exception) else []
        documents = results[1] if not isinstance(results[1], Exception) else []
        entities = results[2] if not isinstance(results[2], Exception) else []
        doc_type_dist = results[3] if not isinstance(results[3], Exception) else {}
        entity_type_dist = results[4] if not isinstance(results[4], Exception) else {}

        # Add default document types if none found
        if not doc_type_dist:
            doc_type_dist = {
                "contrato": 10,
                "factura": 10,
                "informe": 10,
                "acta": 5,
                "presupuesto": 5,
                "documento": 20,
            }
            logger.info("Using default document types for synthetic generation")

        collected_data = {
            "historical_queries": historical_queries,
            "documents": documents,
            "entities": entities,
            "document_type_distribution": doc_type_dist,
            "entity_type_distribution": entity_type_dist,
            "statistics": {
                "total_historical_queries": len(historical_queries),
                "total_documents": len(documents),
                "total_entities": len(entities),
                "unique_document_types": len(doc_type_dist),
                "unique_entity_types": len(entity_type_dist),
            },
            "collected_at": datetime.now().isoformat(),
            "tenant_ids": tenant_ids,
        }

        logger.info(
            f"Collected: {len(historical_queries)} queries, "
            f"{len(documents)} documents, {len(entities)} entities"
        )

        return collected_data

    async def get_collection_stats(
        self,
        tenant_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Get statistics about available training data.

        Quick overview without collecting all data.

        Returns:
            Dict with counts and distributions
        """
        if not self._initialized:
            await self.initialize()

        doc_types = await self.get_document_type_distribution(tenant_ids)
        entity_types = await self.get_entity_type_distribution(tenant_ids)

        return {
            "document_types": doc_types,
            "entity_types": entity_types,
            "total_document_types": len(doc_types),
            "total_entity_types": len(entity_types),
            "tenant_ids": tenant_ids,
        }


# Singleton instance
data_collector = DataCollector()
