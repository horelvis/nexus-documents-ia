"""
Business Ontology API

Endpoints for querying the shared business ontology: entity types,
relation types, type hierarchy, and ontology management.
"""

import logging
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

logger = logging.getLogger(__name__)

from app.services.ontology_service import ontology_service
from app.services.age_client import age_client
from app.core.config import settings

router = APIRouter(prefix="/ontology", tags=["business-ontology"])


@router.get("/types")
async def list_entity_types(
    category: Optional[str] = Query(None, description="Filter by category: document, entity, process"),
    sector: Optional[str] = Query(None, description="Filter by sector: legal, medical, documental"),
):
    """List all entity types, optionally filtered by category or sector."""
    if sector:
        types = ontology_service.get_types_for_sector(sector)
    elif category:
        types = ontology_service.get_types_by_category(category)
    else:
        types = ontology_service.get_all_types()

    return [
        {
            "name": t.name,
            "display_name": t.display_name,
            "category": t.category,
            "parent": t.parent,
            "sector": t.sector,
            "description": t.description,
        }
        for t in types
    ]


@router.get("/types/{type_name}")
async def get_entity_type(type_name: str):
    """Get a specific entity type by name."""
    et = ontology_service.resolve_type(type_name)
    if not et:
        raise HTTPException(status_code=404, detail=f"Entity type '{type_name}' not found")
    return {
        "name": et.name,
        "display_name": et.display_name,
        "category": et.category,
        "parent": et.parent,
        "sector": et.sector,
        "description": et.description,
    }


@router.get("/types/{type_name}/ancestors")
async def get_type_ancestors(type_name: str):
    """Get the ancestor chain for a type (e.g., factura → financial_document → document)."""
    et = ontology_service.resolve_type(type_name)
    if not et:
        raise HTTPException(status_code=404, detail=f"Entity type '{type_name}' not found")
    ancestors = ontology_service.get_type_ancestors(type_name)
    return {"type": type_name, "ancestors": ancestors}


@router.get("/types/{type_name}/descendants")
async def get_type_descendants(type_name: str):
    """Get all descendant types (e.g., financial_document → [factura, nomina, ...])."""
    et = ontology_service.resolve_type(type_name)
    if not et:
        raise HTTPException(status_code=404, detail=f"Entity type '{type_name}' not found")
    descendants = ontology_service.get_type_descendants(type_name)
    return {"type": type_name, "descendants": descendants}


@router.get("/relations")
async def list_relation_types(
    source_type: Optional[str] = Query(None, description="Filter by source entity type"),
    target_type: Optional[str] = Query(None, description="Filter by target entity type"),
    sector: Optional[str] = Query(None, description="Filter by sector"),
):
    """List valid relation types between entity types."""
    relations = ontology_service.get_valid_relations(
        source_type=source_type,
        target_type=target_type,
        sector=sector,
    )
    return [
        {
            "name": r.name,
            "display_name": r.display_name,
            "source_type": r.source_type,
            "target_type": r.target_type,
            "sector": r.sector,
            "description": r.description,
        }
        for r in relations
    ]


@router.get("/summary")
async def get_ontology_summary():
    """Get a summary of the entire ontology (types, relations, counts)."""
    return ontology_service.get_ontology_summary()


@router.get("/hierarchy")
async def get_type_hierarchy():
    """Get the full type hierarchy as a tree structure."""
    all_types = ontology_service.get_all_types()

    # Build tree by category
    tree = {}
    for et in all_types:
        if et.category not in tree:
            tree[et.category] = []

    # Roots first, then children
    type_map = {et.name: et for et in all_types}
    roots = [et for et in all_types if et.parent is None]

    def _build_subtree(node: "EntityType") -> dict:
        children = [et for et in all_types if et.parent == node.name]
        result = {
            "name": node.name,
            "display_name": node.display_name,
            "sector": node.sector,
        }
        if children:
            result["children"] = [_build_subtree(c) for c in children]
        return result

    return {
        category: [_build_subtree(r) for r in roots if r.category == category]
        for category in ["document", "entity", "process"]
    }


