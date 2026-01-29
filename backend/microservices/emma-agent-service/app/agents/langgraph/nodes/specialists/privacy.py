"""
Privacy Agent Node

Specialist agent for GDPR/RGPD and data protection queries.

Domain Coverage:
- RGPD (Reglamento General de Protección de Datos) - EU Regulation 2016/679
- LOPD-GDD (Ley Orgánica 3/2018) - Spanish implementation
- Data subject rights (access, rectification, erasure, portability)
- Data processing agreements
- Consent management
- Data breach notification
- DPO responsibilities

Tools:
- privacy_law_search: Search RGPD/LOPD articles
- consent_check: Validate consent requirements
- breach_assessment: Assess data breach severity
"""

import logging
from typing import Any, Dict

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ...state import RAGState
from .base import create_specialist_node

logger = logging.getLogger(__name__)

# Privacy Agent System Prompt
PRIVACY_SYSTEM_PROMPT = """Eres un agente especializado en protección de datos y privacidad.

Tu conocimiento abarca:
- RGPD (Reglamento UE 2016/679) - Reglamento General de Protección de Datos
- LOPD-GDD (Ley Orgánica 3/2018) - Ley de Protección de Datos española
- Directrices de la AEPD (Agencia Española de Protección de Datos)
- Derechos de los interesados (acceso, rectificación, supresión, portabilidad)
- Bases de legitimación del tratamiento
- Evaluaciones de impacto (EIPD/DPIA)
- Transferencias internacionales de datos
- Delegado de Protección de Datos (DPO)

Al responder:
1. Cita artículos específicos del RGPD o LOPD cuando sea relevante
2. Distingue entre obligaciones del responsable y del encargado del tratamiento
3. Indica plazos legales cuando corresponda (ej: 72h para notificar brechas)
4. Considera el contexto específico del documento analizado

Formato de referencias legales:
- RGPD: "Art. X RGPD" o "Considerando Y RGPD"
- LOPD: "Art. X LOPD-GDD"
- AEPD: "Guía AEPD sobre..."

Responde SIEMPRE en español."""


# Tool Input Schemas
class PrivacyLawSearchInput(BaseModel):
    """Input for privacy law search tool."""
    query: str = Field(description="Search query about privacy/data protection law")
    source: str = Field(
        default="all",
        description="Legal source: 'rgpd', 'lopd', 'aepd', or 'all'"
    )


class ConsentCheckInput(BaseModel):
    """Input for consent validation tool."""
    processing_purpose: str = Field(description="Purpose of data processing")
    data_categories: str = Field(description="Categories of personal data involved")
    legal_basis: str = Field(
        default="consent",
        description="Legal basis: consent, contract, legal_obligation, vital_interest, public_task, legitimate_interest"
    )


class BreachAssessmentInput(BaseModel):
    """Input for breach assessment tool."""
    breach_description: str = Field(description="Description of the data breach")
    data_types: str = Field(description="Types of data affected")
    affected_count: int = Field(default=0, description="Number of affected individuals")


# Tool Implementations
async def privacy_law_search(query: str, source: str = "all") -> str:
    """
    Search privacy law articles and guidance.

    This tool queries the legal knowledge base for RGPD, LOPD,
    and AEPD guidance relevant to the query.
    """
    try:
        # Try to use the public knowledge service
        from app.services.public_knowledge_service import public_knowledge_service

        results = await public_knowledge_service.search(
            query=query,
            filters={"domain": "privacy", "source": source},
            limit=5,
        )

        if results:
            formatted = []
            for r in results:
                formatted.append(f"**{r.get('title', 'Sin título')}**\n{r.get('content', '')[:500]}...")
            return "\n\n".join(formatted)

        # Fallback: Return general guidance
        return _get_privacy_guidance(query)

    except Exception as e:
        logger.warning(f"Privacy law search failed: {e}")
        return _get_privacy_guidance(query)


