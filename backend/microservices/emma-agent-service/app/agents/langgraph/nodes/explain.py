"""
Explain Node — Humanized Query Trace

Generates a human-readable explanation of Emma's reasoning process.
Runs after synthesize/synthesize_swarm and before END.

The node is robust: it NEVER crashes. It always returns is_complete=True.
Anti-hallucination: the LLM only reformulates pre-extracted facts,
never sees the original query.
"""

import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.langgraph.quality_gate import _detect_fabricated_data
from app.agents.langgraph.sectors.registry import get_active_sector_config
from app.agents.llm_models import get_planner_model
from app.core.config import settings
from app.services.langfuse_prompt_client import get_langfuse_prompt_client

logger = logging.getLogger(__name__)

# ── Human-readable tool names (Spanish) ──────────────────────────────────────

TOOL_HUMAN_NAMES = {
    "smart_search": "búsqueda inteligente",
    "get_document_content": "lectura de documento",
    "structural_query": "consulta estructural",
    "analyze_domain": "análisis de dominio",
    "web_search": "búsqueda web",
    "search_jurisprudence": "búsqueda de jurisprudencia",
    "list_sources": "exploración de fuentes",
    "query_connector": "consulta a conector externo",
    "generate_document": "generación de documento",
    "forge_document": "creación de documento PDF",
    "send_email": "envío de email",
    "verified_generation": "generación verificada",
    "predictive_analysis": "análisis predictivo",
    "terminate": "finalización",
}

FALLBACK_TEMPLATE = "Consulté {n} fuente(s) ({source_names}) utilizando {tools_human_names}."


# ── Fact extraction (pure Python, deterministic) ─────────────────────────────

def extract_facts(
    reasoning_steps: List[Dict[str, Any]],
    sources: List[Dict[str, Any]],
) -> List[str]:
    """Map reasoning_steps to human-readable fact strings.

    Only processes known step types; unknown types are silently skipped.
    """
    facts: List[str] = []
    mentioned_sources: set = set()

    for step in reasoning_steps:
        step_type = step.get("type")

        if step_type == "tool_call":
            tool_name = step.get("name", "")
            if tool_name == "smart_search":
                stores = step.get("stores", "documentos")
                count = step.get("result_count", 0)
                facts.append(
                    f"Busqué en {stores} y encontré {count} resultados"
                )
            elif tool_name == "search_jurisprudence":
                facts.append("Busqué jurisprudencia en CENDOJ")
            elif tool_name == "web_search":
                facts.append("Busqué información en internet")
            elif tool_name == "get_document_content":
                doc_id = step.get("doc_id", "desconocido")
                facts.append(
                    f"Leí el contenido del documento {doc_id}"
                )
            elif tool_name == "structural_query":
                facts.append(
                    "Realicé una consulta estructural al grafo de conocimiento"
                )
            elif tool_name == "analyze_domain":
                facts.append("Realicé un análisis de dominio especializado")

        elif step_type == "tool_result":
            tool_name = step.get("name", "")
            if tool_name == "smart_search":
                title = step.get("title", "")
                score = step.get("score", 0)
                if title:
                    mentioned_sources.add(title)
                    facts.append(
                        f"Consulté: {title} (relevancia {score:.0%})"
                    )

    # Add sources not already mentioned via tool_result
    for source in sources:
        title = source.get("title", "")
        if title and title not in mentioned_sources:
            pages = source.get("pages", "")
            if pages:
                facts.append(f"Fuente utilizada: {title}, páginas {pages}")
            else:
                facts.append(f"Fuente utilizada: {title}")

    return facts


# ── LLM call (isolated for testability) ─────────────────────────────────────

