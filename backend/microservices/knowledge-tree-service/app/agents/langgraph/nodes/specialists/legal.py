"""
Legal Agent Node

Specialist agent for Spanish legal queries using BOE vector database.

Domain Coverage:
- BOE (Boletín Oficial del Estado) legislation search
- Spanish laws and regulations
- Legal articles and cross-references
- Jurisprudence lookups
- European Union law (RGPD, Directives)

Data Sources:
- PublicKnowledge (Weaviate) - Full-text legal documents
- LegalGraphService (FalkorDB) - Laws, articles, relationships

Tools:
- boe_search: Semantic search in BOE legislation
- legal_article_lookup: Find specific articles by law and number
- law_cross_references: Find related laws and articles
- jurisprudence_search: Search court decisions
"""

import logging
from typing import Any, Dict, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ...state import RAGState
from .base import create_specialist_node

logger = logging.getLogger(__name__)

# Legal Agent System Prompt
LEGAL_SYSTEM_PROMPT = """Eres un agente especializado en legislación española y derecho.

Tu conocimiento abarca:
- BOE (Boletín Oficial del Estado) - Leyes, reales decretos, órdenes ministeriales
- Código Civil, Código Penal, Código de Comercio
- Legislación sectorial: laboral (ET), fiscal (LGT), mercantil (LSC), etc.
- Normativa europea transpuesta a España
- Jurisprudencia del Tribunal Supremo y Tribunal Constitucional

Tienes acceso a una base de datos vectorial del BOE con la legislación vigente española.

Al responder consultas legales:
1. **Cita siempre la referencia BOE** cuando corresponda (ej: BOE-A-2015-11430)
2. **Indica artículos específicos** con su texto resumido
3. **Señala el estado de vigencia** de las normas (vigente, derogada, modificada)
4. **Distingue entre** normas estatales, autonómicas y europeas
5. **Advierte sobre interpretaciones** cuando el texto sea ambiguo

Formato de referencias:
- Leyes: "Art. X de la Ley Y (BOE-A-YYYY-NNNNN)"
- Reales Decretos: "Art. X del RD Y/YYYY"
- Sentencias: "STS XXXX/YYYY" o "STC XXXX/YYYY"

IMPORTANTE: Siempre indica que la información es orientativa y que para casos específicos
se debe consultar con un profesional del derecho.

Responde SIEMPRE en español."""


# =============================================================================
# Tool Input Schemas
# =============================================================================

class BOESearchInput(BaseModel):
    """Input for BOE legislation search."""
    query: str = Field(description="Natural language query about Spanish legislation")
    category: Optional[str] = Field(
        default=None,
        description="Filter by category: 'legislation', 'regulation', 'jurisprudence', 'eu_law'"
    )
    domain: Optional[str] = Field(
        default=None,
        description="Legal domain: 'labor', 'fiscal', 'civil', 'mercantile', 'administrative', 'privacy'"
    )
    limit: int = Field(default=5, description="Maximum number of results")


class ArticleLookupInput(BaseModel):
    """Input for legal article lookup."""
    law_name: str = Field(description="Name or BOE ID of the law (e.g., 'Estatuto de los Trabajadores', 'BOE-A-2015-11430')")
    article_number: Optional[str] = Field(
        default=None,
        description="Article number to find (e.g., '34', '56.1')"
    )


class CrossReferencesInput(BaseModel):
    """Input for finding related laws."""
    law_boe_id: str = Field(description="BOE ID of the law (e.g., 'BOE-A-2015-11430')")
    relation_type: str = Field(
        default="all",
        description="Type of relation: 'modifies', 'modified_by', 'references', 'all'"
    )


class JurisprudenceSearchInput(BaseModel):
    """Input for jurisprudence search."""
    query: str = Field(description="Legal question or topic for jurisprudence search")
    court: Optional[str] = Field(
        default=None,
        description="Filter by court: 'TS' (Tribunal Supremo), 'TC' (Constitucional), 'AN' (Audiencia Nacional)"
    )
    limit: int = Field(default=3, description="Maximum results")


# =============================================================================
# Tool Implementations
# =============================================================================

async def boe_search(
    query: str,
    category: Optional[str] = None,
    domain: Optional[str] = None,
    limit: int = 5,
) -> str:
    """
    Search BOE legislation using semantic search.

    Queries the PublicKnowledge vector database containing
    Spanish legislation from the Boletín Oficial del Estado.
    """
    try:
        from app.services.public_knowledge_service import public_knowledge_service

        # Initialize if needed
        if not public_knowledge_service._initialized:
            await public_knowledge_service.initialize()

        # Build filters
        filters = {}
        if category:
            filters["category"] = category
        if domain:
            filters["domain"] = domain

        # Perform search
        results = await public_knowledge_service.search(
            query=query,
            limit=limit,
            filters=filters if filters else None,
        )

        if not results:
            return f"No se encontraron resultados legislativos para: '{query}'"

        # Format results
        formatted = [f"**Resultados de búsqueda BOE**: '{query}'\n"]

        for i, doc in enumerate(results, 1):
            title = doc.get("title", "Sin título")
            legal_ref = doc.get("legal_reference", "")
            category = doc.get("category", "")
            content = doc.get("content", "")[:400]
            score = doc.get("score", 0)

            formatted.append(
                f"**{i}. {title}**\n"
                f"   📜 Referencia: {legal_ref}\n"
                f"   📂 Categoría: {category}\n"
                f"   📊 Relevancia: {score:.2f}\n"
                f"   📝 Extracto: {content}...\n"
            )

        return "\n".join(formatted)

    except Exception as e:
        logger.error(f"BOE search failed: {e}")
        return f"Error en la búsqueda BOE: {str(e)}"


