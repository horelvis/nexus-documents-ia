"""
Analysis Tools for Qwen-Agent Framework

These tools provide document analysis capabilities including:
- Deep document analysis
- Document comparison
- Entity extraction
- Risk identification

FRAMEWORK: Qwen-Agent
Reference: https://github.com/QwenLM/Qwen-Agent

MIGRATION NOTE:
- Migrated from MS Agent Framework @ai_function pattern
- Uses class-based tools with @register_tool decorator
"""

import asyncio
import json
import logging
from typing import Dict, Optional, Union

from qwen_agent.tools.base import BaseTool, register_tool

from app.core.security import get_tenant_collection_name
from app.core.execution_context import resolve_tenant_id, resolve_document_id

logger = logging.getLogger(__name__)


# =============================================================================
# Async Helper
# =============================================================================

def _run_async(coro):
    """Run an async coroutine from sync context."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=120)
    except RuntimeError:
        return asyncio.run(coro)


# =============================================================================
# Lazy Loading
# =============================================================================

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


# =============================================================================
# Internal Analysis Functions
# =============================================================================

async def _comprehensive_analysis(content: str, title: str, pipeline, document_id: str = "", tenant_id: str = "") -> Dict:
    """Perform comprehensive document analysis using RAG pipeline."""
    try:
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
        "potential_sections": sections[:20],
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


# =============================================================================
# Qwen-Agent Tool Classes
# =============================================================================

@register_tool('analyze_document')
class AnalyzeDocumentTool(BaseTool):
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
    """

    description = '''Perform deep analysis of a specific document.

Analysis types available:
- comprehensive: Full analysis including structure, entities, summary
- summary: Executive summary with main conclusions
- structure: Document structure analysis
- risks: Identify potential risks, issues, or concerns
- obligations: Extract obligations, requirements, and commitments

Returns JSON with analysis results including summary, key_points, entities, and analysis-specific data.'''

    parameters = [
        {
            'name': 'document_id',
            'type': 'string',
            'description': 'Unique identifier of the document to analyze',
            'required': True
        },
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID owning the document',
            'required': True
        },
        {
            'name': 'analysis_type',
            'type': 'string',
            'description': 'Type: comprehensive, summary, structure, risks, obligations (default: comprehensive)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute document analysis."""
        if isinstance(params, str):
            params = json.loads(params)

        document_id = params.get('document_id')
        tenant_id = params.get('tenant_id')
        analysis_type = params.get('analysis_type', 'comprehensive')

        return _run_async(self._analyze_document(
            document_id=document_id,
            tenant_id=tenant_id,
            analysis_type=analysis_type
        ))

    async def _analyze_document(
        self,
        document_id: str,
        tenant_id: str,
        analysis_type: str = "comprehensive",
    ) -> str:
        """Async implementation of document analysis."""
        actual_tenant_id = resolve_tenant_id(tenant_id)
        actual_document_id = resolve_document_id(document_id)

        logger.info(f"Analyze document: id={actual_document_id}, tenant={actual_tenant_id}, type={analysis_type}")

        if not actual_document_id:
            return json.dumps({
                "error": "No valid document_id provided or found in context",
                "llm_provided": document_id,
                "hint": "The document may not have been loaded correctly."
            })

        try:
            service = _get_weaviate_service()
            collection_name = get_tenant_collection_name(actual_tenant_id)

            doc = await service.get_document_by_id(
                collection_name=collection_name,
                document_id=actual_document_id,
            )

            if not doc:
                return json.dumps({
                    "error": "Document not found",
                    "document_id": actual_document_id,
                    "llm_provided": document_id
                })

            content = doc.get("content", "")
            title = doc.get("title", doc.get("filename", "Unknown"))

            pipeline = _get_rag_pipeline()

            if analysis_type == "comprehensive":
                analysis = await _comprehensive_analysis(content, title, pipeline, actual_document_id, actual_tenant_id)
            elif analysis_type == "summary":
                analysis = await _summary_analysis(content, title, pipeline, actual_document_id, actual_tenant_id)
            elif analysis_type == "structure":
                analysis = await _structure_analysis(content, title)
            elif analysis_type == "risks":
                analysis = await _risk_analysis(content, title, pipeline, actual_document_id, actual_tenant_id)
            elif analysis_type == "obligations":
                analysis = await _obligation_analysis(content, title, pipeline, actual_document_id, actual_tenant_id)
            else:
                analysis = await _comprehensive_analysis(content, title, pipeline, actual_document_id, actual_tenant_id)

            return json.dumps({
                "document_id": actual_document_id,
                "document_title": title,
                "analysis_type": analysis_type,
                **analysis
            }, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.exception(f"Document analysis error: {e}")
            return json.dumps({
                "error": str(e),
                "document_id": actual_document_id
            })


@register_tool('compare_documents')
class CompareDocumentsTool(BaseTool):
    """
    Compare multiple documents to identify similarities and differences.

    Useful for comparing contract versions, policy documents, or related
    documents to understand what changed or differs between them.
    """

    description = '''Compare multiple documents to identify similarities and differences.

Aspects to compare:
- all: Complete comparison
- content: Focus on text content differences
- structure: Compare document organization
- dates: Compare dates and timelines mentioned
- amounts: Compare monetary values and quantities

Returns JSON with similarities, differences, and aspect-specific analysis.'''

    parameters = [
        {
            'name': 'doc_ids',
            'type': 'string',
            'description': "Document IDs separated by comma (e.g., 'id1,id2,id3')",
            'required': True
        },
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID for access control',
            'required': True
        },
        {
            'name': 'aspect',
            'type': 'string',
            'description': 'Aspect to compare: all, content, structure, dates, amounts (default: all)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute document comparison."""
        if isinstance(params, str):
            params = json.loads(params)

        doc_ids = params.get('doc_ids')
        tenant_id = params.get('tenant_id')
        aspect = params.get('aspect', 'all')

        return _run_async(self._compare_documents(
            doc_ids=doc_ids,
            tenant_id=tenant_id,
            aspect=aspect
        ))

    async def _compare_documents(
        self,
        doc_ids: str,
        tenant_id: str,
        aspect: str = "all",
    ) -> str:
        """Async implementation of document comparison."""
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

            documents = []
            for doc_id in ids[:5]:
                doc = await service.get_document_by_id(
                    collection_name=collection_name,
                    document_id=doc_id,
                )
                if doc:
                    documents.append({
                        "id": doc_id,
                        "title": doc.get("title", "Unknown"),
                        "content": doc.get("content", "")[:3000],
                    })

            if len(documents) < 2:
                return json.dumps({
                    "error": "Could not find enough documents to compare"
                })

            comparison = {
                "documents_compared": [d["title"] for d in documents],
                "document_count": len(documents),
                "lengths": {d["id"]: len(d["content"]) for d in documents},
            }

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
                rag_result = await pipeline.process_query(
                    query=prompt,
                    tenant_id=actual_tenant_id,
                    validate_claims=False,
                    top_k=3,
                )
                comparison["analysis"] = rag_result.answer if hasattr(rag_result, 'answer') else str(rag_result)
            except Exception as e:
                comparison["analysis"] = f"Detailed comparison not available: {e}"

            return json.dumps(comparison, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.exception(f"Document comparison error: {e}")
            return json.dumps({"error": str(e)})


@register_tool('extract_entities')
class ExtractEntitiesTool(BaseTool):
    """
    Extract named entities from a document.

    Identifies and extracts specific types of entities mentioned in the
    document, such as people, organizations, dates, monetary amounts,
    and locations.
    """

    description = '''Extract named entities from a document.

Entity types available:
- all: Extract all types
- persons: People mentioned
- organizations: Companies, institutions
- dates: Dates and time references
- amounts: Monetary values, quantities
- locations: Places, addresses

Returns JSON with extracted entities grouped by type.'''

    parameters = [
        {
            'name': 'document_id',
            'type': 'string',
            'description': 'Document ID to extract entities from',
            'required': True
        },
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID for access control',
            'required': True
        },
        {
            'name': 'entity_types',
            'type': 'string',
            'description': 'Entity types to extract: all, persons, organizations, dates, amounts, locations (default: all)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute entity extraction."""
        if isinstance(params, str):
            params = json.loads(params)

        document_id = params.get('document_id')
        tenant_id = params.get('tenant_id')
        entity_types = params.get('entity_types', 'all')

        return _run_async(self._extract_entities(
            document_id=document_id,
            tenant_id=tenant_id,
            entity_types=entity_types
        ))

    async def _extract_entities(
        self,
        document_id: str,
        tenant_id: str,
        entity_types: str = "all",
    ) -> str:
        """Async implementation of entity extraction."""
        actual_tenant_id = resolve_tenant_id(tenant_id)
        logger.info(f"Extract entities: document_id={document_id}, tenant={actual_tenant_id}, types={entity_types}")

        try:
            service = _get_weaviate_service()
            collection_name = get_tenant_collection_name(actual_tenant_id)

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
                rag_result = await pipeline.process_query(
                    query=prompt,
                    tenant_id=actual_tenant_id,
                    validate_claims=False,
                    top_k=3,
                )
                entities = rag_result.answer if hasattr(rag_result, 'answer') else str(rag_result)
                return json.dumps({
                    "document_id": document_id,
                    "document_title": title,
                    "entity_types_requested": types_to_extract,
                    "entities": entities,
                }, ensure_ascii=False, indent=2)
            except Exception as e:
                return json.dumps({
                    "document_id": document_id,
                    "error": f"Entity extraction failed: {e}"
                })

        except Exception as e:
            logger.exception(f"Entity extraction error: {e}")
            return json.dumps({"error": str(e)})


# =============================================================================
# Tool Registration Exports
# =============================================================================

ANALYSIS_TOOLS = [
    AnalyzeDocumentTool,
    CompareDocumentsTool,
    ExtractEntitiesTool,
]

ANALYSIS_TOOL_NAMES = [
    'analyze_document',
    'compare_documents',
    'extract_entities',
]


def get_analysis_tools() -> list:
    """
    Get list of analysis tool names for use in Qwen-Agent Assistant's function_list.
    """
    return ANALYSIS_TOOL_NAMES
