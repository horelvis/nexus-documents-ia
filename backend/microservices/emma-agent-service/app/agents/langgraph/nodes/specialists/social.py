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
from app.core.config import settings
from .base import create_specialist_node

logger = logging.getLogger(__name__)


# =============================================================================
# Social Agent System Prompt
# =============================================================================

SOCIAL_SYSTEM_PROMPT = """IMPORTANTE: Responde ÚNICAMENTE en ESPAÑOL. No uses chino, inglés ni otros idiomas.

Eres Emma, asistente de IA de NouxCubeIA.

## TU CONTEXTO
{location_context}

## REGLAS (OBLIGATORIAS)

1. IDIOMA: Responde SOLO en español de España. Si escribes en otro idioma, el sistema fallará.
2. NO INVENTES DATOS: Si la búsqueda web devuelve información irrelevante (como artículos de ordenadores cuando preguntan el clima), admite que no encontraste la información.
3. TONO: Amigable y conversacional, usando emojis con moderación (1-2 por mensaje).
4. RESPUESTA COMPLETA: Proporciona toda la información solicitada. Si el usuario pide detalles, dáselos sin limitarte.
5. No uses mayúsculas sostenidas.

## FORMATO DE RESPUESTA

- Para saludos: Responde brevemente.
- Para consultas de datos (tiempo, noticias): Resume la información principal.
- Para consultas de documentos: Incluye TODOS los detalles relevantes de cada documento encontrado.
- Cuando el usuario pide "más información" o "detalles": Proporciona una respuesta detallada y completa.

## CÓMO RESPONDER

Cuando la búsqueda web NO tenga datos relevantes:
- Responde: "No pude obtener esa información ahora. 🤔"
- NUNCA inventes temperaturas, precios o datos.

## EJEMPLOS

Pregunta: "¿Qué tiempo hace?"
Respuesta correcta: "Hoy en Molina de Segura está soleado con 18°C. ☀️"

Pregunta: "Hola"
Respuesta correcta: "¡Hola! ¿En qué te ayudo? 👋"

Pregunta: "Busca contratos que expiran pronto"
Respuesta correcta: "He encontrado 3 contratos próximos a expirar:

📄 **Contrato de Mantenimiento - ACME Corp**
   - Vencimiento: 15 marzo 2026
   - Valor: €12,000/año

📄 **Acuerdo de Confidencialidad - TechSolutions**
   - Vencimiento: 22 marzo 2026
   - Renovación automática: No

📄 **Contrato de Servicio - DataPro**
   - Vencimiento: 1 abril 2026
   - Estado: Pendiente de renovación

¿Necesitas que profundice en alguno de ellos?"
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
    Returns detailed information about each document found.
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

        # Format with full details for each document
        count = len(results)
        details = []

        for i, r in enumerate(results[:limit], 1):
            title = r.metadata.get('title', 'Sin título')
            doc_type = r.metadata.get('document_type', '')
            created = r.metadata.get('created_at', r.metadata.get('upload_date', ''))
            expiration = r.metadata.get('expiration_date', r.metadata.get('fecha_vencimiento', ''))

            # Build document info block
            doc_info = f"📄 **{title}**"

            # Add metadata if available
            meta_parts = []
            if doc_type:
                meta_parts.append(f"Tipo: {doc_type}")
            if created:
                meta_parts.append(f"Creado: {created[:10] if len(created) > 10 else created}")
            if expiration:
                meta_parts.append(f"Vencimiento: {expiration[:10] if len(expiration) > 10 else expiration}")

            if meta_parts:
                doc_info += "\n   " + " | ".join(meta_parts)

            # Add content snippet if available
            if r.content:
                snippet = r.content[:200].replace('\n', ' ').strip()
                if len(r.content) > 200:
                    snippet += "..."
                doc_info += f"\n   Extracto: {snippet}"

            details.append(doc_info)

        header = f"📋 Encontré {count} documento(s) relacionado(s) con '{query}':\n\n"
        return header + "\n\n".join(details)

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


# Patterns for queries that NEED document search (contracts, invoices, documents)
DOCUMENT_SEARCH_PATTERNS = [
    # Direct document mentions
    r"\b(?:contrato|contratos|factura|facturas|documento|documentos|archivo|archivos)\b",
    r"\b(?:expediente|expedientes|informe|informes|acuerdo|acuerdos)\b",
    r"\b(?:nómina|nóminas|recibo|recibos|presupuesto|presupuestos)\b",
    # Document actions
    r"\b(?:busca|encuentra|muéstrame|dame|lista|qué)\b.*\b(?:contrato|factura|documento|archivo)\b",
    r"\b(?:contrato|factura|documento)\b.*\b(?:de|del|sobre|para)\b",
    # Expiration/renewal queries
    r"\b(?:expir|venc|caduc|renov)\w*\b",
    r"\b(?:próximo|próxima|pendiente)\b.*\b(?:vencer|expirar|caducar|renovar)\b",
    # Follow-up queries (more details, which one, etc.)
    r"\b(?:más\s+(?:detalle|información|info)|cuéntame\s+más|amplía)\b",
    r"\b(?:el\s+primer|el\s+segund|el\s+tercer|cuál\s+de)\b",
]

_DOCUMENT_SEARCH_REGEX = [re.compile(p, re.IGNORECASE) for p in DOCUMENT_SEARCH_PATTERNS]


def _needs_document_search(query: str) -> bool:
    """Detect if query needs document search (contracts, invoices, etc.)."""
    query_lower = query.lower()
    for pattern in _DOCUMENT_SEARCH_REGEX:
        if pattern.search(query_lower):
            return True
    return False


def _extract_document_query(original_query: str) -> str:
    """Extract the key search terms from a document query."""
    query_lower = original_query.lower()

    # Remove filler words to get core search terms
    filler = [
        "por favor", "puedes", "podrías", "me", "los", "las", "el", "la",
        "qué", "cuál", "cuáles", "dame", "muéstrame", "busca", "encuentra",
        "tenemos", "tengo", "hay", "sobre", "acerca de",
    ]
    result = original_query
    for word in filler:
        result = re.sub(rf"\b{word}\b", "", result, flags=re.IGNORECASE)

    # Clean up extra spaces
    result = re.sub(r"\s+", " ", result).strip()

    # If too short, use original
    if len(result) < 5:
        return original_query

    return result


def _needs_web_search(query: str) -> bool:
    """Detect if query needs web search (weather, news, current events)."""
    query_lower = query.lower()
    for pattern in _WEB_SEARCH_REGEX:
        if pattern.search(query_lower):
            return True
    return False


def _build_web_query(original_query: str, location: Dict[str, Any]) -> str:
    """Build optimized web search query with location context."""
    city = location.get("city", settings.default_location_city)
    region = location.get("region", settings.default_location_region)

    # Detect query type and build optimized search
    query_lower = original_query.lower()

    if any(w in query_lower for w in ["tiempo", "clima", "temperatura", "lluv", "sol", "pronóstico", "weather"]):
        # Use weather-specific search terms that DuckDuckGo understands better
        return f"el tiempo en {city} {region} meteorología"
    elif any(w in query_lower for w in ["noticias", "actualidad", "news"]):
        return f"últimas noticias {city} {region}"
    elif any(w in query_lower for w in ["evento", "concierto", "partido"]):
        return f"eventos {city} hoy"
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
            f"- Ubicación: {location.get('city', settings.default_location_city)}, "
            f"{location.get('region', settings.default_location_region)}, {location.get('country', settings.default_location_country)}\n"
            f"- Zona horaria: {location.get('timezone', settings.default_location_timezone)}"
        )
    else:
        # Use default location from settings
        location = {
            "city": settings.default_location_city,
            "region": settings.default_location_region,
            "country": settings.default_location_country,
            "timezone": settings.default_location_timezone,
        }
        location_context = (
            f"- Ubicación: {settings.default_location_city}, "
            f"{settings.default_location_region}, {settings.default_location_country}\n"
            f"- Zona horaria: {settings.default_location_timezone}"
        )

    # Build customized prompt
    system_prompt = SOCIAL_SYSTEM_PROMPT.replace("{location_context}", location_context)

    logger.info(
        f"📱 social_node: Starting | "
        f"location={location.get('city', 'default')} | "
        f"query='{query[:50]}...'"
    )

    # =================================================================
    # PROACTIVE TOOL CALLS: Small LLMs don't reliably call tools,
    # so we call tools proactively based on query patterns
    # =================================================================
    proactive_context = ""
    proactive_tool_used = None

    # 1. Check for document search needs (contracts, invoices, etc.)
    if _needs_document_search(query):
        logger.info(f"📄 social_node: Detected document search need, calling proactively")
        try:
            search_query = _extract_document_query(query)
            search_results = await quick_document_search(search_query, limit=5)
            if search_results and not search_results.startswith("No encontré") and not search_results.startswith("No pude"):
                proactive_context = f"\n\n📂 DOCUMENTOS ENCONTRADOS (quick_document_search):\n{search_results}"
                proactive_tool_used = "quick_document_search"
                logger.info(f"✅ social_node: Proactive document_search succeeded")
            else:
                logger.info(f"⚠️ social_node: Proactive document_search returned no results")
        except Exception as e:
            logger.warning(f"⚠️ social_node: Proactive document_search failed: {e}")

    # 2. Check for web search needs (weather, news, etc.) - only if no document search
    elif _needs_web_search(query):
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
