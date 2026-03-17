"""
Hybrid Intent Router: Semantic Router (fast) + LLM (fallback).

Uses a two-tier classification strategy for the coordinator node:
1. Semantic Router (~1-3ms) — ONNX-based embedding similarity via FastEmbed
2. LLM classifier (~200ms) — only when semantic router returns no match

The semantic router reuses the same FastEmbedEncoder and semantic-router library
already used by the orchestration router (app/agents/orchestration/router.py).
"""

import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Suppress semantic-router verbose logging
os.environ.setdefault("SEMANTIC_ROUTER_LOG_LEVEL", "ERROR")


class IntentSemanticRouter:
    """
    Semantic intent classifier for coordinator-level routing.

    Routes:
      - conversational: greetings, farewells, smalltalk
      - identity: who-are-you, capabilities, name memory
      - general_knowledge: general questions not requiring tenant documents
      - (None → falls through to LLM or default document_query)
    """

    def __init__(self):
        self._router = None
        self._initialized = False

    def initialize(self):
        if self._initialized:
            return

        try:
            from semantic_router import Route
            from semantic_router.routers import SemanticRouter as RouterLayer

            # FastEmbed (ONNX) preferred; HuggingFace fallback
            try:
                from semantic_router.encoders import FastEmbedEncoder
                encoder = FastEmbedEncoder(model_name="sentence-transformers/all-MiniLM-L6-v2")
                logger.info("IntentRouter: using FastEmbedEncoder (ONNX)")
            except ImportError:
                from semantic_router.encoders import HuggingFaceEncoder
                encoder = HuggingFaceEncoder(name="sentence-transformers/all-MiniLM-L6-v2")
                logger.warning("IntentRouter: FastEmbed unavailable, using HuggingFaceEncoder")

            # score_threshold prevents false positives: only match when
            # cosine similarity exceeds the threshold; below → None → document_query
            conversational = Route(
                name="conversational",
                score_threshold=0.75,
                utterances=[
                    # Greetings (multiple forms boost signal for short inputs)
                    "Hola", "Hola qué tal", "Hola buenos días", "Hola buenas tardes",
                    "Buenos días", "Buenas tardes", "Buenas noches", "Buen día",
                    "Hello", "Hello there", "Hi there", "Hey there",
                    "Good morning", "Good afternoon", "Good evening",
                    "Qué tal", "Qué tal todo", "Cómo estás", "Cómo te va",
                    "How are you", "How is it going",
                    # Farewells
                    "Adiós", "Adiós Emma", "Me voy adiós",
                    "Hasta luego", "Nos vemos", "Hasta pronto",
                    "Chao", "Chao Emma", "Nos vemos luego", "Hasta mañana",
                    "Bye", "Bye bye", "Goodbye", "See you later", "See you",
                    # Thanks
                    "Gracias", "Muchas gracias", "Gracias Emma", "Gracias por todo",
                    "Thank you", "Thanks", "Thanks a lot", "Thank you very much",
                    # Smalltalk
                    "Todo bien", "Qué pasa", "What is up",
                ],
            )

            identity = Route(
                name="identity",
                score_threshold=0.75,
                utterances=[
                    # Identity — always about Emma (tú/Emma explicit)
                    "Quién eres tú Emma", "Quién eres tú", "Cómo te llamas Emma",
                    "Cuál es tu nombre Emma", "Dime tu nombre",
                    "Who are you Emma", "What is your name Emma",
                    # Capabilities — about Emma specifically
                    "Qué puedes hacer tú", "Para qué sirves tú Emma",
                    "Cómo me puedes ayudar Emma", "Qué sabes hacer",
                    "What can you do Emma", "How can you help me Emma",
                    # Help/meta
                    "Necesito ayuda Emma", "I need help Emma",
                    # Name/memory
                    "Me llamo Juan", "Mi nombre es María", "Recuerdas mi nombre",
                    "My name is John", "Call me Carlos", "Do you remember my name",
                ],
            )

            general_knowledge = Route(
                name="general_knowledge",
                score_threshold=0.70,
                utterances=[
                    # Programming / code generation
                    "Genera un código en Python", "Escribe un código en Python",
                    "Crea un script en Python que sume dos números",
                    "Genera un código en JavaScript", "Escribe código Java",
                    "Haz un programa que ordene una lista",
                    "Write a Python function", "Generate code in Python",
                    "Write a script that sorts an array",
                    "Cómo hago un for loop en Python",
                    "Dame un ejemplo de recursividad",
                    # Math / calculations
                    "Cuánto es 2 más 2", "Calcula la raíz cuadrada de 144",
                    "Resuelve esta ecuación", "What is 15 percent of 200",
                    "Cuál es la fórmula del área de un círculo",
                    # General knowledge (not document-specific)
                    "Cuál es la capital de Francia", "What is the capital of Japan",
                    "Quién fue Albert Einstein", "En qué año se fundó la ONU",
                    "Cómo funciona la fotosíntesis", "Qué es machine learning",
                    "Explica qué es una red neuronal", "How does gravity work",
                    # Translations / language
                    "Traduce esto al inglés", "Translate this to Spanish",
                    "Cómo se dice 'contrato' en inglés",
                    # Writing assistance (not document-related)
                    "Escribe un poema sobre la primavera",
                    "Redacta un email de agradecimiento genérico",
                    "Ayúdame a escribir una carta de presentación",
                    # Conversions / utilities
                    "Convierte 100 dólares a euros", "Cuántas millas son 10 kilómetros",
                    "Qué hora es en Tokio",
                ],
            )

            # Document actions — queries that require ReAct tools (email, forge, search).
            # Mapped to document_query in classify_intent() to ensure ReAct loop routing.
            # This route prevents general_knowledge from capturing action queries like
            # "enviar por correo..." or "renueva el contrato...".
            document_action = Route(
                name="document_action",
                score_threshold=0.65,
                utterances=[
                    # Email sending
                    "Envía este documento por correo", "Manda un email con el contrato",
                    "Enviar por correo a juan@empresa.com", "Remite el informe por email",
                    "Reenvía el documento al cliente", "Send this document by email",
                    "Envía el contrato adjunto por correo electrónico",
                    "Manda el PDF por email a recursos humanos",
                    # Document modification / forge
                    "Renueva el contrato cambiando la fecha", "Modifica la fecha de fin del contrato",
                    "Actualiza los datos del contrato", "Cambia la fecha de vencimiento a 2027",
                    "Renueva este contrato de duración determinada",
                    "Modifica el importe del salario en el contrato",
                    "Actualizar la dirección del empleado en el documento",
                    "Cambiar el nombre del trabajador en el contrato",
                    # Document generation from existing
                    "Genera un nuevo contrato basado en este", "Crea una versión actualizada del contrato",
                    "Genera un documento a partir de esta plantilla",
                    # Save / persist
                    "Guarda el documento en el sistema", "Indexa este archivo",
                    "Almacena el contrato generado",
                    # Search specific documents
                    "Busca los contratos de duración determinada", "Encuentra las facturas del mes pasado",
                    "Muestra las nóminas de enero", "Localiza el expediente del empleado",
                    "Busca documentos que venzan pronto",
                ],
            )

            self._router = RouterLayer(
                encoder=encoder,
                routes=[conversational, identity, general_knowledge, document_action],
                auto_sync="local",
            )
            self._initialized = True
            logger.info("IntentSemanticRouter initialized with 4 routes")

        except Exception as e:
            logger.error(f"IntentSemanticRouter init failed: {e}")
            self._initialized = False

    def classify(self, query: str) -> Optional[str]:
        """Return route name or None if no match.

        Maps document_action → document_query so it routes to ReAct loop.
        """
        if not self._initialized:
            self.initialize()
        if not self._router:
            return None

        try:
            result = self._router(query)
            if result is not None and result.name is not None:
                name = result.name.lower()
                # document_action is a semantic route that captures action queries
                # (email, forge, search) — map to document_query for ReAct routing
                if name == "document_action":
                    return "document_query"
                return name
            return None
        except Exception as e:
            logger.warning(f"IntentRouter semantic classify error: {e}")
            return None


