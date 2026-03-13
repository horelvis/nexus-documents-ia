"""
Entity Graph Bridge

Receives normalized entities from the indexing pipeline (weaviate-service)
and persists them as typed nodes in the tenant's sector graph (Apache AGE),
with INSTANCE_OF edges linking to the shared business ontology.

This replaces the NetworkX graph_service and the disconnected AGE
knowledge_graph as the single destination for extracted entities.

Flow:
    weaviate-service (indexing_pipeline)
        → langextract_client.extract_entities()
        → extraction_service.extract_from_document()
        → HTTP POST /tree/entities/store
        → EntityGraphBridge.store_entities()
        → Apache AGE sector graph (Persona, Organizacion, etc.)
           + INSTANCE_OF → EntityType (ontology proxy)
           + EXTRACTED_FROM → structural_document

Usage:
    from app.services.entity_graph_bridge import entity_graph_bridge

    await entity_graph_bridge.store_entities(
        tenant_id="tenant-123",
        document_id="doc-456",
        entities=[
            {"type": "person", "value": "Juan Garcia", "confidence": 0.9},
            {"type": "organization", "value": "ACME Corp", "confidence": 0.85},
        ],
    )
"""

import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.age_client import age_client
from app.services.ontology_service import ontology_service

logger = logging.getLogger(__name__)


