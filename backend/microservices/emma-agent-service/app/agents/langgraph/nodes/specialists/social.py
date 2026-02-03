"""
Social Agent Node — Specialized for social channel interactions.

Handles conversations from Slack, Telegram, WhatsApp with:
- Conversational tone (friendly, brief, emoji-moderate)
- Web search for external info (weather, news, events)
- Quick document search for user's files
- Location awareness

This agent is activated when `social_channel_mode=True` in metadata.
"""

import logging
import time
from typing import Any, Dict

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ...state import RAGState
from app.core.execution_context import get_tenant_id_or_raise
from .base import create_specialist_node

logger = logging.getLogger(__name__)


# =============================================================================
# Social Agent System Prompt
# =============================================================================

SOCIAL_SYSTEM_PROMPT = """Eres Emma, asistente de IA de NouxCubeIA. Estás conversando por un canal social (Slack, Telegram, WhatsApp).

## TU CONTEXTO
{location_context}

## TU PERSONALIDAD
- CERCANA y AMIGABLE, como una compañera experta
- Respuestas BREVES (2-3 oraciones máximo, estilo chat)
- Emojis con moderación (1-2 por mensaje) para dar calidez
- Tono CONVERSACIONAL, nunca robótico ni corporativo
- NO uses markdown elaborado (nada de ##, tablas, listas largas)

## TUS CAPACIDADES
1. **Búsqueda web** → Para clima, noticias, eventos, precios, info actual
2. **Búsqueda de documentos** → Para encontrar archivos del usuario

## REGLAS CRÍTICAS
1. Responde en el MISMO idioma del usuario
2. Si preguntan clima/noticias/info externa → USA `web_search` SIEMPRE
3. Si preguntan por documentos → USA `quick_document_search`
4. NUNCA digas "no puedo" si tienes una herramienta que puede ayudar
5. Sé CONCISA — esto es un chat, no un email formal

## EJEMPLOS DE RESPUESTAS

❌ MAL: "A continuación procedo a detallar la información meteorológica..."
✅ BIEN: "☀️ Hoy en Madrid hace 18°C con cielos despejados. ¡Buen día para pasear!"

❌ MAL: "No tengo acceso a información del tiempo en tiempo real."
✅ BIEN: *usa web_search* → "🌧️ Parece que va a llover esta tarde, lleva paraguas!"

❌ MAL: "He localizado los siguientes documentos en su repositorio corporativo..."
✅ BIEN: "📄 Encontré 3 contratos de ACME. ¿Cuál necesitas?"
"""


# =============================================================================
# Tool Input Schemas
# =============================================================================

class WebSearchInput(BaseModel):
    """Input for web search tool."""
    query: str = Field(description="Search query for the web (weather, news, etc.)")
    max_results: int = Field(default=5, description="Maximum number of results")


class QuickDocumentSearchInput(BaseModel):
    """Input for quick document search."""
    query: str = Field(description="What to search for in user's documents")
    limit: int = Field(default=5, description="Maximum number of results")


# =============================================================================
# Tool Implementations
# =============================================================================