# Singleton (lazy)
_intent_router: Optional[IntentSemanticRouter] = None


def _get_intent_router() -> IntentSemanticRouter:
    global _intent_router
    if _intent_router is None:
        _intent_router = IntentSemanticRouter()
        _intent_router.initialize()
    return _intent_router


async def _llm_classify_intent(query: str) -> Optional[str]:
    """LLM-based intent classification fallback."""
    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        from app.agents.llm_models import get_planner_model

        system_prompt = (
            "Eres Emma, coordinadora de un sistema multi-agente. "
            "Clasifica la intención del usuario en una de estas etiquetas: "
            "CONVERSATIONAL, IDENTITY, GENERAL_KNOWLEDGE, DOCUMENT_QUERY. "
            "Usa GENERAL_KNOWLEDGE para preguntas generales que NO requieren buscar ni "
            "modificar documentos del usuario (código, matemáticas, traducciones, cultura general). "
            "Usa DOCUMENT_QUERY cuando el usuario: "
            "1) pregunta sobre SUS documentos, contratos, facturas, legislación; "
            "2) pide ENVIAR un email con un documento; "
            "3) pide MODIFICAR, RENOVAR o ACTUALIZAR un documento existente; "
            "4) pide BUSCAR documentos específicos (facturas, contratos, nóminas). "
            "Responde SOLO con la etiqueta."
        )

        model = get_planner_model().bind(temperature=0.0, max_tokens=10)
        response = await model.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Consulta: {query}\nEtiqueta:"),
        ])

        if not response or not response.content:
            return None

        label = response.content.strip().upper()
        if "CONVERSATIONAL" in label:
            return "conversational"
        if "IDENTITY" in label:
            return "identity"
        if "GENERAL_KNOWLEDGE" in label:
            return "general_knowledge"
        if "DOCUMENT_QUERY" in label:
            return "document_query"
        return None
    except Exception as e:
        logger.warning(f"IntentRouter LLM fallback failed: {e}")
        return None


