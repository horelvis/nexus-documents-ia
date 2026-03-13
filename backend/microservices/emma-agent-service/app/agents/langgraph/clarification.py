"""
Query Clarification Detector

Detects ambiguous queries and generates clarification requests before
wasting a search+generation cycle on vague input.

Heuristics (no LLM call, ~0ms):
- Query too short (<25 chars) with no specific entities
- Pronoun references without conversation history ("ese contrato", "la factura")
- Generic document references without filtering criteria

Returns a tuple (is_ambiguous, clarification_message, options).
When ambiguous, the clarification_message is returned as a fast_path_answer
instead of proceeding to the ReAct loop. Options provide clickable refinements.

Usage:
    from app.agents.langgraph.clarification import detect_ambiguity

    is_ambiguous, msg, options = detect_ambiguity(query, intent, history, entities)
    if is_ambiguous:
        return {"fast_path_answer": msg, "clarification_options": options, ...}
"""

import re
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Minimum query length to consider non-ambiguous (characters)
_MIN_QUERY_LENGTH = 25

# Entity patterns — presence of any suggests the query is specific enough
_ENTITY_PATTERNS = [
    r"\b\d{8}[A-Z]\b",          # DNI
    r"\b[XYZ]\d{7}[A-Z]\b",     # NIE
    r"\b[A-Z]\d{8}\b",          # CIF
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",  # Date
    r"\b20\d{2}\b",             # Year
    r"\b\d+[.,]\d{2}\s*€\b",   # Amount
]

# Pronoun references that suggest the user is referring to something
# from a previous conversation turn
_PRONOUN_PATTERNS = [
    r"\b(ese|esa|esos|esas)\s+(contrato|factura|documento|nómina|informe|acuerdo)\b",
    r"\b(el|la|los|las)\s+(mismo|misma|mismos|mismas)\b",
    r"\bel\s+anterior\b",
    r"\bla\s+anterior\b",
    r"\blo\s+que\s+mencioné\b",
    r"\blo\s+de\s+antes\b",
]

# Generic document terms — ambiguous when alone without filters
_GENERIC_TERMS = {
    "contrato", "contratos", "factura", "facturas", "nómina", "nóminas",
    "documento", "documentos", "informe", "informes", "acuerdo", "acuerdos",
    "recibo", "recibos", "certificado", "certificados",
}

# Clarification templates (Spanish)
_TEMPLATES = {
    "too_short": (
        "Tu consulta es muy breve y podría referirse a varios documentos. "
        "¿Puedes indicar algún dato adicional?"
    ),
    "pronoun_no_history": (
        "Parece que te refieres a un documento mencionado antes, "
        "pero no tengo contexto previo de esta conversación. "
        "¿Puedes indicar a qué documento te refieres?"
    ),
    "generic_type": (
        "Existen múltiples {doc_type} en el sistema. "
        "¿Puedes precisar a cuál te refieres?"
    ),
}

# Default options per template
_OPTIONS = {
    "too_short": [
        {"label": "Documentos recientes", "value": "documentos recientes del último mes"},
        {"label": "Contratos activos", "value": "contratos activos vigentes"},
        {"label": "Facturas del último mes", "value": "facturas del último mes"},
    ],
    "pronoun_no_history": [
        {"label": "Buscar todos los documentos", "value": "buscar todos los documentos"},
        {"label": "Documentos recientes", "value": "documentos recientes del último mes"},
    ],
}

# Contextual options for generic document types
_GENERIC_TYPE_OPTIONS: Dict[str, List[Dict[str, str]]] = {
    "factura": [
        {"label": "Facturas del último mes", "value": "facturas del último mes"},
        {"label": "Todas las facturas", "value": "todas las facturas"},
        {"label": "Facturas por empresa", "value": "facturas agrupadas por empresa"},
    ],
    "facturas": [
        {"label": "Facturas del último mes", "value": "facturas del último mes"},
        {"label": "Todas las facturas", "value": "todas las facturas"},
        {"label": "Facturas por empresa", "value": "facturas agrupadas por empresa"},
    ],
    "contrato": [
        {"label": "Contratos vigentes", "value": "contratos vigentes actualmente"},
        {"label": "Todos los contratos", "value": "todos los contratos"},
        {"label": "Contratos por vencer", "value": "contratos próximos a vencer"},
    ],
    "contratos": [
        {"label": "Contratos vigentes", "value": "contratos vigentes actualmente"},
        {"label": "Todos los contratos", "value": "todos los contratos"},
        {"label": "Contratos por vencer", "value": "contratos próximos a vencer"},
    ],
    "nómina": [
        {"label": "Nóminas del último mes", "value": "nóminas del último mes"},
        {"label": "Todas las nóminas", "value": "todas las nóminas"},
    ],
    "nóminas": [
        {"label": "Nóminas del último mes", "value": "nóminas del último mes"},
        {"label": "Todas las nóminas", "value": "todas las nóminas"},
    ],
    "documento": [
        {"label": "Documentos recientes", "value": "documentos recientes del último mes"},
        {"label": "Todos los documentos", "value": "todos los documentos"},
    ],
    "documentos": [
        {"label": "Documentos recientes", "value": "documentos recientes del último mes"},
        {"label": "Todos los documentos", "value": "todos los documentos"},
    ],
    "informe": [
        {"label": "Informes recientes", "value": "informes recientes"},
        {"label": "Todos los informes", "value": "todos los informes"},
    ],
    "informes": [
        {"label": "Informes recientes", "value": "informes recientes"},
        {"label": "Todos los informes", "value": "todos los informes"},
    ],
}


