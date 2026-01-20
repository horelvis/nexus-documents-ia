"""
Content Model Discovery Service

Discovers and parses content models from external connectors:
- Alfresco: Dictionary API for types, aspects, properties
- SharePoint: Content Types + Site Columns (future)
- FileSystem: Inferred from file metadata (future)

The discovered model is enriched with LLM-powered semantic analysis
to understand domain, importance, and chunking strategies.
"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import (
    Connector,
    ConnectorContentModel,
    DataLearningJob,
    DataLearningJobStatus,
)
from app.schemas.data_learning import (
    ContentTypeDefinition,
    AspectDefinition,
    PropertyDefinition,
    TypeSemantic,
    PropertySemantic,
    ContentModelSummary,
    DiscoveryMethod,
)

logger = logging.getLogger(__name__)


class ContentModelDiscoveryProvider(ABC):
    """
    Abstract base for content model discovery.

    Each connector type implements this to fetch its native content model
    and convert it to a unified format.
    """

    @abstractmethod
    async def fetch_content_model(self, connector: Connector) -> Dict[str, Any]:
        """
        Fetch raw content model from the connector.

        Returns:
            Dict with keys: content_types, aspects, property_definitions, association_types
        """
        pass

    @abstractmethod
    def get_discovery_method(self) -> DiscoveryMethod:
        """Return the discovery method used by this provider."""
        pass


class AlfrescoContentModelDiscoveryProvider(ContentModelDiscoveryProvider):
    """
    Alfresco content model discovery via REST APIs.

    Uses two approaches in order:
    1. Public API v1 (/model/types, /model/aspects) - Modern REST API
    2. Legacy Dictionary API (/service/api/dictionary) - Fallback for custom models

    The Legacy API is used as fallback because it returns ALL registered models
    including Custom Content Models (CMM) that may not appear in Public API v1.
    """

    def __init__(self, http_client=None):
        """
        Initialize the provider.

        Args:
            http_client: Optional httpx client for testing
        """
        self._http_client = http_client

    async def fetch_content_model(self, connector: Connector) -> Dict[str, Any]:
        """
        Fetch Alfresco content model via Dictionary REST API.

        Uses two approaches:
        1. Legacy Dictionary API (/service/api/dictionary) - Returns ALL registered models
        2. Public API v1 (/model/types, /model/aspects) - Fallback for newer instances

        The Legacy API is preferred because it returns custom models (CMM) that
        may not appear in the Public API.

        Args:
            connector: Connector with Alfresco configuration

        Returns:
            Dict with content_types, aspects, property_definitions, association_types
        """
        import base64
        import httpx

        config = connector.config
        base_url = config.get("url", "").rstrip("/")
        username = config.get("username", "")
        password = config.get("password", "")

        # Build auth header
        auth_str = f"{username}:{password}"
        auth_bytes = base64.b64encode(auth_str.encode()).decode()
        headers = {
            "Authorization": f"Basic {auth_bytes}",
            "Accept": "application/json",
        }

        result = {
            "content_types": {},
            "aspects": {},
            "property_definitions": {},
            "association_types": {},
        }

        api_path = config.get("api_path", "/alfresco/api/-default-/public/alfresco/versions/1")

        client = self._http_client or httpx.AsyncClient(headers=headers, timeout=60.0)
        try:
            # Try Public API v1 first (modern REST API)
            result = await self._fetch_from_public_api(client, base_url, api_path)

            # Count custom types (non-cm:, non-sys: prefixes)
            custom_types = [t for t in result["content_types"].keys()
                          if not t.startswith(("cm:", "sys:", "app:", "usr:"))]

            logger.info(
                f"Public API v1 discovered: "
                f"{len(result['content_types'])} types ({len(custom_types)} custom), "
                f"{len(result['aspects'])} aspects, "
                f"{len(result['property_definitions'])} properties"
            )

            # If no custom types found, try Legacy Dictionary API as fallback
            if not custom_types:
                logger.info("No custom types in Public API, trying Legacy Dictionary API...")
                legacy_result = await self._fetch_from_legacy_dictionary(client, base_url)

                if legacy_result["content_types"]:
                    # Merge legacy results into main result
                    result = self._merge_models(result, legacy_result)

                    custom_types = [t for t in result["content_types"].keys()
                                  if not t.startswith(("cm:", "sys:", "app:", "usr:"))]
                    logger.info(
                        f"After Legacy API merge: "
                        f"{len(result['content_types'])} types ({len(custom_types)} custom), "
                        f"{len(result['aspects'])} aspects, "
                        f"{len(result['property_definitions'])} properties"
                    )

        finally:
            if not self._http_client:
                await client.aclose()

        return result

    async def _fetch_from_legacy_dictionary(
        self,
        client,
        base_url: str,
    ) -> Dict[str, Any]:
        """
        Fetch content model from Alfresco Legacy Dictionary API.

        Endpoint: GET /alfresco/service/api/dictionary

        This API returns ALL registered models including:
        - Core Alfresco models (cm:, sys:, app:)
        - Custom Content Models deployed via CMM
        - Custom models deployed via Spring beans

        Reference: https://docs.alfresco.com/5.0/references/RESTful-Dictionary.html
        """
        result = {
            "content_types": {},
            "aspects": {},
            "property_definitions": {},
            "association_types": {},
        }

        try:
            # Fetch all classes from dictionary
            response = await client.get(
                f"{base_url}/alfresco/service/api/dictionary"
            )

            if response.status_code != 200:
                logger.warning(
                    f"Legacy Dictionary API failed: {response.status_code}"
                )
                return result

            data = response.json()

            # Process types (classes with isAspect=false)
            for class_def in data.get("classes", []):
                class_name = class_def.get("name", "")
                is_aspect = class_def.get("isAspect", False)

                if not class_name:
                    continue

                # Extract properties for this class
                properties = []
                for prop in class_def.get("properties", []):
                    prop_name = prop.get("name", "")
                    if prop_name:
                        properties.append(prop_name)

                        # Store property definition
                        if prop_name not in result["property_definitions"]:
                            result["property_definitions"][prop_name] = {
                                "data_type": prop.get("dataType", "d:text"),
                                "title": prop.get("title", prop_name),
                                "description": prop.get("description"),
                                "mandatory": prop.get("mandatory", False),
                                "multi_valued": prop.get("multiValued", False),
                                "protected": prop.get("protected", False),
                                "indexed": prop.get("indexed", True),
                                "constraints": prop.get("constraints", []),
                                "default_value": prop.get("defaultValue"),
                            }

                if is_aspect:
                    result["aspects"][class_name] = {
                        "title": class_def.get("title", class_name),
                        "description": class_def.get("description"),
                        "parent": class_def.get("parent"),
                        "properties": properties,
                    }
                else:
                    result["content_types"][class_name] = {
                        "title": class_def.get("title", class_name),
                        "description": class_def.get("description"),
                        "parent": class_def.get("parent"),
                        "properties": properties,
                        "mandatory_aspects": class_def.get("mandatoryAspects", []),
                    }

            # Process associations if available
            for assoc in data.get("associations", []):
                assoc_name = assoc.get("name", "")
                if assoc_name:
                    result["association_types"][assoc_name] = {
                        "title": assoc.get("title", assoc_name),
                        "source_type": assoc.get("sourceType"),
                        "target_type": assoc.get("targetType"),
                        "source_mandatory": assoc.get("sourceMandatory", False),
                        "target_mandatory": assoc.get("targetMandatory", False),
                    }

            logger.info(
                f"Legacy Dictionary API parsed: "
                f"{len(result['content_types'])} types, "
                f"{len(result['aspects'])} aspects"
            )

        except Exception as e:
            logger.error(f"Error fetching from Legacy Dictionary API: {e}")

        return result

    async def _fetch_from_public_api(
        self,
        client,
        base_url: str,
        api_path: str,
    ) -> Dict[str, Any]:
        """
        Fetch content model from Alfresco Public REST API v1.

        Endpoints:
        - GET /model/types - Content types
        - GET /model/aspects - Aspects

        Note: This API may not include all custom models (CMM).
        Used as fallback when Legacy API is not available.
        """
        result = {
            "content_types": {},
            "aspects": {},
            "property_definitions": {},
            "association_types": {},
        }

        # Fetch types
        try:
            types_response = await client.get(
                f"{base_url}{api_path}/model/types",
                params={"skipCount": 0, "maxItems": 500}
            )
            if types_response.status_code == 200:
                types_data = types_response.json()
                for entry in types_data.get("list", {}).get("entries", []):
                    type_info = entry.get("entry", {})
                    type_name = type_info.get("id", "")
                    if type_name:
                        result["content_types"][type_name] = {
                            "title": type_info.get("title", type_name),
                            "description": type_info.get("description"),
                            "parent": type_info.get("parentId"),
                            "properties": [
                                p.get("id") for p in type_info.get("properties", [])
                            ],
                            "mandatory_aspects": type_info.get("mandatoryAspects", []),
                        }
                        # Extract property definitions
                        for prop in type_info.get("properties", []):
                            prop_name = prop.get("id")
                            if prop_name and prop_name not in result["property_definitions"]:
                                result["property_definitions"][prop_name] = {
                                    "data_type": prop.get("dataType"),
                                    "mandatory": prop.get("mandatory", False),
                                    "multi_valued": prop.get("multiValued", False),
                                    "constraints": prop.get("constraints"),
                                    "default_value": prop.get("defaultValue"),
                                }
            else:
                logger.warning(
                    f"Failed to fetch types from Public API: {types_response.status_code}"
                )
        except Exception as e:
            logger.error(f"Error fetching types from Public API: {e}")

        # Fetch aspects
        try:
            aspects_response = await client.get(
                f"{base_url}{api_path}/model/aspects",
                params={"skipCount": 0, "maxItems": 500}
            )
            if aspects_response.status_code == 200:
                aspects_data = aspects_response.json()
                for entry in aspects_data.get("list", {}).get("entries", []):
                    aspect_info = entry.get("entry", {})
                    aspect_name = aspect_info.get("id", "")
                    if aspect_name:
                        result["aspects"][aspect_name] = {
                            "title": aspect_info.get("title", aspect_name),
                            "description": aspect_info.get("description"),
                            "properties": [
                                p.get("id") for p in aspect_info.get("properties", [])
                            ],
                        }
                        # Extract property definitions from aspects
                        for prop in aspect_info.get("properties", []):
                            prop_name = prop.get("id")
                            if prop_name and prop_name not in result["property_definitions"]:
                                result["property_definitions"][prop_name] = {
                                    "data_type": prop.get("dataType"),
                                    "mandatory": prop.get("mandatory", False),
                                    "multi_valued": prop.get("multiValued", False),
                                    "constraints": prop.get("constraints"),
                                    "default_value": prop.get("defaultValue"),
                                }
            else:
                logger.warning(
                    f"Failed to fetch aspects from Public API: {aspects_response.status_code}"
                )
        except Exception as e:
            logger.error(f"Error fetching aspects from Public API: {e}")

        return result

    def _merge_models(
        self,
        primary_model: Dict[str, Any],
        fallback_model: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge two content models, adding entries from fallback that don't exist in primary.
        """
        result = {
            "content_types": dict(primary_model.get("content_types", {})),
            "aspects": dict(primary_model.get("aspects", {})),
            "property_definitions": dict(primary_model.get("property_definitions", {})),
            "association_types": dict(primary_model.get("association_types", {})),
        }

        # Add types from fallback that don't exist in primary
        for type_name, type_info in fallback_model.get("content_types", {}).items():
            if type_name not in result["content_types"]:
                result["content_types"][type_name] = type_info

        # Add aspects from fallback that don't exist in primary
        for aspect_name, aspect_info in fallback_model.get("aspects", {}).items():
            if aspect_name not in result["aspects"]:
                result["aspects"][aspect_name] = aspect_info

        # Add property definitions from fallback that don't exist in primary
        for prop_name, prop_info in fallback_model.get("property_definitions", {}).items():
            if prop_name not in result["property_definitions"]:
                result["property_definitions"][prop_name] = prop_info

        # Add associations from fallback that don't exist in primary
        for assoc_name, assoc_info in fallback_model.get("association_types", {}).items():
            if assoc_name not in result["association_types"]:
                result["association_types"][assoc_name] = assoc_info

        return result

    def get_discovery_method(self) -> DiscoveryMethod:
        return DiscoveryMethod.API