async def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the internet for current information.

    Use for: weather, news, events, prices, general knowledge.
    """
    try:
        from app.services.web_search import get_web_search_client

        client = get_web_search_client()
        results = await client.search(query, max_results)

        if not results:
            return f"No encontré resultados para: '{query}'. Intenta reformular la búsqueda."

        # Format results conversationally (not markdown-heavy)
        formatted = [f"Encontré info sobre '{query}':\n"]
        for i, r in enumerate(results[:3], 1):  # Limit to 3 for chat brevity
            formatted.append(f"• {r.title}: {r.snippet[:100]}...")

        return "\n".join(formatted)

    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return f"Ups, no pude buscar eso ahora. ¿Intentamos de nuevo?"


async def quick_document_search(query: str, limit: int = 5) -> str:
    """
    Quick search in user's documents.

    Use for: finding contracts, invoices, reports, etc.
    """
    try:
        tenant_id = get_tenant_id_or_raise()
        from app.clients.weaviate_client import get_weaviate_client

        weaviate_client = get_weaviate_client()
        results = await weaviate_client.hybrid_search(
            tenant_id=tenant_id,
            query=query,
            limit=limit,
        )

        if not results:
            return f"No encontré documentos sobre '{query}' en tu repositorio."

        # Format for chat (brief)
        titles = [r.metadata.get('title', 'Sin título') for r in results[:5]]
        count = len(results)

        if count == 1:
            return f"📄 Encontré: {titles[0]}"
        else:
            preview = ", ".join(titles[:3])
            more = f" y {count - 3} más" if count > 3 else ""
            return f"📄 Encontré {count} documentos: {preview}{more}"

    except Exception as e:
        logger.error(f"Quick document search failed: {e}")
        return "No pude buscar en tus documentos ahora. ¿Intentamos de nuevo?"


# =============================================================================
# Social Agent Tools
# =============================================================================

social_tools = [
    StructuredTool.from_function(
        coroutine=web_search,
        name="web_search",
        description=(
            "Busca en internet. USA ESTO para: clima, tiempo, noticias, "
            "eventos, precios, información actual. Ejemplo: 'tiempo Madrid hoy'"
        ),
        args_schema=WebSearchInput,
    ),
    StructuredTool.from_function(
        coroutine=quick_document_search,
        name="quick_document_search",
        description=(
            "Busca en los documentos del usuario. USA ESTO para: "
            "contratos, facturas, informes, archivos específicos."
        ),
        args_schema=QuickDocumentSearchInput,
    ),
]


# =============================================================================
# Proactive Tool Detection (since small LLMs often don't call tools reliably)
# =============================================================================

import re

# Patterns for queries that NEED web search (weather, news, current events, prices)
WEB_SEARCH_PATTERNS = [
    r"\b(?:tiempo|clima|temperatura|lluv|llover|sol|soleado|nublado|nieve|viento)\b",
    r"\b(?:pronóstico|previsión|meteorolog)\b",
    r"\b(?:hace|hará|estará)\s+(?:frío|calor|buen|mal)\s+(?:tiempo|día)?\b",
    r"\b(?:noticias?|actualidad|últimas?)\b",
    r"\b(?:evento|concierto|partido|exposición|festival)\b",
    r"\b(?:precio|cuesta|vale|costar)\b",
    r"\b(?:hoy|mañana|esta\s+semana|este\s+fin\s+de\s+semana)\b.*\b(?:tiempo|clima|evento)\b",
    r"\b(?:qué\s+(?:tal|hay)|cómo\s+(?:está|va))\s+(?:el\s+)?(?:tiempo|clima|día)\b",
]

_WEB_SEARCH_REGEX = [re.compile(p, re.IGNORECASE) for p in WEB_SEARCH_PATTERNS]


def _needs_web_search(query: str) -> bool:
    """Detect if query needs web search (weather, news, current events)."""
    query_lower = query.lower()
    for pattern in _WEB_SEARCH_REGEX:
        if pattern.search(query_lower):
            return True
    return False


def _build_web_query(original_query: str, location: Dict[str, Any]) -> str:
    """Build optimized web search query with location context."""
    city = location.get("city", "España")

    # Detect query type and build optimized search
    query_lower = original_query.lower()

    if any(w in query_lower for w in ["tiempo", "clima", "temperatura", "lluv", "sol", "pronóstico"]):
        return f"tiempo hoy {city} España temperatura"
    elif any(w in query_lower for w in ["noticias", "actualidad"]):
        return f"noticias hoy {city} España"
    elif any(w in query_lower for w in ["evento", "concierto", "partido"]):
        return f"eventos hoy {city}"
    else:
        # Generic search with location
        return f"{original_query} {city}"


# =============================================================================
# Social Agent Node
# =============================================================================

async def social_node(state: RAGState) -> Dict[str, Any]:
    """
    Social agent node for chat channel interactions.

    Activated when metadata.social_channel_mode = True.
    Provides conversational responses with web search capability.

    Since Qwen 7B doesn't reliably call tools, this node proactively
    calls web_search for weather/news queries and includes results
    in the context.
    """
    start_time = time.time()
    query = state.get("query", "")
    metadata = state.get("metadata", {}) or {}  # Ensure not None

    # Build location context for prompt
    # IMPORTANT: location could be None (not just missing), so use "or {}"
    location = metadata.get("location") or {}
    if location:
        location_context = (
            f"- Ubicación: {location.get('city', 'España')}, "
            f"{location.get('region', '')}, {location.get('country', 'España')}\n"
            f"- Zona horaria: {location.get('timezone', 'Europe/Madrid')}"
        )
    else:
        location_context = "- Ubicación: España (por defecto)"

    # Build customized prompt
    system_prompt = SOCIAL_SYSTEM_PROMPT.replace("{location_context}", location_context)

    logger.info(
        f"📱 social_node: Starting | "
        f"location={location.get('city', 'default')} | "
        f"query='{query[:50]}...'"
    )

    # =================================================================
    # PROACTIVE WEB SEARCH: Small LLMs don't reliably call tools,
    # so we call web_search proactively for weather/news queries
    # =================================================================
    proactive_context = ""
    proactive_tool_used = None

    if _needs_web_search(query):
        logger.info(f"🔍 social_node: Detected web search need, calling proactively")
        try:
            search_query = _build_web_query(query, location)
            search_results = await web_search(search_query, max_results=3)
            if search_results and not search_results.startswith("No encontré"):
                proactive_context = f"\n\n📡 INFORMACIÓN ACTUALIZADA (web_search):\n{search_results}"
                proactive_tool_used = "web_search"
                logger.info(f"✅ social_node: Proactive web_search succeeded")
            else:
                logger.info(f"⚠️ social_node: Proactive web_search returned no results")
        except Exception as e:
            logger.warning(f"⚠️ social_node: Proactive web_search failed: {e}")

    # Inject proactive context into state if we have it
    # This will be picked up by base.py when building user_content
    modified_state = dict(state)
    if proactive_context:
        current_metadata = dict(modified_state.get("metadata", {}))
        current_metadata["proactive_web_context"] = proactive_context
        current_metadata["proactive_tool_used"] = proactive_tool_used
        modified_state["metadata"] = current_metadata

    # Execute through base specialist node
    result = await create_specialist_node(
        agent_name="social_agent",
        system_prompt=system_prompt,
        tools=social_tools,
        state=modified_state,
    )

    # Add proactive tool to tools_used in result
    if proactive_tool_used and "agent_results" in result:
        agent_result = result["agent_results"].get("social_agent", {})
        if agent_result:
            tools_used = list(agent_result.get("tools_used", []))
            if proactive_tool_used not in tools_used:
                tools_used.append(proactive_tool_used)
                agent_result["tools_used"] = tools_used
                result["agent_results"]["social_agent"] = agent_result

    latency_ms = (time.time() - start_time) * 1000
    logger.info(f"✅ social_node: Completed in {latency_ms:.1f}ms | proactive_tool={proactive_tool_used}")

    return result