def _escape(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.replace("'", "''")


# Maps extraction entity types (from KnowledgeExtractionService) to
# sector graph vlabels and ontology EntityType names.
_TYPE_TO_VLABEL: Dict[str, str] = {
    # Person types
    "person": "Persona",
    "empleado": "Persona",
    "trabajador": "Persona",
    "representante": "Persona",
    "firmante": "Persona",
    # Organization types
    "organization": "Organizacion",
    "organizacion": "Organizacion",
    "empresa": "Organizacion",
    "compania": "Organizacion",
    "sociedad": "Organizacion",
    "entidad": "Organizacion",
}

_TYPE_TO_ONTOLOGY: Dict[str, str] = {
    "person": "person",
    "empleado": "employee",
    "trabajador": "employee",
    "representante": "person",
    "firmante": "person",
    "organization": "organization",
    "organizacion": "organization",
    "empresa": "company",
    "compania": "company",
    "sociedad": "company",
    "entidad": "organization",
}

# Extraction relationship types → sector graph edge labels
_REL_TO_ELABEL: Dict[str, str] = {
    "belongs_to": "PERTENECE_A",
    "involves": "ASOCIADO_A",
    "mentions": "ASOCIADO_A",
    "defines": "DEFINE",
    "references": "REFERENCIA",
    "relates_to": "RELACIONADO",
    "part_of": "PARTE_DE",
}


class EntityGraphBridge:
    """
    Bridges extracted entities into the tenant sector graph.

    Creates typed nodes (Persona, Organizacion) in the sector graph
    and links them to:
    - The source document via EXTRACTED_FROM edges
    - The ontology via INSTANCE_OF edges to EntityType proxy nodes
    """

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        await age_client.initialize()
        if not ontology_service._initialized:
            await ontology_service.initialize()
        self._initialized = True

    async def store_entities(
        self,
        tenant_id: str,
        document_id: str,
        entities: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Store extracted entities as graph nodes linked to a document.

        Each entity becomes a typed node (Persona, Organizacion, etc.)
        with edges:
        - (entity)-[:EXTRACTED_FROM]->(structural_document)
        - (entity)-[:INSTANCE_OF]->(EntityType)

        Args:
            tenant_id: Tenant identifier
            document_id: Source document ID
            entities: List of dicts with keys: type, value, confidence, attributes

        Returns:
            Summary with counts of stored nodes and edges
        """
        if not self._initialized:
            await self.initialize()

        if not age_client._pool:
            return {"success": False, "error": "AGE client not available"}

        graph = settings.age_graph_name
        if not graph:
            return {"success": False, "error": "No sector graph configured"}

        stored = 0
        skipped = 0
        errors = []

        for entity in entities:
            entity_type = (entity.get("type") or "").lower().strip()
            entity_value = (entity.get("value") or "").strip()
            confidence = entity.get("confidence", 0.8)

            if not entity_value or len(entity_value) < 2:
                skipped += 1
                continue

            vlabel = _TYPE_TO_VLABEL.get(entity_type)
            if not vlabel:
                # Unknown entity type — skip (dates, amounts, etc. stay in Weaviate only)
                skipped += 1
                continue

            ontology_type = _TYPE_TO_ONTOLOGY.get(entity_type)

            try:
                await self._upsert_entity_node(
                    graph=graph,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    vlabel=vlabel,
                    entity_value=entity_value,
                    entity_type=entity_type,
                    confidence=confidence,
                    ontology_type=ontology_type,
                )
                stored += 1
            except Exception as e:
                logger.warning(f"Failed to store entity '{entity_value}': {e}")
                errors.append(f"{entity_value}: {str(e)[:100]}")

        if stored:
            logger.info(
                f"EntityGraphBridge: stored {stored} entities for doc {document_id} "
                f"(skipped {skipped}, errors {len(errors)})"
            )

        return {
            "success": True,
            "stored": stored,
            "skipped": skipped,
            "errors": errors,
        }

    async def store_relationships(
        self,
        tenant_id: str,
        document_id: str,
        relationships: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Store extracted relationships as edges between entity nodes.

        Only creates edges between nodes that already exist in the graph
        (created by store_entities).

        Args:
            tenant_id: Tenant identifier
            document_id: Source document ID
            relationships: List of dicts with keys: source, target, type, strength
        """
        if not self._initialized:
            await self.initialize()

        if not age_client._pool:
            return {"success": False, "error": "AGE client not available"}

        graph = settings.age_graph_name
        if not graph:
            return {"success": False, "error": "No sector graph configured"}

        stored = 0
        skipped = 0

        for rel in relationships:
            source_value = (rel.get("source") or "").strip()
            target_value = (rel.get("target") or "").strip()
            rel_type = (rel.get("type") or "relates_to").lower()
            strength = rel.get("strength", 0.5)

            if not source_value or not target_value:
                skipped += 1
                continue

            elabel = _REL_TO_ELABEL.get(rel_type, "RELACIONADO")

            try:
                cypher = f"""
                SELECT * FROM cypher('{graph}', $$
                    MATCH (s {{tenant_id: '{_escape(tenant_id)}', name: '{_escape(source_value)}'}})
                    MATCH (t {{tenant_id: '{_escape(tenant_id)}', name: '{_escape(target_value)}'}})
                    MERGE (s)-[r:{elabel}]->(t)
                    SET r.strength = {strength},
                        r.document_id = '{_escape(document_id)}'
                    RETURN id(r)
                $$) as (edge_id agtype)
                """
                await age_client.execute_cypher(cypher)
                stored += 1
            except Exception as e:
                logger.debug(f"Failed to store relationship {source_value}->{target_value}: {e}")
                skipped += 1

        return {"success": True, "stored": stored, "skipped": skipped}

    async def get_document_entities(
        self,
        tenant_id: str,
        document_id: str,
    ) -> List[Dict[str, Any]]:
        """Get all entities extracted from a document."""
        if not age_client._pool:
            return []

        graph = settings.age_graph_name
        if not graph:
            return []

        try:
            cypher = f"""
            SELECT * FROM cypher('{graph}', $$
                MATCH (e)-[:EXTRACTED_FROM]->(d:structural_document {{
                    tenant_id: '{_escape(tenant_id)}',
                    document_id: '{_escape(document_id)}'
                }})
                OPTIONAL MATCH (e)-[:INSTANCE_OF]->(et:EntityType)
                RETURN labels(e)[0] as vlabel, e.name as name,
                       e.entity_type as entity_type, e.confidence as confidence,
                       et.name as ontology_type
            $$) as (vlabel agtype, name agtype, entity_type agtype, confidence agtype, ontology_type agtype)
            """
            rows = await age_client.execute_cypher(cypher)
            from app.services.ontology_service import _clean_agtype
            return [
                {
                    "vlabel": _clean_agtype(r.get("vlabel")),
                    "name": _clean_agtype(r.get("name")),
                    "entity_type": _clean_agtype(r.get("entity_type")),
                    "confidence": _clean_agtype(r.get("confidence")),
                    "ontology_type": _clean_agtype(r.get("ontology_type")),
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"Failed to get document entities: {e}")
            return []

    async def search_entity(
        self,
        tenant_id: str,
        entity_value: str,
        entity_type: Optional[str] = None,
        max_depth: int = 2,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Search for an entity and its neighborhood in the sector graph.

        Used by SmartSearch for graph-based query expansion.
        """
        if not age_client._pool:
            return {"entity": None, "neighbors": [], "documents": []}

        graph = settings.age_graph_name
        if not graph:
            return {"entity": None, "neighbors": [], "documents": []}

        try:
            # Find the entity node
            vlabel_filter = ""
            if entity_type:
                vlabel = _TYPE_TO_VLABEL.get(entity_type.lower())
                if vlabel:
                    vlabel_filter = f":{vlabel}"

            # Get entity + connected documents
            cypher = f"""
            SELECT * FROM cypher('{graph}', $$
                MATCH (e{vlabel_filter} {{tenant_id: '{_escape(tenant_id)}', name: '{_escape(entity_value)}'}})
                OPTIONAL MATCH (e)-[:EXTRACTED_FROM]->(d:structural_document)
                RETURN e.name as name, e.entity_type as entity_type,
                       collect(DISTINCT d.document_id) as document_ids
            $$) as (name agtype, entity_type agtype, document_ids agtype)
            """
            rows = await age_client.execute_cypher(cypher)

            from app.services.ontology_service import _clean_agtype
            if not rows:
                return {"entity": None, "neighbors": [], "documents": []}

            row = rows[0]
            entity_name = _clean_agtype(row.get("name"))

            # Get neighbors (entities connected to the same documents or directly)
            neighbor_cypher = f"""
            SELECT * FROM cypher('{graph}', $$
                MATCH (e {{tenant_id: '{_escape(tenant_id)}', name: '{_escape(entity_value)}'}})
                      -[*1..{max_depth}]-(neighbor)
                WHERE neighbor.tenant_id = '{_escape(tenant_id)}'
                  AND neighbor.name <> '{_escape(entity_value)}'
                RETURN DISTINCT neighbor.name as name, labels(neighbor)[0] as vlabel
                LIMIT {limit}
            $$) as (name agtype, vlabel agtype)
            """
            neighbor_rows = await age_client.execute_cypher(neighbor_cypher)

            return {
                "entity": {
                    "name": entity_name,
                    "type": _clean_agtype(row.get("entity_type")),
                },
                "neighbors": [
                    {
                        "name": _clean_agtype(nr.get("name")),
                        "vlabel": _clean_agtype(nr.get("vlabel")),
                    }
                    for nr in neighbor_rows
                ],
                "documents": str(row.get("document_ids", "[]")),
            }
        except Exception as e:
            logger.warning(f"Entity search failed: {e}")
            return {"entity": None, "neighbors": [], "documents": []}

    # ─── Internal ─────────────────────────────────────────────

    async def _upsert_entity_node(
        self,
        graph: str,
        tenant_id: str,
        document_id: str,
        vlabel: str,
        entity_value: str,
        entity_type: str,
        confidence: float,
        ontology_type: Optional[str],
    ) -> None:
        """
        MERGE a typed entity node and link it to the source document.

        Creates:
        - (Persona/Organizacion) node with name, entity_type, confidence
        - EXTRACTED_FROM edge to structural_document
        - INSTANCE_OF edge to EntityType (ontology proxy)
        """
        # Build INSTANCE_OF clause if ontology type is known
        instance_of_merge = ""
        instance_of_edge = ""
        if ontology_type:
            resolved = ontology_service.resolve_type(ontology_type)
            if resolved:
                instance_of_merge = (
                    f"MERGE (et:EntityType {{name: '{_escape(resolved.name)}'}})"
                    f" SET et.display_name = '{_escape(resolved.display_name)}'"
                    f", et.category = '{_escape(resolved.category)}'"
                )
                if resolved.parent:
                    instance_of_merge += f", et.parent = '{_escape(resolved.parent)}'"
                instance_of_edge = f"MERGE (e)-[:INSTANCE_OF]->(et)"

        cypher = f"""
        SELECT * FROM cypher('{graph}', $$
            MERGE (e:{vlabel} {{tenant_id: '{_escape(tenant_id)}', name: '{_escape(entity_value)}'}})
            SET e.entity_type = '{_escape(entity_type)}',
                e.confidence = {confidence}
            WITH e
            MATCH (d:structural_document {{tenant_id: '{_escape(tenant_id)}', document_id: '{_escape(document_id)}'}})
            MERGE (e)-[:EXTRACTED_FROM]->(d)
            {instance_of_merge}
            {instance_of_edge}
            RETURN e.name
        $$) as (name agtype)
        """
        await age_client.execute_cypher(cypher)


# Singleton
entity_graph_bridge = EntityGraphBridge()
