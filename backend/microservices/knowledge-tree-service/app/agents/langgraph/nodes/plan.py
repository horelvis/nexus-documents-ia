"""
PLAN Node - Emma's Execution Planning

This node analyzes the query and retrieved documents to create
an execution plan - deciding which specialist agents to invoke.

Design Decisions:
1. Use existing DomainRouter for fast keyword-based domain detection
2. For complex queries, use LLM to reason about agent selection
3. Support multi-domain queries (e.g., "labor + fiscal")
4. Detect structural queries (count, list, filter) and route to general_agent
5. Structural queries use Apache AGE graph via weaviate-service

The node populates:
- detected_domains: What domains are relevant
- execution_plan: Which agents to invoke
- plan_reasoning: Why these agents were chosen
- is_structural_query: Whether query is structural (count/list/filter)

References:
- LangGraph Planning: https://langchain-ai.github.io/langgraph/tutorials/multi_agent/
"""

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..state import RAGState
from ..reasoning_tracker import ReasoningTracker, StepType

logger = logging.getLogger(__name__)

# Cached conversational config (loaded from emma_prompts.yaml)
_CONVERSATIONAL_CONFIG: Optional[Dict[str, Any]] = None


# =============================================================================
# Structural Query Detection
# =============================================================================

# Patterns that indicate structural queries (count, list, filter, exists)
STRUCTURAL_PATTERNS = [
    # Counting patterns
    r"cuántos?\s+(documentos?|expedientes?|contratos?|facturas?|archivos?|carpetas?)",
    r"cuántas?\s+(facturas?|nóminas?|carpetas?)",
    r"número\s+de\s+(documentos?|expedientes?|contratos?)",
    r"total\s+de\s+(documentos?|expedientes?)",
    r"cantidad\s+de\s+(documentos?|archivos?)",
    # Listing patterns
    r"lista(r|me)?\s+(todos?|las?|los?)\s+(documentos?|expedientes?|contratos?)",
    r"muéstrame\s+(todos?|las?|los?)",
    r"dame\s+(una\s+)?lista",
    r"enumera(r)?\s+(los?|las?)",
    # Filtering by date/year
    r"del\s+año\s+\d{4}",
    r"de\s+\d{4}",
    r"entre\s+\d{4}\s+y\s+\d{4}",
    r"desde\s+\d{4}",
    r"hasta\s+\d{4}",
    r"del\s+(último|pasado)\s+(mes|año|trimestre)",
    r"de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)",
    # Filtering by type/client
    r"de\s+tipo\s+\w+",
    r"del\s+cliente\s+\w+",
    r"de\s+(acme|cliente|proveedor)\s+\w+",
    # Existence patterns
    r"tengo\s+(algún|alguna|documentos?|expedientes?)",
    r"existe(n)?\s+(documentos?|expedientes?|contratos?)",
    r"hay\s+(algún|alguna|documentos?)",
    # Navigation patterns
    r"qué\s+(documentos?|archivos?)\s+hay\s+en",
    r"contenido\s+de(l)?\s+(expediente|carpeta)",
]

# Compile patterns for efficiency
_STRUCTURAL_REGEX = [re.compile(p, re.IGNORECASE) for p in STRUCTURAL_PATTERNS]


def _is_structural_query(query: str) -> Tuple[bool, str]:
    """
    Detect if query is structural (count, list, filter, exists).

    Structural queries should use the Apache AGE graph via structural_query tool.

    Args:
        query: User's natural language query

    Returns:
        Tuple of (is_structural, matched_pattern)
    """
    query_lower = query.lower()

    for pattern in _STRUCTURAL_REGEX:
        match = pattern.search(query_lower)
        if match:
            return True, match.group(0)

    return False, ""


def _get_conversational_response(query: str) -> str:
    """Return a conversational response using emma_prompts.yaml when available."""
    query_lower = query.lower().strip()

    config = _load_conversational_config()
    if config:
        for category, data in config.items():
            patterns = data.get("patterns", [])
            response = data.get("response", "")
            if not response:
                continue

            for pattern in patterns:
                pattern_lower = str(pattern).lower()
                if category == "greetings":
                    if query_lower.startswith(pattern_lower) or query_lower == pattern_lower:
                        return response.strip()
                else:
                    if pattern_lower in query_lower:
                        return response.strip()

    # Fallback if config missing or no match
    return "¿En qué puedo ayudarte con tus documentos?"