class ContentModelDiscoveryService:
    """
    Main service for content model discovery and storage.

    Orchestrates discovery providers, enriches with LLM semantics,
    and persists to database.
    """

    # Registry of providers by connector type
    _providers: Dict[str, Type[ContentModelDiscoveryProvider]] = {
        "alfresco": AlfrescoContentModelDiscoveryProvider,
    }

    def __init__(self, db: AsyncSession, llm_client=None):
        """
        Initialize the service.

        Args:
            db: Database session
            llm_client: Optional LLM client for semantic enrichment
        """
        self.db = db
        self.llm_client = llm_client

    @classmethod
    def register_provider(
        cls,
        connector_type: str,
        provider_class: Type[ContentModelDiscoveryProvider]
    ):
        """Register a discovery provider for a connector type."""
        cls._providers[connector_type] = provider_class

    async def discover_content_model(
        self,
        connector_id: UUID,
        enrich_with_llm: bool = True,
        update_job: Optional[DataLearningJob] = None,
    ) -> ConnectorContentModel:
        """
        Discover and store content model for a connector.

        Args:
            connector_id: UUID of the connector
            enrich_with_llm: Whether to enrich with LLM semantics
            update_job: Optional job to update progress

        Returns:
            ConnectorContentModel with discovered and enriched model
        """
        # Fetch connector
        result = await self.db.execute(
            select(Connector).where(Connector.id == connector_id)
        )
        connector = result.scalar_one_or_none()
        if not connector:
            raise ValueError(f"Connector not found: {connector_id}")

        # Get provider
        provider_class = self._providers.get(connector.connector_type)
        if not provider_class:
            raise ValueError(
                f"No content model provider for connector type: {connector.connector_type}"
            )

        # Update job progress
        if update_job:
            update_job.current_phase = "Fetching content model from connector"
            update_job.progress_percent = 10
            await self.db.commit()

        # Discover content model
        provider = provider_class()
        raw_model = await provider.fetch_content_model(connector)

        # Update job progress
        if update_job:
            update_job.current_phase = "Processing content model"
            update_job.progress_percent = 50
            await self.db.commit()

        # Enrich with LLM semantics
        type_semantics = None
        property_semantics = None
        if enrich_with_llm and self.llm_client:
            if update_job:
                update_job.current_phase = "Enriching with semantic analysis"
                update_job.progress_percent = 70
                await self.db.commit()

            type_semantics = await self._enrich_type_semantics(
                raw_model.get("content_types", {})
            )
            property_semantics = await self._enrich_property_semantics(
                raw_model.get("property_definitions", {})
            )
        else:
            # Generate basic semantics without LLM
            type_semantics = self._generate_basic_type_semantics(
                raw_model.get("content_types", {})
            )
            property_semantics = self._generate_basic_property_semantics(
                raw_model.get("property_definitions", {})
            )

        # Check if model already exists
        existing_result = await self.db.execute(
            select(ConnectorContentModel).where(
                ConnectorContentModel.connector_id == connector_id
            )
        )
        content_model = existing_result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if content_model:
            # Update existing
            content_model.content_types = raw_model.get("content_types", {})
            content_model.aspects = raw_model.get("aspects", {})
            content_model.property_definitions = raw_model.get("property_definitions")
            content_model.association_types = raw_model.get("association_types")
            content_model.type_semantics = type_semantics
            content_model.property_semantics = property_semantics
            content_model.last_updated_at = now
        else:
            # Create new
            content_model = ConnectorContentModel(
                connector_id=connector_id,
                tenant_id=connector.tenant_id,
                content_types=raw_model.get("content_types", {}),
                aspects=raw_model.get("aspects", {}),
                property_definitions=raw_model.get("property_definitions"),
                association_types=raw_model.get("association_types"),
                type_semantics=type_semantics,
                property_semantics=property_semantics,
                discovery_method=provider.get_discovery_method().value,
                discovered_at=now,
            )
            self.db.add(content_model)

        await self.db.commit()
        await self.db.refresh(content_model)

        # Update job progress
        if update_job:
            update_job.current_phase = "Content model discovery completed"
            update_job.progress_percent = 100
            await self.db.commit()

        logger.info(
            f"Content model discovery completed for connector {connector_id}: "
            f"{len(raw_model.get('content_types', {}))} types"
        )

        return content_model

    async def get_content_model(
        self,
        connector_id: UUID
    ) -> Optional[ConnectorContentModel]:
        """Get existing content model for a connector."""
        result = await self.db.execute(
            select(ConnectorContentModel).where(
                ConnectorContentModel.connector_id == connector_id
            )
        )
        return result.scalar_one_or_none()

    async def get_content_model_summary(
        self,
        connector_id: UUID
    ) -> Optional[ContentModelSummary]:
        """Get summary of content model for a connector."""
        content_model = await self.get_content_model(connector_id)
        if not content_model:
            return None

        # Count custom types (non-cm: prefix)
        custom_types = [
            t for t in content_model.content_types.keys()
            if not t.startswith("cm:")
        ]

        # Extract unique domains from type semantics
        domains = set()
        if content_model.type_semantics:
            for semantic in content_model.type_semantics.values():
                if isinstance(semantic, dict) and "domain" in semantic:
                    domains.add(semantic["domain"])

        return ContentModelSummary(
            total_types=len(content_model.content_types),
            total_aspects=len(content_model.aspects),
            total_properties=len(content_model.property_definitions or {}),
            total_associations=len(content_model.association_types or {}),
            custom_types=custom_types,
            semantic_domains=list(domains),
        )

    def _generate_basic_type_semantics(
        self,
        content_types: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Generate basic type semantics without LLM.

        Uses heuristics based on type names and properties.
        """
        semantics = {}
        for type_name, type_info in content_types.items():
            # Determine domain from type name prefix
            domain = "general"
            if any(kw in type_name.lower() for kw in ["legal", "contract", "clause"]):
                domain = "legal"
            elif any(kw in type_name.lower() for kw in ["hr", "employee", "personnel"]):
                domain = "hr"
            elif any(kw in type_name.lower() for kw in ["invoice", "payment", "fiscal"]):
                domain = "finance"

            # Determine semantic type
            semantic_type = "document"
            if "expediente" in type_name.lower():
                semantic_type = "administrative_file"
            elif "contrato" in type_name.lower() or "contract" in type_name.lower():
                semantic_type = "contract"
            elif "factura" in type_name.lower() or "invoice" in type_name.lower():
                semantic_type = "invoice"

            semantics[type_name] = {
                "semantic_type": semantic_type,
                "domain": domain,
                "description": type_info.get("description"),
                "chunking_strategy": "semantic",  # Default
                "importance": 1.0,
            }

        return semantics

    def _generate_basic_property_semantics(
        self,
        property_definitions: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Generate basic property semantics without LLM.

        Uses heuristics based on property names and types.
        """
        semantics = {}
        for prop_name, prop_info in (property_definitions or {}).items():
            # Default values
            search_weight = 1.0
            include_in_embedding = True
            is_identifier = False
            is_date_field = False

            # Adjust based on property name
            lower_name = prop_name.lower()
            if any(kw in lower_name for kw in ["title", "titulo", "name", "nombre"]):
                search_weight = 1.5
            elif any(kw in lower_name for kw in ["id", "numero", "number", "expediente"]):
                search_weight = 2.0
                is_identifier = True
            elif any(kw in lower_name for kw in ["date", "fecha", "created", "modified"]):
                is_date_field = True
                include_in_embedding = False
            elif any(kw in lower_name for kw in ["description", "descripcion"]):
                search_weight = 0.8

            # Check data type
            data_type = prop_info.get("data_type", "")
            if "datetime" in data_type.lower() or "date" in data_type.lower():
                is_date_field = True
                include_in_embedding = False

            semantics[prop_name] = {
                "search_weight": search_weight,
                "include_in_embedding": include_in_embedding,
                "is_identifier": is_identifier,
                "is_date_field": is_date_field,
                "normalized_name": prop_name.split(":")[-1] if ":" in prop_name else prop_name,
            }

        return semantics

    async def _enrich_type_semantics(
        self,
        content_types: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Enrich type semantics using LLM.

        Asks LLM to classify domain, purpose, and suggest chunking strategy.
        """
        # For now, use basic heuristics
        # TODO: Implement LLM enrichment when llm_client is available
        return self._generate_basic_type_semantics(content_types)

    async def _enrich_property_semantics(
        self,
        property_definitions: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Enrich property semantics using LLM.

        Asks LLM to determine importance, searchability, etc.
        """
        # For now, use basic heuristics
        # TODO: Implement LLM enrichment when llm_client is available
        return self._generate_basic_property_semantics(property_definitions)
