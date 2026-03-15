"""
Fact Extractor — Hybrid regex + optional LLM extraction of user facts.

Called asynchronously after each Emma response to extract and persist
facts about the user for cross-session memory.

Two-stage pipeline:
    Stage 1 (regex, ~1ms): Declarative patterns ("me llamo X", "trabajo en X")
    Stage 2 (LLM, ~200ms, optional): Inferred facts from conversation context

Usage:
    await extract_and_save_facts(tenant_id, user_id, user_message, assistant_response)
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


# ─── Stage 1: Regex patterns ─────────────────────────────────────────

# Each pattern: (compiled_regex, category, fact_key, group_index_for_value)
_DECLARED_PATTERNS: List[Tuple[re.Pattern, str, str, int]] = [
    # Identity
    (re.compile(r"(?:me llamo|mi nombre es|soy)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)*)", re.IGNORECASE), "identity", "name", 1),
    (re.compile(r"(?:tengo|cuento con)\s+(\d{1,3})\s+años", re.IGNORECASE), "identity", "age", 1),

    # Work
    (re.compile(r"(?:trabajo en|pertenezco a(?:l departamento)?|soy del departamento(?: de)?)\s+(.+?)(?:\.|,|$)", re.IGNORECASE), "work", "department", 1),
    (re.compile(r"(?:soy|trabajo como|mi (?:cargo|puesto|rol) es)\s+(.+?)(?:\.|,|$)", re.IGNORECASE), "work", "role", 1),
    (re.compile(r"(?:trabajo en la empresa|mi empresa es|trabajo para)\s+(.+?)(?:\.|,|$)", re.IGNORECASE), "work", "company", 1),

    # Preferences
    (re.compile(r"(?:prefiero|quiero|me gusta(?:ría)?)\s+(?:que (?:me )?respondas |respuestas )?en\s+(español|inglés|catalán|gallego|euskera|valenciano)", re.IGNORECASE), "preference", "language", 1),
    (re.compile(r"(?:prefiero|quiero)\s+respuestas?\s+(breves?|detalladas?|técnicas?|simples?)", re.IGNORECASE), "preference", "response_style", 1),
    (re.compile(r"(?:no me|nunca me)\s+(?:hables|respondas)\s+(?:en|con)\s+(.+?)(?:\.|,|$)", re.IGNORECASE), "preference", "avoid_style", 1),
    (re.compile(r"(?:llámame|dime|puedes llamarme|prefiero que me llames)\s+([A-Za-záéíóúñÁÉÍÓÚÑ]+)", re.IGNORECASE), "identity", "preferred_name", 1),
]

# Forget patterns — user wants to clear a fact
_FORGET_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r"(?:olvida|borra|elimina)\s+(?:mi\s+)?nombre", re.IGNORECASE), "identity", "name"),
    (re.compile(r"(?:olvida|borra|elimina)\s+(?:todo lo que sabes|mis datos|mi información)", re.IGNORECASE), "__clear_all__", ""),
]


def _extract_declared_facts(message: str) -> List[Dict[str, Any]]:
    """Extract facts from explicit user declarations via regex.

    Returns list of {category, fact_key, fact_value, confidence, source}.
    """
    facts = []
    for pattern, category, fact_key, group_idx in _DECLARED_PATTERNS:
        match = pattern.search(message)
        if match:
            value = match.group(group_idx).strip().rstrip(".,;")
            if value and len(value) < 100:  # Sanity check
                facts.append({
                    "category": category,
                    "fact_key": fact_key,
                    "fact_value": value,
                    "confidence": 1.0,
                    "source": "declared",
                })
    return facts


def _check_forget_requests(message: str) -> Optional[Tuple[str, str]]:
    """Check if user wants to forget facts.

    Returns (category, fact_key) or ("__clear_all__", "") for full clear.
    Returns None if no forget request detected.
    """
    for pattern, category, fact_key in _FORGET_PATTERNS:
        if pattern.search(message):
            return (category, fact_key)
    return None


# ─── Stage 2: LLM extraction (optional) ──────────────────────────────

_LLM_EXTRACTION_PROMPT = """\
Analiza este intercambio entre un usuario y Emma (asistente IA). \
Extrae SOLO hechos personales NUEVOS y CONCRETOS sobre el usuario.

NO extraigas: preguntas del usuario, información de documentos, datos genéricos.
SÍ extrae: nombre, cargo, departamento, empresa, preferencias de comunicación, áreas de interés laboral.