def _is_definitional_query(query: str) -> bool:
    """
    Detect definitional queries that should ALWAYS be document_query.

    Patterns like "qué es X", "what is X", "define X" are never greetings,
    even if the semantic router matches them to "qué tal" / "qué pasa".
    """
    import re
    query_lower = query.lower().strip()

    # Spanish definitional patterns
    # "qué es X", "qué son X", "qué significa X", "cuál es X"
    if re.match(r"^¿?qu[ée]\s+(es|son|significa|era|eran)\s+\w", query_lower):
        return True
    if re.match(r"^¿?cu[aá]l\s+(es|son|era|eran)\s+\w", query_lower):
        return True
    # "explica X", "explícame X", "define X", "háblame de X"
    if re.match(r"^(explica|expl[ií]came|define|h[aá]blame\s+de|dime\s+qu[ée])\s+\w", query_lower):
        return True

    # English definitional patterns
    if re.match(r"^what\s+(is|are|does|was|were)\s+\w", query_lower):
        return True
    if re.match(r"^(define|explain|tell\s+me\s+about)\s+\w", query_lower):
        return True

    # Check for law/legal acronyms after "qué" (LOE, LOMLOE, RGPD, etc.)
    if re.search(r"\b(loe|lomloe|lode|lou|losu|rgpd|lopdgdd|lprl|lisos|et|lgss)\b", query_lower):
        return True

    return False


async def classify_intent(query: str) -> Tuple[str, float]:
    """
    Hybrid intent classification.

    Returns:
        (intent_name, confidence) where intent is one of:
        "conversational", "identity", "general_knowledge", "document_query"
    """
    # Tier 0: Rule-based pre-filter for definitional queries
    # These are NEVER greetings, even if semantic router matches them
    if _is_definitional_query(query):
        logger.debug(f"IntentRouter rule-based: document_query (definitional) for '{query[:40]}'")
        return "document_query", 0.95

    # Tier 1: Semantic Router (~1-3ms)
    # Includes document_action route → mapped to document_query in classify()
    router = _get_intent_router()
    semantic_result = router.classify(query)

    if semantic_result is not None:
        logger.debug(f"IntentRouter semantic match: {semantic_result} for '{query[:40]}'")
        return semantic_result, 0.85

    # Tier 2: LLM fallback (~200ms)
    llm_result = await _llm_classify_intent(query)
    if llm_result is not None:
        logger.debug(f"IntentRouter LLM match: {llm_result} for '{query[:40]}'")
        return llm_result, 0.9

    # Tier 3: Default
    logger.debug(f"IntentRouter default: document_query for '{query[:40]}'")
    return "document_query", 0.5
