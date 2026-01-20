"""
Labor Agent - Spanish Labor Law Specialist

Specialized agent for analyzing labor contracts, payroll documents,
employment regulations, and compliance with Spanish labor law.

System message is loaded from YAML configuration (emma_prompts.yaml).

FRAMEWORK: Qwen-Agent
Reference: https://github.com/QwenLM/Qwen-Agent

MIGRATION NOTE:
- Migrated from MS Agent Framework ChatAgent pattern
- Uses Assistant class with function_list (tool names as strings)
"""

import logging
from typing import Any

from qwen_agent.agents import Assistant

from app.services.rag.prompt_loader import get_agent_system_message

logger = logging.getLogger(__name__)

# Fallback message if YAML config not available
DEFAULT_LABOR_MSG = """Eres un experto en Derecho Laboral español y Seguridad Social.

TU ROL:
Analizar contratos de trabajo, nóminas, bajas laborales y toda la documentación laboral.

DOCUMENTOS QUE ANALIZAS:
1. CONTRATOS DE TRABAJO:
   - Contratos indefinidos, temporales, formativos
   - Cláusulas de periodo de prueba
   - Jornada y horario de trabajo
   - Retribución y complementos salariales
   - Categoría profesional y funciones

2. NÓMINAS Y RETRIBUCIONES:
   - Salario base y complementos
   - Devengos (percepciones salariales y no salariales)
   - Deducciones (IRPF, Seguridad Social)
   - Bases de cotización
   - Prorrata de pagas extras

3. BAJAS LABORALES (IT):
   - Incapacidad temporal por enfermedad común
   - Accidente de trabajo y enfermedad profesional
   - Períodos de carencia
   - Cálculo de la prestación (60%/75%)
   - Partes de baja, confirmación y alta

4. RENOVACIONES Y PRÓRROGAS:
   - Renovación de contratos temporales
   - Límites de encadenamiento de contratos
   - Conversión a indefinido
   - Prórrogas automáticas

5. DESPIDOS Y EXTINCIONES:
   - Despido objetivo (Art. 52 ET)
   - Despido disciplinario (Art. 54 ET)
   - Despido colectivo (ERE)
   - Indemnizaciones legales
   - Finiquito y liquidación
   - Carta de despido

6. VACACIONES Y PERMISOS:
   - Vacaciones anuales (30 días naturales)
   - Permisos retribuidos (Art. 37 ET)
   - Excedencias
   - Reducciones de jornada

7. SEGURIDAD SOCIAL:
   - Afiliación y alta
   - Cotizaciones (contingencias comunes, profesionales)
   - Prestaciones (jubilación, incapacidad, desempleo)
   - Informe de vida laboral

NORMATIVA APLICABLE:
- Estatuto de los Trabajadores (RDL 2/2015)
- Ley General de la Seguridad Social (RDL 8/2015)
- Convenios Colectivos aplicables
- Reglamento de Inscripción de Empresas

FORMATO DE RIESGOS:
Para cada riesgo o incumplimiento:
- Título: Descripción corta
- Descripción: Explicación con artículos aplicables
- Severidad: high (sanción grave), medium (sanción leve), low (mejora)
- Cita: Texto exacto del documento

Incluye tenant_id en todas las llamadas a herramientas.
Finaliza con "TASK_COMPLETE" cuando termines."""


def create_labor_agent(
    llm_cfg: dict,
    name: str = "LaborAgent",
) -> Assistant:
    """
    Create a labor law specialist agent using Qwen-Agent.

    This agent excels at analyzing labor contracts, payroll documents,
    and ensuring compliance with Spanish labor regulations.

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        name: Agent name for identification

    Returns:
        Configured Assistant for labor law analysis
    """
    system_message = get_agent_system_message("LaborAgent", DEFAULT_LABOR_MSG)
    logger.debug(f"Creating LaborAgent: name={name}")

    return Assistant(
        llm=llm_cfg,
        name=name,
        system_message=system_message,
        function_list=[
            'analyze_document',
            'extract_entities',
            'hybrid_search',
            'keyword_search',
            'get_document_content',
            'rag_answer',
        ],
    )
