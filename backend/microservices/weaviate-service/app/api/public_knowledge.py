"""
API endpoints for Public Knowledge Base
Provides access to shared specialized documents (legislation, regulations, etc.)
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
import logging

from app.schemas.public_knowledge import (
    PublicDocumentCreate,
    PublicDocumentResponse,
    PublicSearchRequest,
    PublicSearchResponse,
    CombinedSearchRequest,
    CombinedSearchResponse,
    PublicKnowledgeStats,
    PublicDocumentCategory,
    Jurisdiction
)
from app.services.public_knowledge_service import public_knowledge_service
from app.core.security import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public-knowledge", tags=["public-knowledge"])


@router.get("/health")
async def health_check():
    """Check public knowledge base health"""
    try:
        await public_knowledge_service.initialize()
        return {
            "status": "healthy",
            "service": "public-knowledge-base",
            "collection": "PublicKnowledge"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@router.get("/stats", response_model=PublicKnowledgeStats)
async def get_statistics():
    """Get public knowledge base statistics"""
    try:
        return await public_knowledge_service.get_stats()
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents", response_model=PublicDocumentResponse)
async def add_document(
    document: PublicDocumentCreate,
    api_key: str = Depends(verify_api_key)
):
    """
    Add a document to the public knowledge base.
    Requires API key authentication (admin only).
    """
    try:
        return await public_knowledge_service.add_document(document)
    except Exception as e:
        logger.error(f"Failed to add document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/batch")
async def batch_add_documents(
    documents: List[PublicDocumentCreate],
    api_key: str = Depends(verify_api_key)
):
    """
    Add multiple documents in batch.
    Requires API key authentication (admin only).
    """
    try:
        return await public_knowledge_service.batch_add_documents(documents)
    except Exception as e:
        logger.error(f"Batch add failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{document_id}", response_model=PublicDocumentResponse)
async def get_document(document_id: str):
    """Get a specific document by ID"""
    document = await public_knowledge_service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    api_key: str = Depends(verify_api_key)
):
    """
    Delete a document from the public knowledge base.
    Requires API key authentication (admin only).
    """
    success = await public_knowledge_service.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found or could not be deleted")
    return {"status": "deleted", "document_id": document_id}


@router.post("/search", response_model=PublicSearchResponse)
async def search_public_knowledge(request: PublicSearchRequest):
    """
    Search the public knowledge base.
    Supports filtering by category, jurisdiction, topics, and dates.
    """
    try:
        return await public_knowledge_service.search(request)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search", response_model=PublicSearchResponse)
async def search_public_knowledge_get(
    query: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Max results"),
    categories: Optional[List[PublicDocumentCategory]] = Query(None, description="Filter by categories"),
    jurisdictions: Optional[List[Jurisdiction]] = Query(None, description="Filter by jurisdictions"),
    topics: Optional[List[str]] = Query(None, description="Filter by topics"),
    verified_only: bool = Query(False, description="Only verified documents"),
    search_type: str = Query("hybrid", pattern="^(vector|keyword|hybrid)$", description="Search type")
):
    """
    Search the public knowledge base (GET method for simpler queries).
    """
    request = PublicSearchRequest(
        query=query,
        limit=limit,
        categories=categories,
        jurisdictions=jurisdictions,
        topics=topics,
        verified_only=verified_only,
        search_type=search_type
    )
    try:
        return await public_knowledge_service.search(request)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/combined-search", response_model=CombinedSearchResponse)
async def combined_search(
    request: CombinedSearchRequest,
    collection_name: str = Query(..., description="Tenant collection name")
):
    """
    Search both tenant documents and public knowledge base.
    Results can be merged using different strategies.
    """
    try:
        return await public_knowledge_service.combined_search(request, collection_name)
    except Exception as e:
        logger.error(f"Combined search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
async def list_categories():
    """List available document categories"""
    return {
        "categories": [
            {
                "value": cat.value,
                "name": cat.name,
                "description": _get_category_description(cat)
            }
            for cat in PublicDocumentCategory
        ]
    }


@router.get("/jurisdictions")
async def list_jurisdictions():
    """List available jurisdictions"""
    return {
        "jurisdictions": [
            {
                "value": jur.value,
                "name": jur.name,
                "description": _get_jurisdiction_description(jur)
            }
            for jur in Jurisdiction
        ]
    }


def _get_category_description(category: PublicDocumentCategory) -> str:
    """Get description for a category"""
    descriptions = {
        PublicDocumentCategory.LEGISLATION: "Leyes, decretos, códigos",
        PublicDocumentCategory.REGULATION: "Normativas, reglamentos",
        PublicDocumentCategory.JURISPRUDENCE: "Sentencias, jurisprudencia",
        PublicDocumentCategory.TEMPLATE: "Plantillas de documentos legales",
        PublicDocumentCategory.GUIDELINE: "Guías, manuales, procedimientos",
        PublicDocumentCategory.REFERENCE: "Material de referencia general",
        PublicDocumentCategory.FORM: "Formularios oficiales",
        PublicDocumentCategory.TREATY: "Tratados, convenios internacionales"
    }
    return descriptions.get(category, "")


def _get_jurisdiction_description(jurisdiction: Jurisdiction) -> str:
    """Get description for a jurisdiction"""
    descriptions = {
        Jurisdiction.SPAIN: "Legislación española",
        Jurisdiction.EUROPEAN_UNION: "Legislación de la Unión Europea",
        Jurisdiction.INTERNATIONAL: "Legislación internacional",
        Jurisdiction.REGIONAL: "Legislación autonómica / regional"
    }
    return descriptions.get(jurisdiction, "")


# ============================================================================
# Knowledge Extraction from Public Documents
# ============================================================================

@router.post("/extract-knowledge")
async def extract_knowledge_from_public_documents(
    limit: int = Query(100, ge=1, le=1000, description="Max documents to process"),
    category: Optional[PublicDocumentCategory] = Query(None, description="Filter by category"),
    api_key: str = Depends(verify_api_key)
):
    """
    Extract knowledge entities from public documents into the Knowledge Graph.

    This processes existing public documents (guidelines, references, etc.) and extracts
    entities like: articles, terms, references, organizations, dates.

    The extracted entities are stored in the Knowledge Graph collection
    for semantic search and entity-based queries.

    **Note**: For legislation (BOE laws), use the Legal Graph instead.
    Legislation is indexed directly to Apache AGE via /boe/download endpoint,
    which creates legal_law nodes with proper law-to-law relationships.

    Requires API key authentication (admin only).
    """
    # Legislation uses the Legal Graph directly - not entity extraction
    if category == PublicDocumentCategory.LEGISLATION:
        raise HTTPException(
            status_code=400,
            detail=(
                "Legislation uses law-to-law relationships in the Legal Graph (Apache AGE). "
                "Use POST /boe/download to index laws with their relationships. "
                "For existing legislation, run: python scripts/sync_public_knowledge_to_legal_graph.py"
            )
        )

    try:
        from app.services.knowledge import get_knowledge_service
        from app.services.weaviate_service import WeaviateService
        import re
        import uuid

        logger.info(f"🧠 Starting knowledge extraction from public documents | limit={limit}")

        # Initialize services
        await public_knowledge_service.initialize()
        knowledge_service = get_knowledge_service()
        await knowledge_service.initialize()

        weaviate_service = WeaviateService()
        await weaviate_service.initialize()

        # Get public documents using direct fetch (not search)
        # BM25/keyword search doesn't support "*" wildcard, so we use fetch_objects
        import weaviate.classes.query as wq

        await public_knowledge_service.initialize()
        collection = public_knowledge_service.client.collections.get("PublicKnowledge")

        # Build filter for category (exclude legislation by default)
        filters = None
        if category:
            filters = wq.Filter.by_property("category").equal(category.value)
        else:
            # Exclude legislation - it should go to Legal Graph
            filters = wq.Filter.by_property("category").not_equal("legislation")

        # Fetch documents directly without text search
        response = collection.query.fetch_objects(
            limit=limit,
            filters=filters,
            return_properties=["title", "content", "category", "jurisdiction", "keywords", "boe_id"]
        )

        # Convert to list of document-like objects
        class DocResult:
            def __init__(self, obj):
                self.id = str(obj.uuid)
                self.title = obj.properties.get("title", "")
                self.content = obj.properties.get("content", "")
                self.category = type("Cat", (), {"value": obj.properties.get("category", "")})()
                self.jurisdiction = type("Jur", (), {"value": obj.properties.get("jurisdiction", "")})()
                self.keywords = obj.properties.get("keywords", [])
                self.boe_id = obj.properties.get("boe_id", "")

        documents_list = [DocResult(obj) for obj in response.objects]
        logger.info(f"📄 Fetched {len(documents_list)} documents for extraction")

        results = {
            "total_documents": len(documents_list),
            "processed": 0,
            "entities_extracted": 0,
            "errors": 0,
            "details": []
        }

        # Define entity patterns for Spanish legal documents
        entity_patterns = {
            "articulo": r"(?:Artículo|Art\.)\s+(\d+(?:\.\d+)?(?:\s*bis|\s*ter)?)",
            "ley": r"(?:Ley\s+(?:Orgánica\s+)?\d+/\d{4})",
            "real_decreto": r"(?:Real\s+Decreto(?:-ley)?\s+\d+/\d{4})",
            "fecha": r"\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+de\s+\d{4}",
            "boe_referencia": r"BOE-[A-Z]-\d{4}-\d+",
            "organizacion": r"(?:Ministerio\s+de\s+[\w\s]+|Agencia\s+[\w\s]+|Instituto\s+[\w\s]+)",
            "concepto_legal": r"(?:derecho\s+a\s+[\w\s]+|obligación\s+de\s+[\w\s]+|deber\s+de\s+[\w\s]+)",
        }

        for doc in documents_list:
            try:
                doc_id = doc.id
                content = doc.content[:50000] if doc.content else ""  # Limit content size

                if not content:
                    continue

                extracted_entities = []
                seen_values = set()

                # Extract entities using patterns
                for entity_type, pattern in entity_patterns.items():
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    for match in matches:
                        value = match if isinstance(match, str) else match[0] if match else None
                        if value and len(value) > 2:
                            normalized = value.lower().strip()
                            if normalized not in seen_values:
                                seen_values.add(normalized)
                                extracted_entities.append({
                                    "type": entity_type,
                                    "value": value.strip(),
                                    "class_name": entity_type,
                                })

                # Also extract key terms from keywords/topics
                if doc.keywords:
                    for kw in doc.keywords[:10]:
                        if kw and len(kw) > 2:
                            normalized = kw.lower().strip()
                            if normalized not in seen_values:
                                seen_values.add(normalized)
                                extracted_entities.append({
                                    "type": "termino",
                                    "value": kw,
                                    "class_name": "termino",
                                })

                if not extracted_entities:
                    continue

                # Use a pseudo tenant_id for public documents
                public_tenant = "public_knowledge"

                # Store entities in Knowledge Graph via Weaviate
                for entity in extracted_entities[:50]:  # Limit per document
                    try:
                        entity_id = str(uuid.uuid4())

                        # Map type to standard entity types
                        type_mapping = {
                            "articulo": "clause",
                            "ley": "reference",
                            "real_decreto": "reference",
                            "fecha": "date",
                            "boe_referencia": "reference",
                            "organizacion": "organization",
                            "concepto_legal": "concept",
                            "termino": "term",
                        }

                        entity_type = type_mapping.get(entity["type"], "concept")

                        # Add to Weaviate knowledge collection
                        await weaviate_service.add_knowledge_entity(
                            tenant_id=public_tenant,
                            entity_id=entity_id,
                            entity_type=entity_type,
                            entity_value=entity["value"],
                            context_text=f"Extraído de: {doc.title[:100] if doc.title else 'documento público'}",
                            entity_label=entity["value"],
                            domain="legal",
                            source_document_id=doc_id,
                            confidence=0.85,
                            attributes={
                                "source": "public_knowledge",
                                "category": doc.category.value if doc.category else "legislation",
                                "jurisdiction": doc.jurisdiction.value if doc.jurisdiction else "spain",
                                "boe_id": doc.boe_id if hasattr(doc, 'boe_id') else None,
                            },
                            acl_everyone=True  # Public documents are accessible to everyone
                        )

                        results["entities_extracted"] += 1

                    except Exception as entity_error:
                        logger.warning(f"Failed to store entity: {entity_error}")
                        continue

                # Store entities in knowledge-tree-service sector graph (Apache AGE)
                try:
                    from app.clients.knowledge_tree_client import knowledge_tree_legal_client

                    kt_entities = [
                        {
                            "type": e["type"],
                            "value": e["value"],
                            "confidence": 0.85,
                            "attributes": {"domain": "legal", "source": "public_knowledge"},
                        }
                        for e in extracted_entities[:50]
                    ]
                    kt_result = await knowledge_tree_legal_client.store_entities(
                        tenant_id=public_tenant,
                        document_id=doc_id,
                        entities=kt_entities,
                    )
                    kt_stored = kt_result.get("entities_stored", 0)
                    if kt_stored > 0:
                        logger.info(f"📊 Stored {kt_stored} entities in sector graph (AGE) for {doc_id}")
                except Exception as kt_error:
                    logger.warning(f"⚠️ Failed to store entities in knowledge-tree: {kt_error}")

                results["processed"] += 1
                results["details"].append({
                    "document_id": doc_id,
                    "title": doc.title[:50] if doc.title else None,
                    "entities_count": min(len(extracted_entities), 50),
                })

            except Exception as doc_error:
                logger.warning(f"Failed to process document {doc.id}: {doc_error}")
                results["errors"] += 1
                continue

        logger.info(
            f"✅ Knowledge extraction complete: "
            f"{results['processed']} documents, "
            f"{results['entities_extracted']} entities"
        )

        return results

    except Exception as e:
        logger.error(f"❌ Knowledge extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