def _get_generic_options(doc_type: str) -> List[Dict[str, str]]:
    """Get contextual options for a generic document type."""
    if doc_type in _GENERIC_TYPE_OPTIONS:
        return _GENERIC_TYPE_OPTIONS[doc_type]
    # Fallback for any unrecognized type
    return [
        {"label": f"Ver todos los {doc_type}", "value": f"todos los {doc_type}"},
        {"label": f"{doc_type.capitalize()} recientes", "value": f"{doc_type} recientes del último mes"},
    ]


def _has_qualifier(query: str) -> bool:
    """Check if query contains temporal, scope, or grouping qualifiers.

    These indicate the user has already refined their query beyond a bare
    generic type, so we should NOT ask for clarification again.
    Examples: "facturas del último mes", "todos los contratos", "nóminas recientes"
    """
    q_lower = query.lower()
    qualifiers = (
        "último mes", "últimos", "última semana", "recientes", "reciente",
        "vigentes", "vigente", "activos", "activo", "activas", "activa",
        "todos los", "todas las", "por empresa", "por persona", "por fecha",
        "agrupados", "agrupadas", "pendientes", "vencidos", "vencidas",
        "por vencer", "próximos", "próximas", "del mes", "del año",
        "este mes", "este año", "enero", "febrero", "marzo", "abril",
        "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
        "noviembre", "diciembre",
    )
    return any(q in q_lower for q in qualifiers)


def _has_entity(query: str) -> bool:
    """Check if query contains a specific entity (DNI, date, amount, etc.)."""
    for pattern in _ENTITY_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return True
    return False


def _has_proper_noun(query: str) -> bool:
    """Heuristic: check if query contains a capitalized word (potential name/company)."""
    words = query.split()
    # Skip first word (might be capitalized due to sentence start)
    for word in words[1:]:
        if word[0:1].isupper() and len(word) > 2 and word not in {"Del", "Los", "Las", "Con", "Por", "Para"}:
            return True
    return False


def _extract_generic_type(query: str) -> Optional[str]:
    """Find a generic document type mentioned in the query.

    Checks longer terms first so 'facturas' matches before 'factura'.
    """
    q_lower = query.lower()
    for term in sorted(_GENERIC_TERMS, key=len, reverse=True):
        if term in q_lower:
            return term
    return None


def detect_ambiguity(
    query: str,
    intent: str,
    history: Optional[List[Dict[str, str]]] = None,
    entities: Optional[List[str]] = None,
) -> Tuple[bool, str, List[Dict[str, str]]]:
    """Detect if a query is too ambiguous for productive search.

    Args:
        query: The user's query text.
        intent: Classified intent (document_query, legal_query, etc.).
        history: Prior conversation messages (if any).
        entities: Pre-extracted entities from the query.

    Returns:
        Tuple of (is_ambiguous, clarification_message, options).
        If not ambiguous, clarification_message is empty string and options is [].
    """
    # Only check document-related intents
    if intent not in ("document_query", "legal_query", "analysis"):
        return False, "", []

    q = query.strip()

    # Check for pronoun references without conversation history
    has_history = bool(history and len(history) > 0)
    for pattern in _PRONOUN_PATTERNS:
        if re.search(pattern, q, re.IGNORECASE):
            if not has_history:
                logger.debug(f"Ambiguity: pronoun reference without history: {q[:50]}")
                return True, _TEMPLATES["pronoun_no_history"], _OPTIONS["pronoun_no_history"]
            # If there IS history, the pronoun is likely resolvable — not ambiguous
            return False, "", []

    # Short query without specific entities
    if len(q) < _MIN_QUERY_LENGTH:
        has_specificity = bool(entities) or _has_entity(q) or _has_proper_noun(q) or _has_qualifier(q)
        if not has_specificity:
            # Check if it's just a generic type mention
            generic_type = _extract_generic_type(q)
            if generic_type:
                logger.debug(f"Ambiguity: short query with generic type: {q[:50]}")
                return True, _TEMPLATES["generic_type"].format(doc_type=generic_type), _get_generic_options(generic_type)
            # Very short, no entities, no type — too vague
            logger.debug(f"Ambiguity: very short query: {q[:50]}")
            return True, _TEMPLATES["too_short"], _OPTIONS["too_short"]

    # Longer query with ONLY a generic type and common verbs (e.g., "dame el contrato")
    if len(q) < 40:
        generic_type = _extract_generic_type(q)
        if generic_type and not _has_entity(q) and not _has_proper_noun(q) and not _has_qualifier(q):
            # Check if the query has any specificity beyond "give me the [type]"
            q_lower = q.lower()
            action_verbs = ("dame", "muestra", "busca", "encuentra", "necesito", "quiero", "ver")
            if any(q_lower.startswith(v) or f" {v} " in f" {q_lower} " for v in action_verbs):
                logger.debug(f"Ambiguity: action + generic type only: {q[:50]}")
                return True, _TEMPLATES["generic_type"].format(doc_type=generic_type), _get_generic_options(generic_type)

    return False, "", []
