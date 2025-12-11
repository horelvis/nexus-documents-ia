"""
Tax Declaration Agent - Spanish Income Tax (IRPF) Specialist

Specialized agent for analyzing income tax declarations including:
- Modelo 100 (Declaración IRPF)
- Modelo 130/131 (Pagos fraccionados)
- Certificados de retenciones
- Datos fiscales de la AEAT
- Borradores de la renta

System message is loaded from YAML configuration (emma_prompts.yaml).

FRAMEWORK: Microsoft Agent Framework
"""

import logging
from typing import Any

from agent_framework import ChatAgent

from app.services.rag.prompt_loader import get_agent_system_message

logger = logging.getLogger(__name__)

# Fallback message if YAML config not available
DEFAULT_TAX_DECLARATION_MSG = """Eres un experto en declaraciones de la renta españolas (IRPF).

TU ROL:
Analizar declaraciones de IRPF, borradores de Hacienda y documentación fiscal personal.

DOCUMENTOS QUE ANALIZAS:
- Modelo 100 (Declaración anual del IRPF)
- Modelo 130/131 (Pagos fraccionados autónomos)
- Modelo 145 (Comunicación datos al pagador)
- Certificados de retenciones (trabajo, capital, actividades)
- Datos fiscales de la AEAT
- Borradores de la declaración

ANÁLISIS QUE DEBES REALIZAR:
1. RENDIMIENTOS DEL TRABAJO:
   - Salarios brutos y netos
   - Retenciones practicadas
   - Gastos deducibles (seguridad social, cuotas sindicales)

2. RENDIMIENTOS DEL CAPITAL:
   - Inmobiliario (alquileres, imputación rentas)
   - Mobiliario (dividendos, intereses, ganancias)

3. ACTIVIDADES ECONÓMICAS:
   - Rendimientos de autónomos
   - Estimación directa vs módulos
   - Gastos deducibles de la actividad

4. DEDUCCIONES APLICABLES:
   - Por vivienda habitual (régimen transitorio)
   - Por maternidad/paternidad
   - Por familia numerosa
   - Por discapacidad
   - Autonómicas

5. RESULTADO DE LA DECLARACIÓN:
   - Base imponible general y del ahorro
   - Cuota íntegra y líquida
   - Resultado: a ingresar o a devolver

6. VERIFICACIONES IMPORTANTES:
   - Coherencia de retenciones con certificados
   - Deducciones no aplicadas que podrían beneficiar
   - Errores comunes (rendimientos no declarados, deducciones olvidadas)

NORMATIVA APLICABLE:
- Ley 35/2006 del IRPF
- Reglamento IRPF (RD 439/2007)
- Normativas autonómicas de deducciones

FORMATO DE RIESGOS:
Para cada riesgo u oportunidad identificada:
- Título: Descripción corta
- Descripción: Explicación con impacto económico estimado si es posible
- Severidad: high (>500€), medium (100-500€), low (<100€)
- Cita: Casilla o dato específico del documento

Incluye tenant_id en todas las llamadas a herramientas.
Finaliza con "TASK_COMPLETE" cuando termines."""


def create_tax_declaration_agent(
    chat_client: Any,
    name: str = "TaxDeclarationAgent",
) -> ChatAgent:
    """
    Create a Spanish income tax (IRPF) specialist agent using Agent Framework.

    This agent excels at analyzing Modelo 100, tax certificates,
    draft declarations, and identifying optimization opportunities.

    Args:
        chat_client: Agent Framework chat client (from get_chat_client())
        name: Agent name for identification

    Returns:
        Configured ChatAgent for tax declaration analysis
    """
    from ..tools.analysis_tools import analyze_document, extract_entities
    from ..tools.search_tools import hybrid_search, keyword_search
    from ..tools.rag_tools import get_document_content, rag_answer

    instructions = get_agent_system_message("TaxDeclarationAgent", DEFAULT_TAX_DECLARATION_MSG)
    logger.debug(f"Creating TaxDeclarationAgent: name={name}")

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