async def _call_llm(
    facts_formatted: str,
    tools_human_names: str,
    source_names: str,
    sector: str,
    sector_guidance: str,
) -> str:
    """Call the planner LLM to humanize the extracted facts.

    Isolated as a standalone async function so tests can mock it easily.
    """
    client = get_langfuse_prompt_client()

    system_prompt = await client.get_prompt(
        "emma_explain_system",
        variables={
            "sector": sector,
            "sector_guidance": sector_guidance,
        },
    )
    user_prompt = await client.get_prompt(
        "emma_explain_user",
        variables={
            "facts_formatted": facts_formatted,
            "tools_human_names": tools_human_names,
            "source_names": source_names,
        },
    )

    model = get_planner_model()
    messages = [
        SystemMessage(content=system_prompt.content),
        HumanMessage(content=user_prompt.content),
    ]

    response = await model.ainvoke(messages)
    return response.content.strip()


# ── Main node ────────────────────────────────────────────────────────────────

async def explain_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a humanized explanation of Emma's reasoning process.

    Always returns is_complete=True. Never raises exceptions.
    """
    try:
        # Guard 1: skip for fast-path or when disabled
        if state.get("fast_path_used") or not settings.explain_enabled:
            return {"is_complete": True}

        reasoning_steps = state.get("reasoning_steps", [])
        sources = state.get("sources", [])

        # Extract deterministic facts
        facts = extract_facts(reasoning_steps, sources)

        # Collect tool human names from history
        tool_calls_history = state.get("tool_calls_history", [])
        used_tool_names = set()
        for tc in tool_calls_history:
            name = tc.get("name", "")
            if name in TOOL_HUMAN_NAMES:
                used_tool_names.add(TOOL_HUMAN_NAMES[name])
        tools_human_names = ", ".join(sorted(used_tool_names)) or "herramientas de consulta"

        # Collect source names
        source_names_list = []
        for s in sources:
            title = s.get("title", "")
            if title:
                source_names_list.append(title)
        source_names = ", ".join(source_names_list[:5]) or "fuentes consultadas"

        # Guard 2: no facts → fallback template
        if not facts:
            fallback = FALLBACK_TEMPLATE.format(
                n=len(sources),
                source_names=source_names,
                tools_human_names=tools_human_names,
            )
            return {
                "explanation": fallback,
                "is_complete": True,
            }

        # Get sector guidance
        sector_config = get_active_sector_config()
        sector = state.get("sector", "general")
        sector_guidance = (
            sector_config.explain_guidance
            if sector_config
            else "Usa lenguaje accesible. Describe los documentos consultados."
        )

        # Format facts for LLM
        facts_formatted = "\n".join(f"- {f}" for f in facts)

        # Call LLM
        try:
            explanation = await _call_llm(
                facts_formatted=facts_formatted,
                tools_human_names=tools_human_names,
                source_names=source_names,
                sector=sector,
                sector_guidance=sector_guidance,
            )
        except Exception as e:
            logger.warning(f"Explain LLM call failed, using fallback: {e}")
            explanation = FALLBACK_TEMPLATE.format(
                n=len(sources),
                source_names=source_names,
                tools_human_names=tools_human_names,
            )
            return {
                "explanation": explanation,
                "is_complete": True,
            }

        # Validate: check for fabricated data
        messages = state.get("messages", [])
        fabricated = _detect_fabricated_data(explanation, messages)
        if fabricated:
            logger.warning(
                f"Explain node: fabricated data detected ({fabricated[:3]}), "
                f"falling back to template"
            )
            explanation = FALLBACK_TEMPLATE.format(
                n=len(sources),
                source_names=source_names,
                tools_human_names=tools_human_names,
            )

        return {
            "explanation": explanation,
            "is_complete": True,
            "metadata": {
                "explain_facts_count": len(facts),
                "explain_tools_used": list(used_tool_names),
                "explain_sources_count": len(source_names_list),
            },
        }

    except Exception as e:
        # Never crash — always return is_complete=True
        logger.error(f"Explain node unexpected error: {e}", exc_info=True)
        return {"is_complete": True}
