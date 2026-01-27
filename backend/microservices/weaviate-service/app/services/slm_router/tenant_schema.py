"""
Tenant Schema Provider: Extract Schema Context for SLM

This module extracts and formats tenant-specific schema information
that the SLM uses to understand the tenant's data structure:
1. Document types present in the tenant's data
2. Folder types and hierarchy patterns
3. Known entities (clients, employees, departments)
4. Domain-specific terminology
5. Semantic inventory (date ranges, counts per type, temporal distribution)

The schema is cached per-tenant to minimize overhead.

Version 1.1 - January 2026 (Added semantic inventory for context-aware queries)
"""

import asyncio
import logging
import json
from typing import Optional, Dict, Any, List, Set, Tuple
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# SEMANTIC INVENTORY MODELS
# =============================================================================

class DateRange(BaseModel):
    """Date range of documents in the tenant's data."""
    min_year: Optional[int] = None
    max_year: Optional[int] = None
    min_date: Optional[datetime] = None
    max_date: Optional[datetime] = None

    def to_string(self) -> str:
        """Format as human-readable string."""
        if self.min_year and self.max_year:
            if self.min_year == self.max_year:
                return f"año {self.min_year}"
            return f"años {self.min_year}-{self.max_year}"
        return "sin información de fechas"


class DocumentTypeInventory(BaseModel):
    """Inventory of a specific document type."""
    type_name: str
    count: int = 0
    # Year distribution for this type (year -> count)
    year_distribution: Dict[int, int] = Field(default_factory=dict)
    # Sample document names (for context)
    sample_names: List[str] = Field(default_factory=list, max_length=3)

    def years_with_documents(self) -> List[int]:
        """Get years that have documents of this type."""
        return sorted(self.year_distribution.keys())