@router.get("/document-context/{document_id}")
async def get_document_ontology_context(
    document_id: str,
    tenant_id: str = Query(..., description="Tenant identifier"),
):
    """
    Get full ontology context for a document, bridging sector graph and public graph.

    Returns:
    - Structural info (folder, semantic_type, associated_person) from sector graph
    - Ontology type info (display_name, ancestors) from business_ontology
    - Applicable laws from knowledge_graph_public
    """
    graph = settings.age_graph_name
    if not graph or not age_client._pool:
        raise HTTPException(status_code=503, detail="Knowledge graph not available")

    result = {
        "document_id": document_id,
        "tenant_id": tenant_id,
        "structural": None,
        "ontology": None,
        "applicable_laws": [],
    }

    doc_escaped = document_id.replace("'", "''")
    tenant_escaped = tenant_id.replace("'", "''")

    # 1. Query sector graph for structural info
    try:
        cypher = f"""
        SELECT * FROM cypher('{graph}', $$
            MATCH (d:structural_document {{document_id: '{doc_escaped}', tenant_id: '{tenant_escaped}'}})
            OPTIONAL MATCH (d)-[:INSTANCE_OF]->(et:EntityType)
            OPTIONAL MATCH (d)-[:ASOCIADO_A]->(p:Persona)
            OPTIONAL MATCH (f:structural_folder)-[:HAS_DOCUMENT]->(d)
            RETURN d.semantic_type as semantic_type, d.domain as domain,
                   d.title as title, d.folder_path as folder_path,
                   et.name as ontology_type, et.display_name as type_display_name,
                   p.name as person_name, f.folder_type as folder_type
        $$) as (semantic_type agtype, domain agtype, title agtype, folder_path agtype,
                ontology_type agtype, type_display_name agtype, person_name agtype, folder_type agtype)
        """
        rows = await age_client.execute_cypher(cypher)
        if rows:
            row = rows[0]
            from app.services.ontology_service import _clean_agtype
            semantic_type = _clean_agtype(row.get("semantic_type"))
            ontology_type = _clean_agtype(row.get("ontology_type"))

            result["structural"] = {
                "title": _clean_agtype(row.get("title")),
                "semantic_type": semantic_type,
                "domain": _clean_agtype(row.get("domain")),
                "folder_path": _clean_agtype(row.get("folder_path")),
                "folder_type": _clean_agtype(row.get("folder_type")),
                "associated_person": _clean_agtype(row.get("person_name")),
            }

            if ontology_type:
                ancestors = ontology_service.get_type_ancestors(ontology_type)
                result["ontology"] = {
                    "type": ontology_type,
                    "display_name": _clean_agtype(row.get("type_display_name")),
                    "ancestors": ancestors,
                    "category": ontology_service.resolve_type(ontology_type).category if ontology_service.resolve_type(ontology_type) else None,
                }
    except Exception as e:
        logger.warning(f"Failed to query sector graph for document {document_id}: {e}")

    # 2. Query public graph for applicable laws
    try:
        from app.services.legal_graph_service import legal_graph
        laws = await legal_graph.get_applicable_laws(document_id, tenant_id)
        result["applicable_laws"] = laws
    except Exception as e:
        logger.warning(f"Failed to query applicable laws for document {document_id}: {e}")

    return result


@router.get("/type-expansion/{type_name}")
async def expand_type_for_search(type_name: str):
    """
    Expand a type name into all equivalent semantic_types for search.

    Given "financial_document", returns ["factura", "nomina", "presupuesto",
    "albaran", "pedido", "recibo"] — useful for SmartSearch to expand
    abstract type queries into concrete semantic_type filters.
    """
    et = ontology_service.resolve_type(type_name)
    if not et:
        return {"type": type_name, "semantic_types": [type_name]}

    # If it's a leaf type, just return it
    descendants = ontology_service.get_type_descendants(type_name)
    if not descendants:
        return {"type": type_name, "semantic_types": [type_name]}

    # Filter to only leaf types (ones with no children)
    leaf_types = [
        d for d in descendants
        if not ontology_service.get_type_descendants(d)
    ]
    return {"type": type_name, "semantic_types": leaf_types}
