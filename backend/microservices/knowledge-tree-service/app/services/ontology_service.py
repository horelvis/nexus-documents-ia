"""
Business Ontology Service

Manages the shared business_ontology graph in Apache AGE. This graph
defines EntityType and RelationType nodes that serve as the "type system"
for all tenant sector graphs.

Tenant documents connect to the ontology via INSTANCE_OF edges:
    (structural_document)-[:INSTANCE_OF]->(EntityType {name: 'factura'})

The ontology supports type hierarchy via the `parent` property:
    factura → financial_document → document

This enables type-coerced queries: "find all financial documents"
matches facturas, albaranes, nominas, etc.

Usage:
    from app.services.ontology_service import ontology_service

    await ontology_service.initialize()
    entity_type = await ontology_service.resolve_type("factura")
    ancestors = await ontology_service.get_type_ancestors("factura")
    valid_rels = await ontology_service.get_valid_relations("document", "person")
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from app.services.age_client import age_client

logger = logging.getLogger(__name__)

ONTOLOGY_GRAPH = "business_ontology"
SCHEMA_FILE = Path(__file__).parent.parent.parent / "config" / "graphs" / "business_ontology.cypher"


def _escape(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.replace("'", "''")


def _clean_agtype(val) -> Optional[str]:
    """Strip agtype quotes and ::type suffix from AGE return values."""
    if val is None:
        return None
    s = str(val).strip('"').strip("'")
    # Remove AGE type suffixes like ::vertex, ::text
    if "::" in s:
        s = s.split("::")[0].strip('"').strip("'")
    return s if s and s != "null" else None


@dataclass
class EntityType:
    """An entity type definition from the ontology."""
    name: str
    display_name: str
    category: str  # "document", "entity", "process"
    parent: Optional[str] = None
    sector: Optional[str] = None
    description: str = ""


@dataclass
class RelationType:
    """A relation type definition from the ontology."""
    name: str
    display_name: str
    source_type: str
    target_type: str
    sector: Optional[str] = None
    description: str = ""


class OntologyService:
    """
    Service for the shared business ontology graph.

    Provides:
    - Type resolution (semantic_type → EntityType)
    - Hierarchy traversal (ancestors/descendants)
    - Relation validation (what edges are valid between types)
    - In-memory cache for fast lookups (ontology is small and static)
    """

    def __init__(self):
        self._initialized = False
        self._types_cache: Dict[str, EntityType] = {}
        self._relations_cache: List[RelationType] = []

    async def initialize(self) -> None:
        """Initialize the ontology graph and load cache."""
        if self._initialized:
            return

        await age_client.initialize()
        if not age_client._pool:
            logger.warning("AGE client not available — ontology service disabled")
            self._initialized = True
            return

        await self._ensure_graph()
        await self._load_cache()
        self._initialized = True
        logger.info(
            f"Ontology service ready: {len(self._types_cache)} types, "
            f"{len(self._relations_cache)} relations"
        )

    async def _ensure_graph(self) -> None:
        """Create the ontology graph if it doesn't exist."""
        async with age_client._get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT count(*) as cnt FROM ag_catalog.ag_graph WHERE name = $1",
                ONTOLOGY_GRAPH,
            )
            if row and row["cnt"] > 0:
                logger.info(f"Ontology graph '{ONTOLOGY_GRAPH}' exists")
                return

        # Bootstrap from schema file
        if not SCHEMA_FILE.exists():
            logger.error(f"Ontology schema file not found: {SCHEMA_FILE}")
            return

        logger.info(f"Bootstrapping ontology graph from {SCHEMA_FILE.name}...")
        content = SCHEMA_FILE.read_text()
        statements = [
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("--") and line.strip().endswith(";")
        ]

        async with age_client._get_connection() as conn:
            for stmt in statements:
                try:
                    await conn.execute(stmt)
                except Exception as e:
                    if "already exists" in str(e):
                        pass
                    else:
                        logger.error(f"Ontology bootstrap error: {stmt[:60]}... {e}")

        logger.info(f"Ontology graph '{ONTOLOGY_GRAPH}' bootstrapped")

    async def _load_cache(self) -> None:
        """Load all entity types and relation types into memory."""
        # Load EntityTypes
        try:
            query = f"""
            SELECT * FROM cypher('{ONTOLOGY_GRAPH}', $$
                MATCH (t:EntityType)
                RETURN t.name, t.display_name, t.category, t.parent, t.sector, t.description
            $$) as (name agtype, display_name agtype, category agtype, parent agtype, sector agtype, description agtype)
            """
            rows = await age_client.execute_cypher(query)
            self._types_cache = {}
            for row in rows:
                name = _clean_agtype(row.get("name"))
                if not name:
                    continue
                self._types_cache[name] = EntityType(
                    name=name,
                    display_name=_clean_agtype(row.get("display_name")) or name,
                    category=_clean_agtype(row.get("category")) or "document",
                    parent=_clean_agtype(row.get("parent")),
                    sector=_clean_agtype(row.get("sector")),
                    description=_clean_agtype(row.get("description")) or "",
                )
        except Exception as e:
            logger.warning(f"Failed to load EntityTypes: {e}")

        # Load RelationTypes
        try:
            query = f"""
            SELECT * FROM cypher('{ONTOLOGY_GRAPH}', $$
                MATCH (r:RelationType)
                RETURN r.name, r.display_name, r.source_type, r.target_type, r.sector, r.description
            $$) as (name agtype, display_name agtype, source_type agtype, target_type agtype, sector agtype, description agtype)
            """
            rows = await age_client.execute_cypher(query)
            self._relations_cache = []
            for row in rows:
                name = _clean_agtype(row.get("name"))
                if not name:
                    continue
                self._relations_cache.append(RelationType(
                    name=name,
                    display_name=_clean_agtype(row.get("display_name")) or name,
                    source_type=_clean_agtype(row.get("source_type")) or "",
                    target_type=_clean_agtype(row.get("target_type")) or "",
                    sector=_clean_agtype(row.get("sector")),
                    description=_clean_agtype(row.get("description")) or "",
                ))
        except Exception as e:
            logger.warning(f"Failed to load RelationTypes: {e}")

    # ─── Public API ───────────────────────────────────────────────

    def resolve_type(self, semantic_type: str) -> Optional[EntityType]:
        """
        Resolve a semantic_type string to its EntityType definition.

        This is the primary lookup used by structural_indexer to create
        INSTANCE_OF edges. Returns None if the type is unknown.
        """
        return self._types_cache.get(semantic_type)

    def get_type_ancestors(self, type_name: str) -> List[str]:
        """
        Get the ancestor chain for a type (child → parent → grandparent).

        Example: get_type_ancestors("factura")
                 → ["financial_document", "document"]
        """
        ancestors = []
        current = type_name
        seen = set()
        while current:
            et = self._types_cache.get(current)
            if not et or not et.parent or et.parent in seen:
                break
            ancestors.append(et.parent)
            seen.add(et.parent)
            current = et.parent
        return ancestors

    def get_type_descendants(self, type_name: str) -> List[str]:
        """
        Get all descendant types of a given type.

        Example: get_type_descendants("financial_document")
                 → ["factura", "nomina", "presupuesto", "albaran", "pedido", "recibo"]
        """
        descendants = []
        for et in self._types_cache.values():
            if self._is_descendant_of(et.name, type_name):
                descendants.append(et.name)
        return descendants

    def _is_descendant_of(self, child: str, ancestor: str) -> bool:
        """Check if child is a descendant of ancestor in the type hierarchy."""
        if child == ancestor:
            return False
        current = child
        seen = set()
        while current:
            et = self._types_cache.get(current)
            if not et or not et.parent or et.parent in seen:
                return False
            if et.parent == ancestor:
                return True
            seen.add(et.parent)
            current = et.parent
        return False

    def get_types_by_category(self, category: str) -> List[EntityType]:
        """Get all types in a category ('document', 'entity', 'process')."""
        return [et for et in self._types_cache.values() if et.category == category]

    def get_types_for_sector(self, sector: Optional[str]) -> List[EntityType]:
        """
        Get types available for a sector.
        Returns universal types (sector=None) + sector-specific types.
        """
        return [
            et for et in self._types_cache.values()
            if et.sector is None or et.sector == sector
        ]

    def get_valid_relations(
        self,
        source_type: Optional[str] = None,
        target_type: Optional[str] = None,
        sector: Optional[str] = None,
    ) -> List[RelationType]:
        """
        Get valid relation types, optionally filtered.

        Matches are inclusive: a relation defined for source_type='document'
        also applies to descendants like 'factura' or 'contrato'.
        """
        results = []
        for rel in self._relations_cache:
            if sector and rel.sector and rel.sector != sector:
                continue
            if source_type:
                if not (
                    rel.source_type == source_type
                    or self._is_descendant_of(source_type, rel.source_type)
                ):
                    continue
            if target_type:
                if not (
                    rel.target_type == target_type
                    or self._is_descendant_of(target_type, rel.target_type)
                ):
                    continue
            results.append(rel)
        return results

    def get_all_types(self) -> List[EntityType]:
        """Return all entity types."""
        return list(self._types_cache.values())

    def get_all_relations(self) -> List[RelationType]:
        """Return all relation types."""
        return list(self._relations_cache)

    async def add_entity_type(
        self,
        name: str,
        display_name: str,
        category: str,
        parent: Optional[str] = None,
        sector: Optional[str] = None,
        description: str = "",
    ) -> bool:
        """
        Add a new entity type to the ontology at runtime.
        Updates the in-memory cache after insertion.
        """
        if name in self._types_cache:
            return True  # Already exists

        props = [
            f"name: '{_escape(name)}'",
            f"display_name: '{_escape(display_name)}'",
            f"category: '{_escape(category)}'",
        ]
        if parent:
            props.append(f"parent: '{_escape(parent)}'")
        if sector:
            props.append(f"sector: '{_escape(sector)}'")
        if description:
            props.append(f"description: '{_escape(description)}'")

        cypher = f"""
        SELECT * FROM cypher('{ONTOLOGY_GRAPH}', $$
            MERGE (t:EntityType {{name: '{_escape(name)}'}})
            SET {', '.join(f't.{p.split(":")[0].strip()} = {p.split(":", 1)[1].strip()}' for p in props[1:])}
            RETURN t.name
        $$) as (name agtype)
        """
        try:
            await age_client.execute_cypher(cypher)
            self._types_cache[name] = EntityType(
                name=name,
                display_name=display_name,
                category=category,
                parent=parent,
                sector=sector,
                description=description,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to add entity type '{name}': {e}")
            return False

    async def add_relation_type(
        self,
        name: str,
        display_name: str,
        source_type: str,
        target_type: str,
        sector: Optional[str] = None,
        description: str = "",
    ) -> bool:
        """Add a new relation type to the ontology at runtime."""
        # Check if already exists
        for rel in self._relations_cache:
            if rel.name == name and rel.source_type == source_type and rel.target_type == target_type:
                return True

        props = {
            "name": name,
            "display_name": display_name,
            "source_type": source_type,
            "target_type": target_type,
        }
        if sector:
            props["sector"] = sector
        if description:
            props["description"] = description

        set_parts = ", ".join(f"r.{k} = '{_escape(v)}'" for k, v in props.items())

        cypher = f"""
        SELECT * FROM cypher('{ONTOLOGY_GRAPH}', $$
            MERGE (r:RelationType {{name: '{_escape(name)}', source_type: '{_escape(source_type)}', target_type: '{_escape(target_type)}'}})
            SET {set_parts}
            RETURN r.name
        $$) as (name agtype)
        """
        try:
            await age_client.execute_cypher(cypher)
            self._relations_cache.append(RelationType(
                name=name,
                display_name=display_name,
                source_type=source_type,
                target_type=target_type,
                sector=sector,
                description=description,
            ))
            return True
        except Exception as e:
            logger.error(f"Failed to add relation type '{name}': {e}")
            return False

    def get_ontology_summary(self) -> Dict:
        """Get a summary of the ontology for API/debug."""
        docs = [et for et in self._types_cache.values() if et.category == "document"]
        entities = [et for et in self._types_cache.values() if et.category == "entity"]
        processes = [et for et in self._types_cache.values() if et.category == "process"]
        return {
            "total_types": len(self._types_cache),
            "total_relations": len(self._relations_cache),
            "document_types": len(docs),
            "entity_types": len(entities),
            "process_types": len(processes),
            "types": {
                name: {
                    "display_name": et.display_name,
                    "category": et.category,
                    "parent": et.parent,
                    "sector": et.sector,
                }
                for name, et in sorted(self._types_cache.items())
            },
            "relations": [
                {
                    "name": r.name,
                    "source": r.source_type,
                    "target": r.target_type,
                    "sector": r.sector,
                }
                for r in self._relations_cache
            ],
        }


# Singleton
ontology_service = OntologyService()
