"""
Legal Context Search - BOE Legislation Search for Agent Enhancement

This module provides functionality to search the PublicKnowledge database (BOE)
for relevant legislation that agents can cite in their responses.

The search results are formatted as context that can be prepended to agent tasks,
ensuring agents have access to specific legal references (Article X, BOE-A-XXXX).
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


async def search_legal_context(
    query: str,
    topics: Optional[List[str]] = None,
    limit: int = 5
) -> str:
    """
    Search PublicKnowledge (BOE) for relevant legislation.

    Returns formatted legal context that can be included in agent prompts.
    Agents use this context to cite specific laws and regulations.

    Args:
        query: Search query or document excerpt (max 500 chars used)
        topics: Optional list of topics to filter by (e.g., ["laboral", "RGPD"])
        limit: Maximum number of results to return

    Returns:
        Formatted string with legal references, or empty string if no results

    Example:
        >>> context = await search_legal_context(
        ...     "contrato de trabajo temporal",
        ...     topics=["laboral", "ET"],
        ...     limit=5
        ... )
        >>> # Returns formatted BOE references for labor law
    """
    try:
        from app.services.public_knowledge_service import public_knowledge_service
        from app.schemas.public_knowledge import PublicSearchRequest

        # Initialize service if needed
        await public_knowledge_service.initialize()

        # Build search query with optional topics
        search_query = query
        if topics:
            search_query = f"{query} {' '.join(topics)}"

        # Create search request
        request = PublicSearchRequest(
            query=search_query[:500],  # Limit query length
            limit=limit,
            search_type="hybrid",
            verified_only=False,
            current_version_only=True,
        )

        # Execute search
        response = await public_knowledge_service.search(request)

        if not response.results:
            logger.debug("No legal context found for query")
            return ""

        # Format legal context for the agent
        legal_context_parts = [
            "=== LEGISLACIÓN APLICABLE (BOE) ===",
            "Usa estas referencias legales para fundamentar tus hallazgos:",
            ""
        ]

        for i, doc in enumerate(response.results, 1):
            ref = doc.legal_reference or doc.boe_id or "Sin referencia"
            title = doc.title or "Sin título"
            # Con 32K tokens disponibles, resumen completo de 400 chars
            summary = doc.summary or (doc.content[:400] if doc.content else "")

            legal_context_parts.append(f"""
{i}. {title}
   Referencia: {ref}
   Fuente: {doc.source_name or 'BOE'}
   Resumen: {summary[:400]}...
""")

        legal_context_parts.append("=== FIN LEGISLACIÓN ===")
        legal_context_parts.append("")
        legal_context_parts.append("INSTRUCCIÓN: Cita estas leyes específicamente en tus hallazgos usando el formato 'Art. X de [Ley] (BOE-A-XXXX-XXXXX)'")

        result = "\n".join(legal_context_parts)
        logger.info(f"📚 Legal context found: {len(response.results)} references ({len(result)} chars)")

        return result

    except ImportError as e:
        logger.warning(f"⚠️ PublicKnowledge service not available: {e}")
        return ""
    except Exception as e:
        logger.warning(f"⚠️ Could not search legal context: {e}")
        return ""


def get_topics_for_agent(agent_name: str) -> List[str]:
    """
    Get relevant search topics based on agent type.

    Args:
        agent_name: Name of the agent

    Returns:
        List of topic keywords to enhance legal search
    """
    topic_mapping = {
        "ContractAgent": ["contratos", "obligaciones", "código civil"],
        "ComplianceAgent": ["RGPD", "LOPDGDD", "cumplimiento", "protección datos"],
        "LaborAgent": ["laboral", "estatuto trabajadores", "ET", "convenio colectivo", "despido"],
        "FiscalAgent": ["IVA", "IRPF", "tributario", "facturación", "impuestos"],
        "RealEstateAgent": ["arrendamiento", "LAU", "alquiler", "hipoteca", "propiedad horizontal"],
        "PrivacyAgent": ["RGPD", "LOPDGDD", "privacidad", "datos personales", "AEPD"],
        "EducationAgent": ["LOMLOE", "educación", "escolar", "LOE", "universitario"],
    }

    return topic_mapping.get(agent_name, [])
