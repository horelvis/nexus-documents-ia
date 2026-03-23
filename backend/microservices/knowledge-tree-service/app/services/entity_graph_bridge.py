"""
Entity Graph Bridge (FalkorDB)

Receives normalized entities from the indexing pipeline (weaviate-service)
and persists them as :Entity nodes in the knowledge graph (FalkorDB),
with :INSTANCE_OF edges linking to the shared business ontology.

All entity types use a single :Entity label with an `entity_type` property,
replacing the per-type vlabels (Persona, Organizacion, etc.) from AGE.

Flow:
    weaviate-service (indexing_pipeline)
        -> langextract_client.extract_entities()
        -> extraction_service.extract_from_document()
        -> HTTP POST /tree/entities/store
        -> EntityGraphBridge.store_entities()
        -> FalkorDB knowledge graph (:Entity nodes)
           + :MENTIONED_IN -> :Document (provenance)

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
from app.services.falkordb_client import falkordb_client

logger = logging.getLogger(__name__)


# Maps extraction entity types to unified entity_type values.
# All become :Entity nodes with entity_type property.
_TYPE_TO_ENTITY_TYPE: Dict[str, str] = {
    # Person types
    "person": "person",
    "empleado": "person",
    "trabajador": "person",
    "representante": "person",
    "firmante": "person",
    # Organization types
    "organization": "organization",
    "organizacion": "organization",
    "empresa": "organization",
    "compania": "organization",
    "sociedad": "organization",
    "entidad": "organization",
    # Legal types
    "ley": "law",
    "real_decreto": "law",
    "reference": "law",
    "normativa": "law",
    "articulo": "clause",
    "clause": "clause",
    "concepto_legal": "concept",
    "concept": "concept",
    "termino": "concept",
    "term": "concept",
    "boe_referencia": "law",
    # Contract types
    "contrato": "contract",
    # Medical types
    "farmaco": "medication",
    "medicamento": "medication",
    "diagnostico": "diagnosis",
}

class EntityGraphBridge:
    """
    Bridges extracted entities into the FalkorDB knowledge graph.

    Creates :Entity nodes with entity_type property and links them to
    the source document via :MENTIONED_IN edges (with provenance).
    Entity type is stored as a string property on the node.
    """

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        await falkordb_client.initialize()
        self._initialized = True

    async def store_entities(
        self,
        tenant_id: str,
        document_id: str,
        entities: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Store extracted entities as :Entity nodes linked to a :Document.

        Each entity becomes an :Entity node with edges:
        - (entity)-[:MENTIONED_IN {extraction_method, confidence}]->(Document)

        Args:
            tenant_id: Tenant identifier
            document_id: Source document ID
            entities: List of dicts with keys: type, value, confidence, attributes

        Returns:
            Summary with counts of stored nodes and edges
        """
        if not self._initialized:
            await self.initialize()

        graph_name = settings.falkordb_graph_name
        if not graph_name:
            return {"success": False, "error": "No graph configured"}

        stored = 0
        skipped = 0
        errors = []

        for entity in entities:
            raw_type = (entity.get("type") or "").lower().strip()
            entity_value = (entity.get("value") or "").strip()
            confidence = entity.get("confidence", 0.8)

            if not entity_value or len(entity_value) < 2:
                skipped += 1
                continue

            entity_type = _TYPE_TO_ENTITY_TYPE.get(raw_type)
            if not entity_type:
                # Unknown entity type -- skip (dates, amounts, etc. stay in Weaviate only)
                skipped += 1
                continue

            try:
                await self._upsert_entity_node(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    entity_value=entity_value,
                    entity_type=entity_type,
                    confidence=confidence,
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
        Store extracted relationships as :RELATED_TO edges between :Entity nodes.

        Only creates edges between nodes that already exist in the graph
        (created by store_entities).

        Args:
            tenant_id: Tenant identifier
            document_id: Source document ID
            relationships: List of dicts with keys: source, target, type, strength
        """
        if not self._initialized:
            await self.initialize()

        graph_name = settings.falkordb_graph_name
        if not graph_name:
            return {"success": False, "error": "No graph configured"}

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

            try:
                cypher = """
                    MATCH (s:Entity {tenant_id: $tenant_id, name: $source})
                    MATCH (t:Entity {tenant_id: $tenant_id, name: $target})
                    MERGE (s)-[r:RELATED_TO {relation_type: $rel_type}]->(t)
                    SET r.strength = $strength,
                        r.document_id = $document_id
                    RETURN id(r) AS edge_id
                """
                await falkordb_client.execute_cypher(cypher, {
                    "tenant_id": tenant_id,
                    "source": source_value,
                    "target": target_value,
                    "rel_type": rel_type,
                    "strength": strength,
                    "document_id": document_id,
                })
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
        graph_name = settings.falkordb_graph_name
        if not graph_name:
            return []

        try:
            cypher = """
                MATCH (e:Entity)-[:MENTIONED_IN]->(d:Document {
                    tenant_id: $tenant_id,
                    document_id: $document_id
                })
                RETURN e.entity_type AS entity_type, e.name AS name,
                       e.confidence AS confidence
            """
            rows = await falkordb_client.execute_cypher(cypher, {
                "tenant_id": tenant_id,
                "document_id": document_id,
            })
            return [
                {
                    "entity_type": r.get("entity_type"),
                    "name": r.get("name"),
                    "confidence": r.get("confidence"),
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
        Search for an entity and its neighborhood in the knowledge graph.

        Used by SmartSearch for graph-based query expansion.
        """
        graph_name = settings.falkordb_graph_name
        if not graph_name:
            return {"entity": None, "neighbors": [], "documents": []}

        try:
            # Build optional entity_type filter
            type_filter = ""
            params: Dict[str, Any] = {
                "tenant_id": tenant_id,
                "entity_value": entity_value,
            }
            if entity_type:
                mapped = _TYPE_TO_ENTITY_TYPE.get(entity_type.lower())
                if mapped:
                    type_filter = ", entity_type: $entity_type_filter"
                    params["entity_type_filter"] = mapped

            # Get entity + connected documents
            cypher = f"""
                MATCH (e:Entity {{tenant_id: $tenant_id, name: $entity_value{type_filter}}})
                OPTIONAL MATCH (e)-[:MENTIONED_IN]->(d:Document)
                RETURN e.name AS name, e.entity_type AS entity_type,
                       collect(DISTINCT d.document_id) AS document_ids
            """
            rows = await falkordb_client.execute_cypher(cypher, params)

            if not rows:
                return {"entity": None, "neighbors": [], "documents": []}

            row = rows[0]

            # Get neighbors (entities connected within max_depth hops)
            neighbor_params: Dict[str, Any] = {
                "tenant_id": tenant_id,
                "entity_value": entity_value,
                "limit": limit,
            }
            neighbor_cypher = f"""
                MATCH (e:Entity {{tenant_id: $tenant_id, name: $entity_value}})
                      -[*1..{max_depth}]-(neighbor:Entity)
                WHERE neighbor.tenant_id = $tenant_id
                  AND neighbor.name <> $entity_value
                RETURN DISTINCT neighbor.name AS name, neighbor.entity_type AS entity_type
                LIMIT $limit
            """
            neighbor_rows = await falkordb_client.execute_cypher(neighbor_cypher, neighbor_params)

            return {
                "entity": {
                    "name": row.get("name"),
                    "type": row.get("entity_type"),
                },
                "neighbors": [
                    {
                        "name": nr.get("name"),
                        "entity_type": nr.get("entity_type"),
                    }
                    for nr in neighbor_rows
                ],
                "documents": row.get("document_ids", []),
            }
        except Exception as e:
            logger.warning(f"Entity search failed: {e}")
            return {"entity": None, "neighbors": [], "documents": []}

    # --- Internal ---

    async def _upsert_entity_node(
        self,
        tenant_id: str,
        document_id: str,
        entity_value: str,
        entity_type: str,
        confidence: float,
    ) -> None:
        """
        MERGE an :Entity node and link it to the source :Document.

        Creates:
        - :Entity node with name, entity_type, confidence
        - :MENTIONED_IN edge to :Document (with extraction_method + confidence)
        """
        params: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "document_id": document_id,
            "entity_value": entity_value,
            "entity_type": entity_type,
            "confidence": confidence,
        }

        # For public_knowledge entities, Document nodes may not exist
        # in the graph -- create entity without MENTIONED_IN edge
        if tenant_id == "public_knowledge":
            cypher = """
                MERGE (e:Entity {tenant_id: $tenant_id, name: $entity_value})
                SET e.entity_type = $entity_type,
                    e.confidence = $confidence,
                    e.source_document_id = $document_id,
                    e.shared = true
                RETURN e.name AS name
            """
        else:
            cypher = """
                MERGE (e:Entity {tenant_id: $tenant_id, name: $entity_value})
                SET e.entity_type = $entity_type,
                    e.confidence = $confidence
                WITH e
                MATCH (d:Document {tenant_id: $tenant_id, document_id: $document_id})
                MERGE (e)-[:MENTIONED_IN {extraction_method: 'entity_extraction', confidence: $confidence}]->(d)
                RETURN e.name AS name
            """
        await falkordb_client.execute_cypher(cypher, params)


# Singleton
entity_graph_bridge = EntityGraphBridge()