class SemanticInventory(BaseModel):
    """
    Complete semantic inventory of a tenant's data.

    This gives Emma full awareness of WHAT data exists, enabling
    queries like "¿Cuántos seguros tengo en 2006?"
    """
    # Date range across all documents
    date_range: DateRange = Field(default_factory=DateRange)

    # Detailed inventory per document type
    document_types: Dict[str, DocumentTypeInventory] = Field(default_factory=dict)

    # Year distribution across all types (year -> total count)
    total_by_year: Dict[int, int] = Field(default_factory=dict)

    # Top categories with counts (for quick reference)
    top_categories: List[Tuple[str, int]] = Field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Format inventory as context for SLM prompt."""
        parts = []

        # Date range
        parts.append(f"Rango temporal: {self.date_range.to_string()}")

        # Top categories with counts
        if self.top_categories:
            categories_str = ", ".join(
                f"{cat}: {count}" for cat, count in self.top_categories[:10]
            )
            parts.append(f"Inventario por tipo: {categories_str}")

        # Years with data
        if self.total_by_year:
            years = sorted(self.total_by_year.keys())
            if len(years) <= 5:
                years_str = ", ".join(
                    f"{y}({self.total_by_year[y]})" for y in years
                )
            else:
                # Show first 2 and last 2 years
                years_str = f"{years[0]}({self.total_by_year[years[0]]}), " \
                           f"{years[1]}({self.total_by_year[years[1]]}), ..., " \
                           f"{years[-2]}({self.total_by_year[years[-2]]}), " \
                           f"{years[-1]}({self.total_by_year[years[-1]]})"
            parts.append(f"Documentos por año: {years_str}")

        return "\n".join(parts)


# =============================================================================
# SCHEMA MODELS
# =============================================================================

class TenantSchema(BaseModel):
    """
    Schema information for a tenant.

    This is passed to the SLM to help it understand the tenant's data.
    """
    tenant_id: str
    tenant_name: Optional[str] = None

    # Document structure
    document_types: List[str] = Field(
        default_factory=list,
        description="Semantic types of documents present (contract, invoice, etc.)"
    )
    folder_types: List[str] = Field(
        default_factory=list,
        description="Types of folders/containers (case, project, client_folder)"
    )

    # Known entities
    known_clients: List[str] = Field(
        default_factory=list,
        description="Client names in the system"
    )
    known_departments: List[str] = Field(
        default_factory=list,
        description="Department names"
    )
    known_employees: List[str] = Field(
        default_factory=list,
        description="Employee names (limited for privacy)"
    )

    # Domains present
    domains: List[str] = Field(
        default_factory=list,
        description="Domains represented (legal, fiscal, hr, etc.)"
    )

    # Statistics (helps SLM calibrate expectations)
    total_documents: int = 0
    total_folders: int = 0

    # Semantic inventory (date ranges, counts per type, temporal distribution)
    semantic_inventory: SemanticInventory = Field(
        default_factory=SemanticInventory,
        description="Full semantic inventory for context-aware queries"
    )

    # Custom terminology (tenant-specific terms)
    terminology: Dict[str, str] = Field(
        default_factory=dict,
        description="Custom terms mapping (e.g., 'expediente' -> 'case')"
    )

    # Graph labels available
    graph_labels: List[str] = Field(
        default_factory=list,
        description="Apache AGE node labels available"
    )

    # Timestamps
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None

    def to_prompt_context(self) -> str:
        """
        Format as context string for SLM prompt.

        Includes semantic inventory for queries like:
        - "¿Cuántos seguros tengo en 2006?"
        - "¿Qué contratos hay del cliente ACME?"
        - "¿Cuál es el rango de fechas de mis documentos?"
        """
        parts = [f"Tenant: {self.tenant_name or self.tenant_id}"]

        # Semantic inventory first (most important for context-aware queries)
        if self.semantic_inventory:
            inventory_context = self.semantic_inventory.to_prompt_context()
            if inventory_context:
                parts.append(inventory_context)

        if self.document_types:
            parts.append(f"Tipos de documento: {', '.join(self.document_types[:15])}")

        if self.folder_types:
            parts.append(f"Tipos de carpeta: {', '.join(self.folder_types[:10])}")

        if self.known_clients:
            parts.append(f"Clientes conocidos: {', '.join(self.known_clients[:10])}")

        if self.domains:
            parts.append(f"Dominios: {', '.join(self.domains)}")

        if self.graph_labels:
            parts.append(f"Etiquetas de grafo: {', '.join(self.graph_labels)}")

        if self.terminology:
            terms = [f"{k}={v}" for k, v in list(self.terminology.items())[:5]]
            parts.append(f"Terminología: {', '.join(terms)}")

        parts.append(f"Totales: {self.total_documents} documentos, {self.total_folders} carpetas")

        return "\n".join(parts)

    def is_expired(self) -> bool:
        """Check if schema cache has expired."""
        if self.expires_at is None:
            return True
        return datetime.utcnow() > self.expires_at


# =============================================================================
# SCHEMA EXTRACTION
# =============================================================================

class SchemaExtractor:
    """
    Extracts schema information from the tenant's data.

    Uses Apache AGE graph and Weaviate to gather metadata.
    """

    def __init__(self):
        self._graph_provider = None
        self._weaviate_client = None

    async def _ensure_graph_provider(self):
        """Lazy initialization of graph provider."""
        if self._graph_provider is not None:
            return

        try:
            from ..sil.graph import get_graph_provider
            self._graph_provider = await get_graph_provider()
        except ImportError:
            logger.warning("SIL graph provider not available for schema extraction")
        except Exception as e:
            logger.error(f"Failed to get graph provider: {e}")

    async def _ensure_weaviate_client(self):
        """Lazy initialization of Weaviate client."""
        if self._weaviate_client is not None:
            return

        try:
            from ..weaviate_service import get_weaviate_client
            self._weaviate_client = get_weaviate_client()
        except ImportError:
            logger.warning("Weaviate client not available for schema extraction")
        except Exception as e:
            logger.error(f"Failed to get Weaviate client: {e}")

    async def extract(self, tenant_id: str, cache_ttl_seconds: int = 300) -> TenantSchema:
        """
        Extract schema for a tenant.

        Args:
            tenant_id: The tenant to extract schema for
            cache_ttl_seconds: How long the schema is valid (default 5 min)

        Returns:
            TenantSchema with extracted information
        """
        schema = TenantSchema(
            tenant_id=tenant_id,
            expires_at=datetime.utcnow() + timedelta(seconds=cache_ttl_seconds)
        )

        # Extract in parallel
        await asyncio.gather(
            self._extract_from_graph(tenant_id, schema),
            self._extract_from_weaviate(tenant_id, schema),
            return_exceptions=True
        )

        # Add default graph labels
        schema.graph_labels = [
            "structural_document",
            "structural_folder",
            "Entity",
            "Chunk"
        ]

        # Add common Spanish terminology mappings
        schema.terminology.update({
            "expediente": "case",
            "contrato": "contract",
            "factura": "invoice",
            "cliente": "client",
            "empleado": "employee",
            "carpeta": "folder"
        })

        logger.info(
            f"Schema extracted for tenant {tenant_id}: "
            f"{len(schema.document_types)} doc types, "
            f"{len(schema.known_clients)} clients, "
            f"{schema.total_documents} docs"
        )

        return schema

    async def _extract_from_graph(self, tenant_id: str, schema: TenantSchema):
        """Extract schema information from Apache AGE graph."""
        await self._ensure_graph_provider()

        if not self._graph_provider:
            return

        try:
            # Get document types with counts
            doc_types_query = """
                MATCH (d:structural_document)
                WHERE d.tenant_id = $tenant_id
                RETURN DISTINCT d.semantic_type as doc_type, count(*) as num
                ORDER BY num DESC LIMIT 20
            """
            result = await self._graph_provider.execute_cypher(
                doc_types_query,
                {"tenant_id": tenant_id}
            )
            if result:
                schema.document_types = [r['doc_type'] for r in result if r.get('doc_type')]
                schema.total_documents = sum(r.get('num', 0) for r in result)

                # Build semantic inventory - top categories
                schema.semantic_inventory.top_categories = [
                    (r['doc_type'], r.get('num', 0))
                    for r in result if r.get('doc_type')
                ]

            # Get folder types
            folder_types_query = """
                MATCH (f:structural_folder)
                WHERE f.tenant_id = $tenant_id
                RETURN DISTINCT f.folder_type as folder_type, count(*) as num
                ORDER BY num DESC LIMIT 10
            """
            result = await self._graph_provider.execute_cypher(
                folder_types_query,
                {"tenant_id": tenant_id}
            )
            if result:
                schema.folder_types = [r['folder_type'] for r in result if r.get('folder_type')]
                schema.total_folders = sum(r.get('num', 0) for r in result)

            # Get known entities (clients)
            entities_query = """
                MATCH (e:Entity)
                WHERE e.tenant_id = $tenant_id AND e.type = 'client'
                RETURN DISTINCT e.name as name
                ORDER BY name LIMIT 20
            """
            result = await self._graph_provider.execute_cypher(
                entities_query,
                {"tenant_id": tenant_id}
            )
            if result:
                schema.known_clients = [r['name'] for r in result if r.get('name')]

            # Get domains
            domains_query = """
                MATCH (d:structural_document)
                WHERE d.tenant_id = $tenant_id
                RETURN DISTINCT d.domain as doc_domain, count(*) as num
                ORDER BY num DESC LIMIT 10
            """
            result = await self._graph_provider.execute_cypher(
                domains_query,
                {"tenant_id": tenant_id}
            )
            if result:
                schema.domains = [r['doc_domain'] for r in result if r.get('doc_domain')]

            # =================================================================
            # SEMANTIC INVENTORY EXTRACTION
            # =================================================================

            # Get date range (min/max year from document dates)
            date_range_query = """
                MATCH (d:structural_document)
                WHERE d.tenant_id = $tenant_id AND d.document_date IS NOT NULL
                RETURN
                    min(d.document_date) as min_date,
                    max(d.document_date) as max_date
            """
            result = await self._graph_provider.execute_cypher(
                date_range_query,
                {"tenant_id": tenant_id}
            )
            if result and result[0].get('min_date'):
                min_date = result[0]['min_date']
                max_date = result[0]['max_date']

                # Parse dates and extract years
                try:
                    if isinstance(min_date, str):
                        min_dt = datetime.fromisoformat(min_date.replace('Z', '+00:00'))
                        max_dt = datetime.fromisoformat(max_date.replace('Z', '+00:00'))
                    else:
                        min_dt = min_date
                        max_dt = max_date

                    schema.semantic_inventory.date_range = DateRange(
                        min_year=min_dt.year,
                        max_year=max_dt.year,
                        min_date=min_dt,
                        max_date=max_dt
                    )
                except Exception as e:
                    logger.warning(f"Could not parse date range: {e}")

            # Get document count by year
            year_distribution_query = """
                MATCH (d:structural_document)
                WHERE d.tenant_id = $tenant_id AND d.document_date IS NOT NULL
                WITH d, substring(toString(d.document_date), 0, 4) as year_str
                WHERE year_str IS NOT NULL
                RETURN year_str as year, count(*) as num
                ORDER BY year
            """
            result = await self._graph_provider.execute_cypher(
                year_distribution_query,
                {"tenant_id": tenant_id}
            )
            if result:
                for r in result:
                    try:
                        year = int(r['year'])
                        count = r.get('num', 0)
                        schema.semantic_inventory.total_by_year[year] = count
                    except (ValueError, TypeError):
                        continue

            # Get detailed inventory per document type (type + year distribution)
            type_year_query = """
                MATCH (d:structural_document)
                WHERE d.tenant_id = $tenant_id AND d.semantic_type IS NOT NULL
                WITH d.semantic_type as doc_type,
                     CASE WHEN d.document_date IS NOT NULL
                          THEN substring(toString(d.document_date), 0, 4)
                          ELSE null
                     END as year_str,
                     d.name as doc_name
                RETURN doc_type, year_str as year, count(*) as num,
                       collect(doc_name)[0..3] as samples
                ORDER BY doc_type, year
            """
            result = await self._graph_provider.execute_cypher(
                type_year_query,
                {"tenant_id": tenant_id}
            )
            if result:
                for r in result:
                    doc_type = r.get('doc_type')
                    if not doc_type:
                        continue

                    # Get or create inventory entry
                    if doc_type not in schema.semantic_inventory.document_types:
                        schema.semantic_inventory.document_types[doc_type] = DocumentTypeInventory(
                            type_name=doc_type
                        )

                    inventory = schema.semantic_inventory.document_types[doc_type]
                    inventory.count += r.get('num', 0)

                    # Add year distribution
                    year = r.get('year')
                    if year:
                        try:
                            year_int = int(year)
                            inventory.year_distribution[year_int] = r.get('num', 0)
                        except (ValueError, TypeError):
                            pass

                    # Add samples
                    samples = r.get('samples', [])
                    if samples and len(inventory.sample_names) < 3:
                        inventory.sample_names.extend(samples[:3 - len(inventory.sample_names)])

        except Exception as e:
            logger.error(f"Error extracting schema from graph: {e}")

    async def _extract_from_weaviate(self, tenant_id: str, schema: TenantSchema):
        """Extract schema information from Weaviate."""
        await self._ensure_weaviate_client()

        if not self._weaviate_client:
            return

        try:
            from ...core.config import settings

            collection_name = f"{settings.collection_prefix}documents"

            # Get aggregated document info
            collection = self._weaviate_client.collections.get(collection_name)

            # This is a simplified extraction - full implementation would
            # use Weaviate's aggregate API
            # For now, we supplement from graph extraction

        except Exception as e:
            logger.debug(f"Weaviate schema extraction skipped: {e}")


# =============================================================================
# TENANT SCHEMA PROVIDER (with caching)
# =============================================================================

class TenantSchemaProvider:
    """
    Provides cached tenant schema information.

    Caches schema per tenant with configurable TTL.
    """

    def __init__(self, cache_ttl_seconds: int = 300):
        self._cache: Dict[str, TenantSchema] = {}
        self._extractor = SchemaExtractor()
        self._cache_ttl = cache_ttl_seconds
        self._redis_client = None
        self._use_redis = False

    async def initialize(self, use_redis: bool = True):
        """Initialize with optional Redis caching."""
        self._use_redis = use_redis

        if use_redis:
            try:
                from ...core.config import settings
                import redis.asyncio as redis

                self._redis_client = redis.from_url(settings.redis_url)
                await self._redis_client.ping()
                logger.info("TenantSchemaProvider initialized with Redis cache")
            except Exception as e:
                logger.warning(f"Redis not available, using in-memory cache: {e}")
                self._use_redis = False

    async def get_schema(self, tenant_id: str) -> TenantSchema:
        """
        Get schema for a tenant (from cache or extract fresh).

        Args:
            tenant_id: The tenant ID

        Returns:
            TenantSchema for the tenant
        """
        # Try in-memory cache first
        if tenant_id in self._cache:
            schema = self._cache[tenant_id]
            if not schema.is_expired():
                return schema

        # Try Redis cache
        if self._use_redis and self._redis_client:
            try:
                cached = await self._redis_client.get(f"slm:schema:{tenant_id}")
                if cached:
                    schema = TenantSchema.model_validate_json(cached)
                    if not schema.is_expired():
                        self._cache[tenant_id] = schema
                        return schema
            except Exception as e:
                logger.warning(f"Redis cache read error: {e}")

        # Extract fresh schema
        schema = await self._extractor.extract(tenant_id, self._cache_ttl)

        # Cache it
        self._cache[tenant_id] = schema

        if self._use_redis and self._redis_client:
            try:
                await self._redis_client.setex(
                    f"slm:schema:{tenant_id}",
                    self._cache_ttl,
                    schema.model_dump_json()
                )
            except Exception as e:
                logger.warning(f"Redis cache write error: {e}")

        return schema

    async def get_prompt_context(self, tenant_id: str) -> str:
        """
        Get formatted schema context for SLM prompt.

        Args:
            tenant_id: The tenant ID

        Returns:
            Formatted string for prompt context
        """
        schema = await self.get_schema(tenant_id)
        return schema.to_prompt_context()

    async def invalidate(self, tenant_id: str):
        """Invalidate cached schema for a tenant."""
        if tenant_id in self._cache:
            del self._cache[tenant_id]

        if self._use_redis and self._redis_client:
            try:
                await self._redis_client.delete(f"slm:schema:{tenant_id}")
            except Exception:
                pass

    async def close(self):
        """Close resources."""
        if self._redis_client:
            await self._redis_client.close()


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_schema_provider: Optional[TenantSchemaProvider] = None


def get_schema_provider() -> TenantSchemaProvider:
    """Get the singleton schema provider instance."""
    global _schema_provider
    if _schema_provider is None:
        _schema_provider = TenantSchemaProvider()
    return _schema_provider


async def initialize_schema_provider(use_redis: bool = True) -> TenantSchemaProvider:
    """Initialize the singleton schema provider."""
    global _schema_provider
    _schema_provider = TenantSchemaProvider()
    await _schema_provider.initialize(use_redis)
    return _schema_provider