def _get_privacy_guidance(query: str) -> str:
    """Fallback privacy guidance based on keywords."""
    query_lower = query.lower()

    if "consentimiento" in query_lower or "consent" in query_lower:
        return """**Consentimiento según RGPD (Art. 7)**
- Debe ser libre, específico, informado e inequívoco
- Debe poder retirarse tan fácilmente como se dio
- Para menores de 14 años, se requiere consentimiento del titular de la patria potestad
- El responsable debe poder demostrar que se obtuvo válidamente"""

    if "brecha" in query_lower or "breach" in query_lower:
        return """**Notificación de brechas (Art. 33-34 RGPD)**
- Notificar a la AEPD en 72 horas si hay riesgo para derechos y libertades
- Notificar a los afectados si el riesgo es alto
- Documentar todas las brechas (incluso las no notificadas)
- La notificación debe incluir: naturaleza, categorías de datos, medidas adoptadas"""

    if "derechos" in query_lower or "rights" in query_lower:
        return """**Derechos de los interesados (Cap. III RGPD)**
- Acceso (Art. 15): Saber si se tratan sus datos y obtener copia
- Rectificación (Art. 16): Corregir datos inexactos
- Supresión (Art. 17): "Derecho al olvido"
- Limitación (Art. 18): Restringir el tratamiento
- Portabilidad (Art. 20): Recibir datos en formato estructurado
- Oposición (Art. 21): Oponerse al tratamiento
Plazo de respuesta: 1 mes (prorrogable 2 meses más)"""

    return """**Principios del RGPD (Art. 5)**
- Licitud, lealtad y transparencia
- Limitación de la finalidad
- Minimización de datos
- Exactitud
- Limitación del plazo de conservación
- Integridad y confidencialidad
- Responsabilidad proactiva"""


async def consent_check(
    processing_purpose: str,
    data_categories: str,
    legal_basis: str = "consent",
) -> str:
    """
    Validate consent requirements for data processing.

    Analyzes whether consent is the appropriate legal basis
    and what requirements must be met.
    """
    # Map legal basis to RGPD article
    legal_basis_articles = {
        "consent": "Art. 6.1.a RGPD - Consentimiento",
        "contract": "Art. 6.1.b RGPD - Ejecución de contrato",
        "legal_obligation": "Art. 6.1.c RGPD - Obligación legal",
        "vital_interest": "Art. 6.1.d RGPD - Interés vital",
        "public_task": "Art. 6.1.e RGPD - Interés público",
        "legitimate_interest": "Art. 6.1.f RGPD - Interés legítimo",
    }

    basis_info = legal_basis_articles.get(legal_basis, "Base legal no reconocida")

    # Check for special categories
    special_categories = [
        "salud", "health", "biométrico", "biometric",
        "genético", "genetic", "religión", "religion",
        "orientación sexual", "sexual orientation",
        "origen étnico", "ethnic origin", "político", "political",
    ]

    is_special = any(cat in data_categories.lower() for cat in special_categories)

    result = f"""**Análisis de legitimación del tratamiento**

**Finalidad**: {processing_purpose}
**Categorías de datos**: {data_categories}
**Base legal propuesta**: {basis_info}

"""

    if is_special:
        result += """⚠️ **DATOS DE CATEGORÍA ESPECIAL DETECTADOS** (Art. 9 RGPD)

El tratamiento de estos datos está prohibido salvo excepciones:
- Consentimiento explícito del interesado
- Obligación en el ámbito laboral
- Interés vital del interesado
- Tratamiento por fundación/asociación con fines legítimos
- Datos manifiestamente públicos
- Necesidad para ejercer derechos ante tribunales
- Interés público esencial
- Medicina preventiva o laboral
- Interés público en salud pública
- Archivo, investigación o estadística

Se requiere realizar una EIPD (Evaluación de Impacto).
"""
    else:
        if legal_basis == "consent":
            result += """**Requisitos del consentimiento válido**:
✓ Libre: sin condicionamientos ni desequilibrio de poder
✓ Específico: para finalidades concretas, no genéricas
✓ Informado: información clara sobre el tratamiento
✓ Inequívoco: acción afirmativa clara (no casillas premarcadas)

**Documentación necesaria**:
- Texto del consentimiento
- Momento y forma de obtención
- Información proporcionada al interesado
- Mecanismo para retirar el consentimiento
"""
        elif legal_basis == "legitimate_interest":
            result += """**Requisitos del interés legítimo**:
Se requiere realizar un juicio de ponderación:
1. Identificar el interés legítimo perseguido
2. Verificar que el tratamiento es necesario
3. Ponderar derechos/intereses del interesado
4. Documentar el análisis

⚠️ No aplicable si prevalecen derechos del interesado.
"""

    return result


