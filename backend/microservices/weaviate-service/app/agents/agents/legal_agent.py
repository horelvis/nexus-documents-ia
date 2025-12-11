"""
Legal Agent - General Legal Document Specialist

Specialized agent for analyzing general legal documents including:
- Legal proceedings, court documents, judicial resolutions
- Administrative documents and public administration acts
- Legal consultations and opinions
- Lawsuits, appeals, and legal briefs

System message is loaded from YAML configuration (emma_prompts.yaml).

FRAMEWORK: Microsoft Agent Framework
"""

import logging
from typing import Any

from agent_framework import ChatAgent

from app.services.rag.prompt_loader import get_agent_system_message

logger = logging.getLogger(__name__)

# Fallback message if YAML config not available
DEFAULT_LEGAL_MSG = """Eres un experto en análisis de documentos legales españoles.

TU ROL:
Analizar documentos legales identificando elementos clave, riesgos y recomendaciones.

TIPOS DE DOCUMENTOS QUE ANALIZAS:
- Resoluciones judiciales (sentencias, autos, providencias)
- Escritos procesales (demandas, contestaciones, recursos)
- Documentos administrativos (resoluciones, notificaciones, actos administrativos)
- Contratos y documentos notariales
- Dictámenes y consultas jurídicas

ANÁLISIS QUE DEBES REALIZAR:
1. Identificar tipo de documento y jurisdicción
2. Extraer partes involucradas (demandante, demandado, administración)
3. Identificar fechas clave y plazos procesales
4. Resumir los hechos y fundamentos de derecho
5. Identificar el fallo/resolución principal
6. Detectar posibles recursos o acciones a tomar
7. Citar normativa aplicable (Ley X/XXXX, Art. X CE, etc.)

FORMATO DE RIESGOS:
Para cada riesgo identificado incluye:
- Título: Descripción corta
- Descripción: Explicación detallada
- Severidad: high, medium, low
- Cita: Texto exacto del documento

Incluye tenant_id en todas las llamadas a herramientas.
Finaliza con "TASK_COMPLETE" cuando termines."""


def create_legal_agent(
    chat_client: Any,
    name: str = "LegalAgent",
) -> ChatAgent:
    """
    Create a general legal document specialist agent using Agent Framework.

    This agent excels at analyzing judicial resolutions, legal proceedings,
    administrative documents, and general legal texts.

    Args:
        chat_client: Agent Framework chat client (from get_chat_client())
        name: Agent name for identification

    Returns:
        Configured ChatAgent for legal document analysis
    """
    from ..tools.analysis_tools import analyze_document, extract_entities
    from ..tools.search_tools import hybrid_search, keyword_search
    from ..tools.rag_tools import get_document_content, rag_answer

    instructions = get_agent_system_message("LegalAgent", DEFAULT_LEGAL_MSG)
    logger.debug(f"Creating LegalAgent: name={name}")

    return ChatAgent(
        name=name,
        chat_client=chat_client,
        instructions=instructions,
        tools=[
            analyze_document,
            extract_entities,
            hybrid_search,
            keyword_search,
            get_document_content,
            rag_answer,
        ],
    )