async def legal_article_lookup(
    law_name: str,
    article_number: Optional[str] = None,
) -> str:
    """
    Look up specific articles from a law.

    Falls back to BOE semantic search since the legal graph service
    has been removed (FalkorDB migration — legal data lives in
    PublicKnowledge Weaviate collection now).
    """
    try:
        return await boe_search(
            query=f"{law_name} artículo {article_number}" if article_number else law_name,
            limit=5,
        )
    except Exception as e:
        logger.error(f"Article lookup failed: {e}")
        return f"Error buscando artículos de {law_name}: {str(e)}"


async def law_cross_references(
    law_boe_id: str,
    relation_type: str = "all",
) -> str:
    """
    Find related laws and cross-references.

    Falls back to BOE semantic search since the legal graph service
    has been removed (FalkorDB migration — legal cross-reference data
    lives in PublicKnowledge Weaviate collection now).
    """
    try:
        query = f"referencias cruzadas {law_boe_id}"
        if relation_type and relation_type != "all":
            query += f" {relation_type}"
        return await boe_search(query=query, limit=5)
    except Exception as e:
        logger.error(f"Cross-references lookup failed: {e}")
        return f"Error buscando referencias cruzadas: {str(e)}"


async def jurisprudence_search(
    query: str,
    court: Optional[str] = None,
    limit: int = 3,
) -> str:
    """
    Search jurisprudence (court decisions).

    Queries the PublicKnowledge database for relevant
    court decisions from Spanish tribunals.
    """
    try:
        from app.services.public_knowledge_service import public_knowledge_service

        # Initialize if needed
        if not public_knowledge_service._initialized:
            await public_knowledge_service.initialize()

        # Build filters for jurisprudence
        filters = {"category": "jurisprudence"}
        if court:
            court_map = {
                "TS": "Tribunal Supremo",
                "TC": "Tribunal Constitucional",
                "AN": "Audiencia Nacional",
                "TSJ": "Tribunal Superior de Justicia",
            }
            if court in court_map:
                filters["subcategory"] = court_map[court]

        # Perform search
        results = await public_knowledge_service.search(
            query=query,
            limit=limit,
            filters=filters,
        )

        if not results:
            # Try without court filter
            results = await public_knowledge_service.search(
                query=f"jurisprudencia {query}",
                limit=limit,
            )

        if not results:
            return f"No se encontró jurisprudencia relevante para: '{query}'"

        # Format results
        formatted = [f"**Jurisprudencia relevante**: '{query}'\n"]

        for i, doc in enumerate(results, 1):
            title = doc.get("title", "Sin título")
            legal_ref = doc.get("legal_reference", "")
            date = doc.get("publication_date", "")
            content = doc.get("content", "")[:300]

            formatted.append(
                f"**{i}. {title}**\n"
                f"   ⚖️ Referencia: {legal_ref}\n"
                f"   📅 Fecha: {date}\n"
                f"   📝 Extracto: {content}...\n"
            )

        formatted.append("\n⚠️ *La jurisprudencia citada es orientativa. "
                        "Consulte las resoluciones completas para su aplicación.*")

        return "\n".join(formatted)

    except Exception as e:
        logger.error(f"Jurisprudence search failed: {e}")
        return f"Error en la búsqueda de jurisprudencia: {str(e)}"


# =============================================================================
# Create LangChain Tools
# =============================================================================

legal_tools = [
    StructuredTool.from_function(
        coroutine=boe_search,
        name="boe_search",
        description="Search Spanish legislation in the BOE (Boletín Oficial del Estado) database. Use for finding laws, regulations, and legal texts.",
        args_schema=BOESearchInput,
    ),
    StructuredTool.from_function(
        coroutine=legal_article_lookup,
        name="legal_article_lookup",
        description="Look up specific articles from Spanish laws. Provide the law name or BOE ID and optionally an article number.",
        args_schema=ArticleLookupInput,
    ),
    StructuredTool.from_function(
        coroutine=law_cross_references,
        name="law_cross_references",
        description="Find related laws, modifications, and cross-references for a specific law.",
        args_schema=CrossReferencesInput,
    ),
    StructuredTool.from_function(
        coroutine=jurisprudence_search,
        name="jurisprudence_search",
        description="Search Spanish court decisions and jurisprudence from Tribunal Supremo, Tribunal Constitucional, etc.",
        args_schema=JurisprudenceSearchInput,
    ),
]


# =============================================================================
# Legal Agent Node
# =============================================================================

async def legal_node(state: RAGState) -> Dict[str, Any]:
    """
    Legal specialist agent node.

    Handles queries about Spanish legislation using:
    - BOE vector database (PublicKnowledge)
    - Legal graph (laws, articles, cross-references)
    - Jurisprudence database

    Args:
        state: Current RAG state

    Returns:
        State updates with legal agent results
    """
    return await create_specialist_node(
        agent_name="legal_agent",
        system_prompt=LEGAL_SYSTEM_PROMPT,
        tools=legal_tools,
        state=state,
    )