def _extract_declared_name(query: str) -> Optional[str]:
    """Extract a user-declared name from common patterns."""
    patterns = [
        r"(?:me llamo|mi nombre es|llámame|puedes llamarme)\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ][\wÁÉÍÓÚÜÑáéíóúüñ' -]{1,40})",
        r"(?:my name is|call me)\s+([A-Za-z][\w' -]{1,40})",
    ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # Keep first 3 words max to avoid long captures
            return " ".join(name.split()[:3])

    return None


def _is_name_query(query: str) -> bool:
    """Detect questions about the user's name."""
    query_lower = query.lower()
    name_questions = [
        "cómo me llamo", "como me llamo", "recuerdas mi nombre",
        "qué nombre tengo", "que nombre tengo", "¿cuál es mi nombre?",
        "what is my name", "do you remember my name",
    ]
    return any(p in query_lower for p in name_questions)


def _extract_name_from_messages(messages: List[Any]) -> Optional[str]:
    """Scan previous user messages for name declarations."""
    if not messages:
        return None

    # Scan from latest to oldest
    for msg in reversed(messages):
        content = getattr(msg, "content", None)
        if not content or not isinstance(content, str):
            continue

        name = _extract_declared_name(content)
        if name:
            return name

    return None


def _load_conversational_config() -> Optional[Dict[str, Any]]:
    """Load conversational patterns from emma_prompts.yaml (cached)."""
    global _CONVERSATIONAL_CONFIG
    if _CONVERSATIONAL_CONFIG is not None:
        return _CONVERSATIONAL_CONFIG

    config_path = (
        Path(__file__).parent.parent.parent.parent / "config" / "prompts" / "emma_prompts.yaml"
    )
    try:
        if config_path.exists():
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                _CONVERSATIONAL_CONFIG = config.get("conversational", {})
                return _CONVERSATIONAL_CONFIG
    except Exception as e:
        logger.warning(f"Failed to load conversational config: {e}")

    _CONVERSATIONAL_CONFIG = None
    return None

# Mapping from domain types to agent names
DOMAIN_TO_AGENT = {
    "labor": "labor_agent",
    "fiscal": "fiscal_agent",
    "privacy": "privacy_agent",
    "realestate": "realestate_agent",
    "contract": "contract_agent",
    "compliance": "compliance_agent",
    "education": "education_agent",
    "legal": "legal_agent",
    "general": "general_agent",
}

# System prompt for Emma's planning
PLANNING_PROMPT = """You are Emma, an AI assistant specialized in Spanish legal documents.

Analyze the user's query and the retrieved documents to determine which specialist agents should handle this request.

Available Specialist Agents:
- labor_agent: Labor law (Estatuto de los Trabajadores, contratos laborales, despidos, nóminas)
- fiscal_agent: Tax law (IVA, IRPF, facturas, declaraciones)
- privacy_agent: Data protection (RGPD, LOPD, protección de datos)
- contract_agent: General contracts (cláusulas, obligaciones, partes)
- general_agent: General document queries and fallback

For each query, determine:
1. Which domains are relevant (can be multiple)
2. Which agents should be invoked (in order of priority)
3. Brief reasoning for your selection

Output format (JSON):
{
    "domains": ["labor", "fiscal"],
    "agents": ["labor_agent", "fiscal_agent"],
    "reasoning": "Query involves dismissal compensation (labor) and tax implications (fiscal)"
}

If the query is simple and only needs general document search, use:
{
    "domains": ["general"],
    "agents": ["general_agent"],
    "reasoning": "General document search request"
}"""


async def plan_node(state: RAGState) -> Dict[str, Any]:
    """
    Plan execution by analyzing query and selecting agents.

    This node:
    1. Detects structural queries (count, list, filter) → route to general_agent
    2. Uses DomainRouter for keyword-based domain detection
    3. For complex queries, uses LLM for agent selection
    4. Creates execution plan with full traceability

    Args:
        state: Current RAG state with query and retrieved docs

    Returns:
        State updates: detected_domains, execution_plan, plan_reasoning
    """
    start_time = time.time()
    query = state.get("query", "")
    tenant_id = state.get("tenant_id", "")
    retrieved_docs = state.get("retrieved_docs", [])

    logger.info(f"📋 PLAN: Analyzing query for agent selection | tenant={tenant_id}")

    # Initialize reasoning tracker for this planning phase
    tracker = ReasoningTracker.get_current()
    tracker.set_source("plan_node")

    # Step 1: Analyze query
    tracker.add_step(
        StepType.QUERY_ANALYSIS,
        f"Analizando consulta: '{query[:50]}...'"
    )

    # Handle user name memory (set or recall)
    declared_name = _extract_declared_name(query)
    if declared_name or _is_name_query(query):
        response = None
        name_source = None

        try:
            from app.services.memory import get_memory_service
            memory = get_memory_service()
            await memory.initialize()

            if declared_name and state.get("user_id"):
                await memory.update_preference(
                    tenant_id=state.get("tenant_id", ""),
                    user_id=state.get("user_id", ""),
                    key="display_name",
                    value=declared_name,
                )
                response = f"¡Gracias, {declared_name}! Lo recordaré para esta sesión."
                name_source = "stored_preference"
            elif _is_name_query(query):
                if state.get("user_id"):
                    user_ctx = await memory.get_user_context(
                        tenant_id=state.get("tenant_id", ""),
                        user_id=state.get("user_id", ""),
                    )
                    stored_name = user_ctx.get("name")
                else:
                    stored_name = None

                if not stored_name:
                    stored_name = _extract_name_from_messages(state.get("messages", []))
                    if stored_name:
                        name_source = "conversation_history"

                if stored_name:
                    response = f"Te llamas {stored_name}."
                else:
                    response = "No tengo tu nombre guardado. ¿Cómo quieres que te llame?"

        except Exception as e:
            logger.warning(f"Name memory handling failed: {e}")

        if response:
            latency_ms = (time.time() - start_time) * 1000
            tracker.add_step(
                StepType.ROUTING,
                "Consulta de identidad detectada, omitiendo agentes",
                confidence=0.95,
                metadata={"route": "IDENTITY", "source": name_source}
            )
            tracker.add_step(
                StepType.RESPONSE,
                f"Respuesta de identidad generada ({latency_ms:.0f}ms)",
                confidence=0.95
            )

            return {
                "detected_domains": ["identity"],
                "execution_plan": [],
                "plan_reasoning": "Consulta de identidad: respuesta directa sin agentes",
                "reasoning_steps": tracker.get_steps(),
                "slm_fast_path_used": True,
                "slm_answer": response,
                "final_answer": response,
                "success": True,
                "metadata": {
                    **state.get("metadata", {}),
                    "planning_latency_ms": latency_ms,
                    "is_identity_query": True,
                    "decision_path": ["plan", "identity"],
                },
            }

    # Short-circuit conversational queries (retrieval was skipped)
    if state.get("retrieval_skipped") and state.get("metadata", {}).get("retrieval_skipped_reason") == "conversational_query":
        response = _get_conversational_response(query)
        latency_ms = (time.time() - start_time) * 1000

        tracker.add_step(
            StepType.ROUTING,
            "Consulta conversacional detectada, omitiendo agentes",
            confidence=0.95,
            metadata={"route": "CONVERSATIONAL"}
        )
        tracker.add_step(
            StepType.RESPONSE,
            f"Respuesta conversacional generada ({latency_ms:.0f}ms)",
            confidence=0.95
        )

        logger.info(
            f"💬 PLAN: Conversational query | "
            f"latency={latency_ms:.1f}ms"
        )

        return {
            "detected_domains": ["conversational"],
            "execution_plan": [],
            "plan_reasoning": "Consulta conversacional: respuesta directa sin agentes",
            "reasoning_steps": tracker.get_steps(),
            "slm_fast_path_used": True,
            "slm_answer": response,
            "final_answer": response,
            "success": True,
            "metadata": {
                **state.get("metadata", {}),
                "planning_latency_ms": latency_ms,
                "is_conversational_query": True,
                "decision_path": ["plan", "conversational"],
            },
        }

    # Step 2: Check for structural queries (count, list, filter, exists)
    # These should use general_agent with structural_query tool (Apache AGE graph)
    is_structural, matched_pattern = _is_structural_query(query)

    if is_structural:
        latency_ms = (time.time() - start_time) * 1000

        # Emit reasoning steps for structural detection
        tracker.add_step(
            StepType.ROUTING,
            f"Detectado: consulta estructural (patrón: '{matched_pattern}')",
            confidence=0.95
        )
        tracker.add_step(
            StepType.ROUTING,
            "Decisión: usar Apache AGE (base de datos de grafos)",
            confidence=0.95,
            metadata={"route": "GRAPH", "pattern": matched_pattern}
        )

        plan_reasoning = (
            f"Consulta estructural detectada (patrón: '{matched_pattern}'). "
            f"Ejecutando en Apache AGE (grafo)."
        )

        logger.info(
            f"📊 PLAN: Structural query detected | "
            f"pattern='{matched_pattern}' | routing=general_agent | "
            f"latency={latency_ms:.1f}ms"
        )

        return {
            "detected_domains": ["structural"],
            "execution_plan": ["general_agent"],
            "plan_reasoning": plan_reasoning,
            "reasoning_steps": tracker.get_steps(),
            "slm_fast_path_used": False,
            "slm_answer": None,
            "current_agent_index": 0,
            "metadata": {
                **state.get("metadata", {}),
                "planning_latency_ms": latency_ms,
                "is_structural_query": True,
                "structural_pattern": matched_pattern,
                "decision_path": ["plan", "structural_detection", "general_agent"],
            },
        }

    # Step 3: Use DomainRouter for keyword-based detection
    tracker.add_step(
        StepType.ROUTING,
        "No es consulta estructural, analizando dominio semántico...",
        confidence=0.5
    )

    domains, domain_confidence = await _detect_domains(query, retrieved_docs)

    # Step 4: Map domains to agents
    if domain_confidence >= 0.7 or len(domains) == 1:
        # High confidence or single domain - use direct mapping
        execution_plan = [DOMAIN_TO_AGENT.get(d, "general_agent") for d in domains]
        plan_reasoning = f"Dominio detectado: {', '.join(domains)} (confianza: {domain_confidence:.0%})"
        decision_method = "keyword_domain"

        tracker.add_step(
            StepType.ROUTING,
            f"Detectado: dominio {', '.join(domains)}",
            confidence=domain_confidence
        )
        tracker.add_step(
            StepType.ROUTING,
            f"Decisión: búsqueda semántica en Weaviate (vectores)",
            confidence=domain_confidence,
            metadata={"route": "VECTOR", "domains": domains}
        )
    else:
        # Low confidence or complex query - use LLM planning
        tracker.add_step(
            StepType.QUERY_ANALYSIS,
            "Consulta compleja, usando LLM para planificación...",
            confidence=domain_confidence
        )

        llm_plan = await _llm_planning(query, retrieved_docs, state)
        if llm_plan:
            execution_plan = llm_plan["agents"]
            domains = llm_plan["domains"]
            plan_reasoning = llm_plan["reasoning"]
            decision_method = "llm_planning"

            tracker.add_step(
                StepType.ROUTING,
                f"LLM decidió: {', '.join(domains)} → {', '.join(execution_plan)}",
                confidence=0.8
            )
        else:
            # Fallback to general agent
            execution_plan = ["general_agent"]
            domains = ["general"]
            plan_reasoning = "Usando agente general (fallback)"
            decision_method = "fallback"

            tracker.add_step(
                StepType.ROUTING,
                "Fallback: usando agente general con búsqueda híbrida",
                confidence=0.5,
                metadata={"route": "HYBRID"}
            )

    # Remove duplicates while preserving order
    seen = set()
    execution_plan = [a for a in execution_plan if not (a in seen or seen.add(a))]

    latency_ms = (time.time() - start_time) * 1000

    # Final step
    tracker.add_step(
        StepType.RESPONSE,
        f"Plan listo: {' → '.join(execution_plan)} ({latency_ms:.0f}ms)",
        confidence=domain_confidence
    )

    logger.info(
        f"✅ PLAN: domains={domains} | agents={execution_plan} | "
        f"method={decision_method} | confidence={domain_confidence:.2f} | "
        f"latency={latency_ms:.1f}ms"
    )

    return {
        "detected_domains": domains,
        "execution_plan": execution_plan,
        "plan_reasoning": plan_reasoning,
        "reasoning_steps": tracker.get_steps(),
        "slm_fast_path_used": False,
        "slm_answer": None,
        "current_agent_index": 0,
        "metadata": {
            **state.get("metadata", {}),
            "planning_latency_ms": latency_ms,
            "is_structural_query": False,
            "domain_confidence": domain_confidence,
            "decision_method": decision_method,
            "decision_path": ["plan", decision_method] + execution_plan,
        },
    }


# NOTE: SLM Router fast-path removed - SLM Router is in weaviate-service, not emma-agent-service.
# Structural queries are now handled via general_agent's structural_query tool which calls
# weaviate-service's /weaviate/structural/query endpoint (Apache AGE graph).


async def _detect_domains(
    query: str,
    retrieved_docs: List[Dict],
) -> tuple[List[str], float]:
    """
    Detect domains using keyword-based DomainRouter.

    Args:
        query: User's query
        retrieved_docs: Retrieved documents (for context)

    Returns:
        Tuple of (domains, confidence)
    """
    try:
        from app.agents.domain_router import domain_router, DomainType

        # Get all potentially relevant domains
        results = domain_router.get_domains_for_query(query, threshold=0.3)

        if not results:
            return ["general"], 1.0

        # Extract domains and highest confidence
        domains = [r.domain.value for r in results]
        confidence = results[0].confidence if results else 0.0

        # Boost confidence if documents support the domain
        if retrieved_docs:
            doc_domains = _extract_domains_from_docs(retrieved_docs)
            if any(d in doc_domains for d in domains):
                confidence = min(confidence + 0.2, 1.0)

        return domains, confidence

    except Exception as e:
        logger.warning(f"Domain detection failed: {e}")
        return ["general"], 0.5


def _extract_domains_from_docs(docs: List[Dict]) -> List[str]:
    """Extract domain hints from document metadata."""
    domains = set()

    for doc in docs:
        metadata = doc.get("metadata", {})

        # Check document_type
        doc_type = metadata.get("document_type", "").lower()
        if "labor" in doc_type or "trabajo" in doc_type or "nomina" in doc_type:
            domains.add("labor")
        if "factura" in doc_type or "fiscal" in doc_type or "iva" in doc_type:
            domains.add("fiscal")
        if "privacidad" in doc_type or "rgpd" in doc_type:
            domains.add("privacy")
        if "contrato" in doc_type:
            domains.add("contract")

    return list(domains)


async def _llm_planning(
    query: str,
    retrieved_docs: List[Dict],
    state: RAGState,
) -> Optional[Dict[str, Any]]:
    """
    Use LLM for complex query planning.

    This is invoked when keyword-based detection has low confidence.

    Args:
        query: User's query
        retrieved_docs: Retrieved documents
        state: Current state

    Returns:
        Planning result dict or None if failed
    """
    try:
        from app.agents.llm_client import get_llm_client
        import json

        llm_client = await get_llm_client()

        # Build context from docs
        doc_context = ""
        if retrieved_docs:
            doc_summaries = []
            for i, doc in enumerate(retrieved_docs[:5]):
                title = doc.get("title", "Untitled")
                doc_type = doc.get("metadata", {}).get("document_type", "unknown")
                doc_summaries.append(f"{i+1}. {title} (type: {doc_type})")
            doc_context = "\n".join(doc_summaries)

        # Build planning prompt
        user_message = f"""Query: {query}

Retrieved Documents:
{doc_context if doc_context else "No documents retrieved"}

Please analyze and provide the execution plan."""

        messages = [
            {"role": "system", "content": PLANNING_PROMPT},
            {"role": "user", "content": user_message},
        ]

        response = await llm_client.chat(
            messages=messages,
            temperature=0.1,  # Low temperature for consistent planning
            max_tokens=500,
        )

        if response and response.content:
            # Parse JSON from response
            content = response.content.strip()

            # Extract JSON if wrapped in markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            plan = json.loads(content)

            # Validate plan structure
            if "domains" in plan and "agents" in plan:
                return {
                    "domains": plan["domains"],
                    "agents": plan["agents"],
                    "reasoning": plan.get("reasoning", "LLM planning"),
                }

    except Exception as e:
        logger.warning(f"LLM planning failed: {e}")

    return None
