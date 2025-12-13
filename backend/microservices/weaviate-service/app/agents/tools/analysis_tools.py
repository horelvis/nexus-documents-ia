"""
Analysis Tools for Agent Framework

These tools provide document analysis capabilities including:
- Deep document analysis
- Document comparison
- Entity extraction
- Risk identification

FRAMEWORK: Microsoft Agent Framework
Uses ChatAgent with @ai_function decorator.
"""

import json
import logging
from typing import Annotated, List, Dict, Any, Optional
from pydantic import Field

from app.core.security import get_tenant_collection_name
from app.core.execution_context import resolve_tenant_id

# Try to import ai_function from Agent Framework, fall back to identity decorator
try:
    from agent_framework import ai_function
except ImportError:
    def ai_function(func):
        return func

logger = logging.getLogger(__name__)

# Lazy loading
_rag_pipeline = None
_weaviate_service = None


def _get_rag_pipeline():
    """Get or create RAG pipeline (lazy loading)."""
    global _rag_pipeline
    if _rag_pipeline is None:
        from app.services.rag.rag_pipeline import RAGPipeline
        _rag_pipeline = RAGPipeline()
    return _rag_pipeline


def _get_weaviate_service():
    """Get or create Weaviate service (lazy loading)."""
    global _weaviate_service
    if _weaviate_service is None:
        from app.services.weaviate_service import WeaviateService
        _weaviate_service = WeaviateService()
    return _weaviate_service