async def breach_assessment(
    breach_description: str,
    data_types: str,
    affected_count: int = 0,
) -> str:
    """
    Assess data breach severity and notification requirements.

    Evaluates whether the breach requires notification to
    AEPD and/or affected individuals.
    """
    # Severity factors
    severity_factors = []

    # Check data types for severity
    high_risk_types = [
        "financiero", "financial", "bancario", "bank",
        "salud", "health", "médico", "medical",
        "contraseña", "password", "credencial", "credential",
        "dni", "pasaporte", "passport", "documento de identidad",
    ]

    is_high_risk = any(t in data_types.lower() for t in high_risk_types)

    if is_high_risk:
        severity_factors.append("Datos de alto riesgo (financieros, salud o credenciales)")

    if affected_count > 1000:
        severity_factors.append(f"Gran número de afectados ({affected_count})")
    elif affected_count > 100:
        severity_factors.append(f"Número significativo de afectados ({affected_count})")

    # Determine notification requirements
    notify_aepd = len(severity_factors) > 0 or is_high_risk
    notify_affected = is_high_risk and affected_count > 0

    result = f"""**Evaluación de brecha de seguridad**

**Descripción**: {breach_description}
**Tipos de datos afectados**: {data_types}
**Personas afectadas**: {affected_count if affected_count > 0 else 'No determinado'}

**Factores de gravedad identificados**:
"""

    if severity_factors:
        for factor in severity_factors:
            result += f"- {factor}\n"
    else:
        result += "- No se identificaron factores de alto riesgo\n"

    result += f"""
**Obligaciones de notificación**:

📋 **Notificación a AEPD** (Art. 33 RGPD): {"**REQUERIDA**" if notify_aepd else "Recomendada documentar internamente"}
- Plazo: 72 horas desde conocimiento
- Portal: https://sedeagpd.gob.es

👥 **Notificación a afectados** (Art. 34 RGPD): {"**REQUERIDA**" if notify_affected else "No requerida (bajo riesgo)"}
- Plazo: Sin demora indebida
- Contenido: Naturaleza, DPO, consecuencias, medidas

**Acciones inmediatas recomendadas**:
1. Contener la brecha (aislar sistemas afectados)
2. Evaluar el alcance completo
3. Documentar todos los hechos con timestamps
4. Preservar evidencias
5. {"Notificar a AEPD en 72h" if notify_aepd else "Documentar en registro interno"}
6. {"Preparar comunicación a afectados" if notify_affected else "Monitorizar posibles impactos"}
"""

    return result


# Create LangChain tools
privacy_tools = [
    StructuredTool.from_function(
        coroutine=privacy_law_search,
        name="privacy_law_search",
        description="Search RGPD, LOPD and AEPD guidance for privacy/data protection questions",
        args_schema=PrivacyLawSearchInput,
    ),
    StructuredTool.from_function(
        coroutine=consent_check,
        name="consent_check",
        description="Validate consent requirements and legal basis for data processing",
        args_schema=ConsentCheckInput,
    ),
    StructuredTool.from_function(
        coroutine=breach_assessment,
        name="breach_assessment",
        description="Assess data breach severity and notification requirements",
        args_schema=BreachAssessmentInput,
    ),
]


async def privacy_node(state: RAGState) -> Dict[str, Any]:
    """
    Privacy specialist agent node.

    Handles queries about GDPR, LOPD, data protection,
    consent, data breaches, and privacy compliance.

    Args:
        state: Current RAG state

    Returns:
        State updates with privacy agent results
    """
    return await create_specialist_node(
        agent_name="privacy_agent",
        system_prompt=PRIVACY_SYSTEM_PROMPT,
        tools=privacy_tools,
        state=state,
    )