Mensaje del usuario: {user_message}
Respuesta de Emma: {assistant_response}

Responde SOLO con un JSON array (vacío si no hay hechos nuevos):
[{{"category": "identity|work|preference|interest", "fact_key": "nombre_corto", "fact_value": "valor"}}]
"""


async def _extract_inferred_facts(
    user_message: str,
    assistant_response: str,
) -> List[Dict[str, Any]]:
    """Extract inferred facts via LLM (Stage 2).

    Only called when USER_MEMORY_LLM_EXTRACTION is enabled.
    Returns list of fact dicts with confidence < 1.0.
    """
    try:
        from langchain_core.messages import HumanMessage
        from app.agents.llm_models import get_planner_model

        prompt = _LLM_EXTRACTION_PROMPT.format(
            user_message=user_message[:500],
            assistant_response=assistant_response[:500],
        )

        model = get_planner_model().bind(temperature=0.1, max_tokens=300)
        response = await model.ainvoke([
            HumanMessage(content=prompt),
        ])

        content = (response.content or "").strip()

        # Extract JSON array from response
        # Handle thinking tags
        if "<think>" in content:
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        # Find JSON array
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if not match:
            return []

        parsed = json.loads(match.group())
        if not isinstance(parsed, list):
            return []

        facts = []
        for item in parsed:
            if all(k in item for k in ("category", "fact_key", "fact_value")):
                cat = item["category"]
                if cat not in ("identity", "work", "preference", "interest"):
                    continue
                facts.append({
                    "category": cat,
                    "fact_key": item["fact_key"][:100],
                    "fact_value": str(item["fact_value"])[:500],
                    "confidence": 0.7,
                    "source": "inferred",
                })

        return facts

    except Exception as e:
        logger.debug(f"LLM fact extraction failed (non-critical): {e}")
        return []


# ─── Main entrypoint ─────────────────────────────────────────────────

async def extract_and_save_facts(
    tenant_id: str,
    user_id: str,
    user_message: str,
    assistant_response: str,
) -> None:
    """Extract facts from a conversation exchange and save them.

    Called asynchronously (fire-and-forget) after each Emma response.
    Exceptions are caught internally to never break the main flow.
    """
    if not user_id or not user_message:
        return

    if not getattr(settings, "user_memory_enabled", True):
        return

    try:
        from .user_facts import get_user_facts_service
        service = get_user_facts_service()

        # Check for forget requests first
        forget = _check_forget_requests(user_message)
        if forget:
            category, fact_key = forget
            if category == "__clear_all__":
                await service.clear_user_facts(tenant_id, user_id)
                logger.info(f"User {user_id[:8]}... requested full memory clear")
                return
            else:
                # Delete specific fact (soft-delete all matching active facts)
                pool = await service._get_pool()
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE emma_user_memory_facts
                        SET is_active = false, updated_at = now()
                        WHERE tenant_id = $1::uuid AND user_id = $2
                          AND category = $3 AND fact_key = $4 AND is_active = true
                        """,
                        tenant_id, user_id, category, fact_key,
                    )
                await service._invalidate_cache(tenant_id, user_id)
                logger.info(f"User {user_id[:8]}... requested forget [{category}/{fact_key}]")
                return

        # Stage 1: Regex extraction (~1ms)
        declared_facts = _extract_declared_facts(user_message)

        # Stage 2: LLM extraction (optional, ~200ms)
        inferred_facts: List[Dict[str, Any]] = []
        if getattr(settings, "user_memory_llm_extraction", False):
            inferred_facts = await _extract_inferred_facts(
                user_message, assistant_response
            )

        # Merge (declared facts take precedence over inferred)
        all_facts = declared_facts + inferred_facts
        if not all_facts:
            return

        # Enforce max facts limit
        max_facts = getattr(settings, "user_memory_max_facts", 50)
        existing = await service.get_user_facts(tenant_id, user_id)
        if len(existing) >= max_facts:
            logger.debug(f"User {user_id[:8]}... at max facts limit ({max_facts}), skipping save")
            return

        # Save facts
        for fact in all_facts:
            await service.save_fact(
                tenant_id=tenant_id,
                user_id=user_id,
                category=fact["category"],
                fact_key=fact["fact_key"],
                fact_value=fact["fact_value"],
                confidence=fact.get("confidence", 1.0),
                source=fact.get("source", "declared"),
                source_query=user_message[:500],
            )

    except Exception as e:
        logger.warning(f"Fact extraction failed (non-critical): {e}")