@ai_function
async def analyze_document(
    document_id: Annotated[str, Field(description="Unique identifier of the document to analyze")],
    tenant_id: Annotated[str, Field(description="Tenant ID owning the document")],
    analysis_type: Annotated[str, Field(description="Type: comprehensive, summary, structure, risks, obligations")] = "comprehensive",
) -> str:
    """
    Perform deep analysis of a specific document.

    This tool retrieves a document and performs the requested type of analysis,
    extracting structured information based on the analysis type.

    Analysis types:
    - comprehensive: Full analysis including structure, entities, summary, and key points
    - summary: Executive summary with main conclusions
    - structure: Document structure analysis (sections, headings, organization)
    - risks: Identify potential risks, issues, or concerns
    - obligations: Extract obligations, requirements, and commitments

    Args:
        document_id: The unique document identifier
        tenant_id: Tenant identifier for access control
        analysis_type: Type of analysis to perform

    Returns:
        JSON string with analysis results including:
        - summary: Brief overview
        - key_points: List of important points
        - entities: Extracted named entities
        - analysis_specific_data: Data specific to the analysis type
    """
    # Resolve tenant_id from execution context (overrides LLM-provided value)
    actual_tenant_id = resolve_tenant_id(tenant_id)
    logger.info(f"🔍 ANALYSIS_TOOL CALLED: analyze_document")
    logger.info(f"🔍 Parameters: document_id={document_id}, tenant_id={tenant_id}, actual_tenant_id={actual_tenant_id}, type={analysis_type}")

    try:
        service = _get_weaviate_service()
        collection_name = get_tenant_collection_name(actual_tenant_id)
        logger.info(f"🔍 Collection name: {collection_name}")

        # Get document content
        doc = await service.get_document_by_id(
            collection_name=collection_name,
            document_id=document_id,
        )

        if not doc:
            return json.dumps({
                "error": "Document not found",
                "document_id": document_id
            })

        content = doc.get("content", "")
        title = doc.get("title", doc.get("filename", "Unknown"))

        # Perform analysis based on type
        pipeline = _get_rag_pipeline()

        if analysis_type == "comprehensive":
            analysis = await _comprehensive_analysis(content, title, pipeline, document_id, actual_tenant_id)
        elif analysis_type == "summary":
            analysis = await _summary_analysis(content, title, pipeline, document_id, actual_tenant_id)
        elif analysis_type == "structure":
            analysis = await _structure_analysis(content, title)
        elif analysis_type == "risks":
            analysis = await _risk_analysis(content, title, pipeline, document_id, actual_tenant_id)
        elif analysis_type == "obligations":
            analysis = await _obligation_analysis(content, title, pipeline, document_id, actual_tenant_id)
        else:
            analysis = await _comprehensive_analysis(content, title, pipeline, document_id, actual_tenant_id)

        return json.dumps({
            "document_id": document_id,
            "document_title": title,
            "analysis_type": analysis_type,
            **analysis
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.exception(f"Document analysis error: {e}")
        return json.dumps({
            "error": str(e),
            "document_id": document_id
        })


async def _comprehensive_analysis(content: str, title: str, pipeline, document_id: str = "", tenant_id: str = "") -> Dict:
    """Perform comprehensive document analysis using RAG pipeline."""
    try:
        # Use the pipeline's analyze_document method
        result = await pipeline.analyze_document(
            document_content=content,
            document_id=document_id or "analysis",
            tenant_id=tenant_id or "default",
            analysis_type="comprehensive"
        )

        if result.get("success"):
            return {
                "analysis": result.get("answer", "No analysis generated"),
                "word_count": len(content.split()),
                "char_count": len(content),
                "execution_time_ms": result.get("execution_time_ms", 0),
            }
        else:
            logger.warning(f"Pipeline analysis returned no success: {result}")
            return _basic_analysis(content, title)

    except Exception as e:
        logger.warning(f"LLM analysis failed, using basic analysis: {e}")
        return _basic_analysis(content, title)


def _basic_analysis(content: str, title: str) -> Dict:
    """Fallback basic analysis when LLM fails."""
    # Extract basic info from content
    lines = content.strip().split('\n')
    word_count = len(content.split())

    return {
        "analysis": f"Document: {title}\nWord count: {word_count}\nLines: {len(lines)}\nPreview: {content[:500]}...",
        "word_count": word_count,
        "char_count": len(content),
    }


async def _summary_analysis(content: str, title: str, pipeline, document_id: str = "", tenant_id: str = "") -> Dict:
    """Generate executive summary using RAG pipeline."""
    try:
        result = await pipeline.analyze_document(
            document_content=content,
            document_id=document_id or "summary",
            tenant_id=tenant_id or "default",
            analysis_type="summary"
        )

        if result.get("success"):
            return {"summary": result.get("answer", "No summary generated")}
        else:
            return {"summary": f"Summary: {content[:500]}..."}

    except Exception as e:
        return {"summary": f"Summary not available: {e}"}


async def _structure_analysis(content: str, title: str) -> Dict:
    """Analyze document structure without LLM."""
    lines = content.split('\n')
    sections = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Detect potential headers
        if stripped and (
            stripped.isupper() or
            stripped.endswith(':') or
            (len(stripped) < 100 and stripped[0].isupper() and not stripped.endswith('.'))
        ):
            sections.append({
                "line": i + 1,
                "text": stripped[:100],
                "type": "potential_header"
            })

    return {
        "total_lines": len(lines),
        "total_paragraphs": content.count('\n\n') + 1,
        "potential_sections": sections[:20],  # Limit to first 20
        "has_numbered_lists": bool(any(line.strip().startswith(('1.', '2.', 'a)', 'b)')) for line in lines)),
        "has_bullet_points": bool(any(line.strip().startswith(('-', '*', '•')) for line in lines)),
    }


async def _risk_analysis(content: str, title: str, pipeline, document_id: str = "", tenant_id: str = "") -> Dict:
    """Identify risks in document using RAG pipeline."""
    try:
        result = await pipeline.analyze_document(
            document_content=content,
            document_id=document_id or "risks",
            tenant_id=tenant_id or "default",
            analysis_type="risks"
        )

        if result.get("success"):
            return {"risk_analysis": result.get("answer", "No risk analysis generated")}
        else:
            return {"risk_analysis": "Risk analysis not available"}

    except Exception as e:
        return {"risk_analysis": f"Risk analysis not available: {e}"}


async def _obligation_analysis(content: str, title: str, pipeline, document_id: str = "", tenant_id: str = "") -> Dict:
    """Extract obligations and requirements using RAG pipeline."""
    try:
        result = await pipeline.analyze_document(
            document_content=content,
            document_id=document_id or "obligations",
            tenant_id=tenant_id or "default",
            analysis_type="obligations"
        )

        if result.get("success"):
            return {"obligation_analysis": result.get("answer", "No obligation analysis generated")}
        else:
            return {"obligation_analysis": "Obligation analysis not available"}

    except Exception as e:
        return {"obligation_analysis": f"Obligation extraction not available: {e}"}


@ai_function
async def compare_documents(
    doc_ids: Annotated[str, Field(description="Document IDs separated by comma (e.g., 'id1,id2,id3')")],
    tenant_id: Annotated[str, Field(description="Tenant ID for access control")],
    aspect: Annotated[str, Field(description="Aspect to compare: all, content, structure, dates, amounts")] = "all",
) -> str:
    """
    Compare multiple documents to identify similarities and differences.

    Useful for comparing contract versions, policy documents, or related
    documents to understand what changed or differs between them.

    Args:
        doc_ids: Comma-separated list of document IDs to compare
        tenant_id: Tenant identifier
        aspect: What aspect to focus comparison on:
            - all: Complete comparison
            - content: Focus on text content differences
            - structure: Compare document organization
            - dates: Compare dates and timelines mentioned
            - amounts: Compare monetary values and quantities

    Returns:
        JSON string with comparison results including:
        - similarities: What the documents have in common
        - differences: How they differ
        - aspect_specific_analysis: Detailed analysis for requested aspect
    """
    # Resolve tenant_id from execution context (overrides LLM-provided value)
    actual_tenant_id = resolve_tenant_id(tenant_id)
    logger.info(f"Comparing documents: ids={doc_ids}, tenant={actual_tenant_id}, aspect={aspect}")

    try:
        ids = [id.strip() for id in doc_ids.split(",")]
        if len(ids) < 2:
            return json.dumps({
                "error": "At least 2 document IDs required for comparison"
            })

        service = _get_weaviate_service()
        collection_name = get_tenant_collection_name(actual_tenant_id)

        # Fetch all documents
        documents = []
        for doc_id in ids[:5]:  # Limit to 5 documents
            doc = await service.get_document_by_id(
                collection_name=collection_name,
                document_id=doc_id,
            )
            if doc:
                documents.append({
                    "id": doc_id,
                    "title": doc.get("title", "Unknown"),
                    "content": doc.get("content", "")[:3000],  # Limit content
                })

        if len(documents) < 2:
            return json.dumps({
                "error": "Could not find enough documents to compare"
            })

        # Basic comparison without LLM
        comparison = {
            "documents_compared": [d["title"] for d in documents],
            "document_count": len(documents),
            "lengths": {d["id"]: len(d["content"]) for d in documents},
        }

        # Try LLM-based comparison
        pipeline = _get_rag_pipeline()
        doc_summaries = "\n\n".join([
            f"Document: {d['title']}\nContent excerpt: {d['content'][:1500]}"
            for d in documents
        ])

        prompt = f"""Compare these {len(documents)} documents:

{doc_summaries}

Focus on: {aspect}

Provide:
1. Key similarities
2. Key differences
3. Notable observations
"""

        try:
            result = await pipeline.generate_response(
                query=prompt,
                context=doc_summaries,
                system_prompt="You are a document analyst. Compare documents objectively."
            )
            comparison["analysis"] = result
        except Exception as e:
            comparison["analysis"] = f"Detailed comparison not available: {e}"

        return json.dumps(comparison, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.exception(f"Document comparison error: {e}")
        return json.dumps({"error": str(e)})


@ai_function
async def extract_entities(
    document_id: Annotated[str, Field(description="Document ID to extract entities from")],
    tenant_id: Annotated[str, Field(description="Tenant ID for access control")],
    entity_types: Annotated[str, Field(description="Entity types to extract: all, persons, organizations, dates, amounts, locations")] = "all",
) -> str:
    """
    Extract named entities from a document.

    Identifies and extracts specific types of entities mentioned in the
    document, such as people, organizations, dates, monetary amounts,
    and locations.

    Args:
        document_id: Document to extract entities from
        tenant_id: Tenant identifier
        entity_types: Which entity types to extract (comma-separated or 'all')

    Returns:
        JSON string with extracted entities grouped by type:
        - persons: People mentioned
        - organizations: Companies, institutions
        - dates: Dates and time references
        - amounts: Monetary values, quantities
        - locations: Places, addresses
    """
    # Resolve tenant_id from execution context (overrides LLM-provided value)
    actual_tenant_id = resolve_tenant_id(tenant_id)
    logger.info(f"🔍 ANALYSIS_TOOL CALLED: extract_entities")
    logger.info(f"🔍 Parameters: document_id={document_id}, tenant_id={tenant_id}, actual_tenant_id={actual_tenant_id}, types={entity_types}")

    try:
        service = _get_weaviate_service()
        collection_name = get_tenant_collection_name(actual_tenant_id)
        logger.info(f"🔍 Collection name: {collection_name}")

        doc = await service.get_document_by_id(
            collection_name=collection_name,
            document_id=document_id,
        )

        if not doc:
            return json.dumps({
                "error": "Document not found",
                "document_id": document_id
            })

        content = doc.get("content", "")
        title = doc.get("title", "Unknown")

        # Use RAG pipeline for entity extraction
        pipeline = _get_rag_pipeline()

        types_to_extract = entity_types if entity_types != "all" else "persons, organizations, dates, amounts, locations"

        prompt = f"""Extract named entities from this document.

Document: {title}

Content:
{content[:6000]}

Extract these entity types: {types_to_extract}

Format as structured lists for each entity type.
"""

        try:
            result = await pipeline.generate_response(
                query=prompt,
                context=content[:6000],
                system_prompt="You are a named entity recognition system. Extract entities precisely."
            )
            return json.dumps({
                "document_id": document_id,
                "document_title": title,
                "entity_types_requested": types_to_extract,
                "entities": result,
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({
                "document_id": document_id,
                "error": f"Entity extraction failed: {e}"
            })

    except Exception as e:
        logger.exception(f"Entity extraction error: {e}")
        return json.dumps({"error": str(e)})
