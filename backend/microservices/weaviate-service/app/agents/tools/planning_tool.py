"""
PlanningTool - Gestion de planes con pasos y estados.

Basado en el patron OpenManus:
https://github.com/FoundationAgents/OpenManus/blob/main/app/tool/planning.py

Este modulo implementa la gestion de planes de ejecucion con:
- Estados de pasos (NOT_STARTED, IN_PROGRESS, COMPLETED, BLOCKED)
- Asignacion de agentes a pasos
- Seguimiento de progreso

FRAMEWORK: Qwen-Agent
Reference: https://github.com/QwenLM/Qwen-Agent

MIGRATION NOTE:
- Updated internal ChatAgent usage to Qwen-Agent's Assistant pattern
- This is a utility class, not a tool that needs @register_tool
"""
from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import uuid
import logging

logger = logging.getLogger(__name__)


class PlanStepStatus(str, Enum):
    """Estados posibles de un paso del plan."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"

    @classmethod
    def get_marker(cls, status: str) -> str:
        """Obtiene el marcador visual para un estado."""
        markers = {
            cls.NOT_STARTED.value: "[ ]",
            cls.IN_PROGRESS.value: "[->]",
            cls.COMPLETED.value: "[v]",
            cls.BLOCKED.value: "[!]",
        }
        return markers.get(status, "[ ]")

    @classmethod
    def get_emoji(cls, status: str) -> str:
        """Obtiene el emoji para un estado."""
        emojis = {
            cls.NOT_STARTED.value: "pending",
            cls.IN_PROGRESS.value: "running",
            cls.COMPLETED.value: "done",
            cls.BLOCKED.value: "error",
        }
        return emojis.get(status, "pending")


@dataclass
class PlanStep:
    """Un paso individual del plan."""
    index: int
    description: str
    agent: str
    status: str = PlanStepStatus.NOT_STARTED.value
    note: str = ""
    result: Optional[Dict] = None

    def to_dict(self) -> Dict:
        """Convierte a diccionario."""
        return {
            "index": self.index,
            "description": self.description,
            "agent": self.agent,
            "status": self.status,
            "marker": PlanStepStatus.get_marker(self.status),
            "emoji": PlanStepStatus.get_emoji(self.status),
            "note": self.note,
            "has_result": self.result is not None,
        }


@dataclass
class Plan:
    """Un plan de ejecucion con multiples pasos."""
    plan_id: str
    title: str
    steps: List[PlanStep] = field(default_factory=list)
    analysis_type: str = "general"
    tenant_id: str = ""
    document_id: str = ""
    created_at: str = ""

    def __post_init__(self):
        """Inicializacion post-creacion."""
        if not self.created_at:
            from datetime import datetime
            self.created_at = datetime.utcnow().isoformat()

    @property
    def total_steps(self) -> int:
        """Total de pasos."""
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        """Pasos completados."""
        return sum(1 for s in self.steps if s.status == PlanStepStatus.COMPLETED.value)

    @property
    def progress_percentage(self) -> int:
        """Porcentaje de progreso."""
        if not self.steps:
            return 0
        return int(self.completed_steps / self.total_steps * 100)

    @property
    def is_complete(self) -> bool:
        """Indica si el plan esta completado."""
        return self.completed_steps == self.total_steps and self.total_steps > 0

    @property
    def current_step(self) -> Optional[PlanStep]:
        """Obtiene el paso actual (primer no completado)."""
        for step in self.steps:
            if step.status in [PlanStepStatus.NOT_STARTED.value, PlanStepStatus.IN_PROGRESS.value]:
                return step
        return None

    def to_dict(self) -> Dict:
        """Convierte a diccionario."""
        return {
            "plan_id": self.plan_id,
            "title": self.title,
            "analysis_type": self.analysis_type,
            "tenant_id": self.tenant_id,
            "document_id": self.document_id,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "progress_percentage": self.progress_percentage,
            "is_complete": self.is_complete,
            "created_at": self.created_at,
            "steps": [s.to_dict() for s in self.steps],
        }


class PlanningTool:
    """
    Herramienta para crear y gestionar planes de ejecucion.

    Basado en el patron OpenManus, permite:
    - Crear planes con pasos y agentes asignados
    - Actualizar estados de pasos
    - Monitorear progreso
    - Obtener el paso actual
    """

    # Planes predefinidos por tipo de analisis
    PREDEFINED_PLANS = {
        "legal": [
            ("Analizar estructura y partes del contrato", "ContractAgent"),
            ("Revisar aspectos laborales (periodo de prueba, jornada, vacaciones)", "LaborAgent"),
            ("Verificar cumplimiento normativo (RGPD, proteccion datos)", "ComplianceAgent"),
            ("Generar resumen ejecutivo con recomendaciones", "SummarizerAgent"),
        ],
        "contract": [
            ("Analizar estructura y partes del contrato", "ContractAgent"),
            ("Revisar aspectos laborales segun Estatuto de los Trabajadores", "LaborAgent"),
            ("Verificar cumplimiento normativo", "ComplianceAgent"),
            ("Generar resumen ejecutivo con recomendaciones", "SummarizerAgent"),
        ],
        "labor": [
            ("Analizar tipo de contrato y modalidad contractual", "LaborAgent"),
            ("Verificar periodo de prueba segun Art. 14 ET", "LaborAgent"),
            ("Revisar jornada laboral, salario y vacaciones", "LaborAgent"),
            ("Verificar cumplimiento del Estatuto de los Trabajadores", "ComplianceAgent"),
            ("Generar resumen con hallazgos laborales", "SummarizerAgent"),
        ],
        "compliance": [
            ("Identificar tratamiento de datos personales", "ComplianceAgent"),
            ("Verificar bases legales y consentimientos", "ComplianceAgent"),
            ("Evaluar medidas de seguridad", "ComplianceAgent"),
            ("Generar informe de cumplimiento", "SummarizerAgent"),
        ],
        "financial": [
            ("Analizar terminos financieros y montos", "ContractAgent"),
            ("Verificar obligaciones de pago", "ContractAgent"),
            ("Identificar riesgos financieros", "ContractAgent"),
            ("Generar resumen financiero", "SummarizerAgent"),
        ],
        "general": [
            ("Analizar contenido del documento", "ContractAgent"),
            ("Identificar puntos clave y riesgos", "ContractAgent"),
            ("Generar resumen", "SummarizerAgent"),
        ],
    }

    def __init__(self):
        """Inicializa el PlanningTool."""
        self.plans: Dict[str, Plan] = {}
        self._current_plan_id: Optional[str] = None

    def create_plan(
        self,
        title: str,
        steps: List[Tuple[str, str]],
        analysis_type: str = "general",
        tenant_id: str = "",
        document_id: str = "",
    ) -> str:
        """
        Crea un nuevo plan con pasos y agentes asignados.

        Args:
            title: Titulo del plan
            steps: Lista de tuplas (descripcion, agente)
            analysis_type: Tipo de analisis
            tenant_id: ID del tenant
            document_id: ID del documento

        Returns:
            ID del plan creado
        """
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"

        plan_steps = [
            PlanStep(index=i, description=desc, agent=agent)
            for i, (desc, agent) in enumerate(steps)
        ]

        self.plans[plan_id] = Plan(
            plan_id=plan_id,
            title=title,
            steps=plan_steps,
            analysis_type=analysis_type,
            tenant_id=tenant_id,
            document_id=document_id,
        )

        self._current_plan_id = plan_id
        logger.info(f"Plan creado: {plan_id} con {len(steps)} pasos")

        return plan_id

    def create_plan_for_analysis(
        self,
        analysis_type: str,
        tenant_id: str,
        document_id: str,
        task_description: str = "",
    ) -> str:
        """
        Crea un plan predefinido segun el tipo de analisis.

        Args:
            analysis_type: Tipo de analisis (legal, compliance, financial, general)
            tenant_id: ID del tenant
            document_id: ID del documento
            task_description: Descripcion adicional de la tarea

        Returns:
            ID del plan creado
        """
        steps = self.PREDEFINED_PLANS.get(
            analysis_type,
            self.PREDEFINED_PLANS["general"]
        )

        title = f"Analisis {analysis_type}"
        if task_description:
            title += f": {task_description[:50]}"

        return self.create_plan(
            title=title,
            steps=steps,
            analysis_type=analysis_type,
            tenant_id=tenant_id,
            document_id=document_id,
        )

    def get_plan(self, plan_id: str = None) -> Optional[Plan]:
        """
        Obtiene un plan por ID.

        Args:
            plan_id: ID del plan (usa el actual si None)

        Returns:
            Plan o None si no existe
        """
        pid = plan_id or self._current_plan_id
        return self.plans.get(pid)

    def get_current_step(self, plan_id: str = None) -> Optional[Tuple[int, str, str]]:
        """
        Obtiene el paso actual (primer no completado).

        Args:
            plan_id: ID del plan (usa el actual si None)

        Returns:
            Tupla (indice, descripcion, agente) o None si todos completados
        """
        plan = self.get_plan(plan_id)
        if not plan:
            return None

        step = plan.current_step
        if step:
            return (step.index, step.description, step.agent)
        return None

    def mark_step(
        self,
        step_index: int,
        status: PlanStepStatus,
        note: str = "",
        result: Dict = None,
        plan_id: str = None,
    ) -> bool:
        """
        Actualiza el estado de un paso.

        Args:
            step_index: Indice del paso
            status: Nuevo estado
            note: Nota opcional
            result: Resultado opcional
            plan_id: ID del plan (usa el actual si None)

        Returns:
            True si se actualizo correctamente
        """
        plan = self.get_plan(plan_id)
        if not plan:
            return False

        if 0 <= step_index < len(plan.steps):
            step = plan.steps[step_index]
            step.status = status.value
            if note:
                step.note = note
            if result:
                step.result = result

            emoji = PlanStepStatus.get_emoji(status.value)
            logger.info(f"{emoji} Paso {step_index + 1}: {status.value} - {step.description[:50]}")
            return True

        return False

    def mark_step_in_progress(self, step_index: int, plan_id: str = None) -> bool:
        """Marca un paso como en progreso."""
        return self.mark_step(step_index, PlanStepStatus.IN_PROGRESS, plan_id=plan_id)

    def mark_step_completed(
        self,
        step_index: int,
        note: str = "",
        result: Dict = None,
        plan_id: str = None,
    ) -> bool:
        """Marca un paso como completado."""
        return self.mark_step(
            step_index,
            PlanStepStatus.COMPLETED,
            note=note,
            result=result,
            plan_id=plan_id,
        )

    def mark_step_blocked(
        self,
        step_index: int,
        error: str = "",
        plan_id: str = None,
    ) -> bool:
        """Marca un paso como bloqueado."""
        return self.mark_step(
            step_index,
            PlanStepStatus.BLOCKED,
            note=f"Error: {error}",
            plan_id=plan_id,
        )

    def get_progress(self, plan_id: str = None) -> Dict:
        """
        Obtiene el progreso del plan.

        Args:
            plan_id: ID del plan (usa el actual si None)

        Returns:
            Diccionario con informacion de progreso
        """
        plan = self.get_plan(plan_id)
        if not plan:
            return {"error": "Plan no encontrado"}

        return plan.to_dict()

    def get_all_results(self, plan_id: str = None) -> List[Dict]:
        """
        Obtiene todos los resultados de los pasos completados.

        Args:
            plan_id: ID del plan (usa el actual si None)

        Returns:
            Lista de resultados
        """
        plan = self.get_plan(plan_id)
        if not plan:
            return []

        return [
            step.result
            for step in plan.steps
            if step.result is not None
        ]

    def format_progress_text(self, plan_id: str = None) -> str:
        """
        Formatea el progreso como texto legible.

        Args:
            plan_id: ID del plan (usa el actual si None)

        Returns:
            Texto formateado con el progreso
        """
        plan = self.get_plan(plan_id)
        if not plan:
            return "Plan no encontrado"

        lines = [
            f"Plan: {plan.title}",
            f"Progreso: {plan.completed_steps}/{plan.total_steps} ({plan.progress_percentage}%)",
            "",
        ]

        for step in plan.steps:
            marker = PlanStepStatus.get_marker(step.status)
            lines.append(f"  {marker} {step.index + 1}. {step.description}")
            if step.note:
                lines.append(f"      -> {step.note}")

        return "\n".join(lines)

    # Mapeo de tipos de documento a analisis predefinidos
    DOCUMENT_TYPE_TO_ANALYSIS = {
        "contrato_laboral": "labor",
        "contrato_trabajo": "labor",
        "contrato_temporal": "labor",
        "contrato_indefinido": "labor",
        "contrato_practicas": "labor",
        "contrato_arrendamiento": "real_estate",
        "arrendamiento": "real_estate",
        "compraventa_inmueble": "real_estate",
        "nda": "compliance",
        "confidencialidad": "compliance",
        "proteccion_datos": "compliance",
        "politica_privacidad": "compliance",
        "factura": "financial",
        "presupuesto": "financial",
        "contrato_servicios": "contract",
        "contrato_mercantil": "contract",
        "escritura": "contract",
        "poder_notarial": "contract",
        "estatutos": "contract",
        "normativa_educativa": "education",
        "matricula": "education",
        "beca": "education",
    }

    async def detect_document_type(
        self,
        document_content: str,
        llm_cfg: dict,
    ) -> dict:
        """
        Detecta el tipo de documento usando LLM (Qwen-Agent).

        Analiza la estructura y contenido del documento para clasificarlo
        y determinar que agentes especializados son mas relevantes.

        Args:
            document_content: Contenido completo del documento
            llm_cfg: LLM configuration dict for Qwen-Agent

        Returns:
            {
                "document_type": "contrato_laboral",
                "document_type_display": "Contrato de Trabajo Temporal",
                "confidence": 0.95,
                "key_sections": ["objeto", "duracion", "salario", "periodo de prueba"],
                "suggested_agents": ["LaborAgent", "ComplianceAgent", "SummarizerAgent"],
                "analysis_type": "labor"
            }
        """
        from qwen_agent.agents import Assistant

        content_preview = document_content[:5000] if document_content else ""

        if not content_preview:
            return self._default_detection_result()

        detection_prompt = f"""Analiza el siguiente documento y clasificalo.

DOCUMENTO (primeros 5000 caracteres):
---
{content_preview}
---

RESPONDE UNICAMENTE en formato JSON con esta estructura exacta:
```json
{{
  "document_type": "tipo_interno (ej: contrato_laboral, arrendamiento, nda, factura, contrato_servicios...)",
  "document_type_display": "Nombre legible (ej: Contrato de Trabajo Temporal)",
  "confidence": 0.0-1.0,
  "key_sections": ["lista", "de", "secciones", "detectadas"],
  "suggested_agents": ["LaborAgent", "ComplianceAgent"]
}}
```

AGENTES DISPONIBLES para suggested_agents:
- ContractAgent: Contratos generales, clausulas, obligaciones
- LaborAgent: Contratos laborales, Art. 14 ET, jornada, vacaciones
- ComplianceAgent: RGPD, cumplimiento normativo, proteccion datos
- FiscalAgent: IVA, retenciones, aspectos tributarios
- RealEstateAgent: Arrendamientos, compraventa inmuebles
- PrivacyAgent: Politicas privacidad, cookies, consentimientos
- EducationAgent: Normativa educativa, becas, matriculas
- SummarizerAgent: Resumenes (SIEMPRE incluir)

REGLAS:
1. Analiza el contenido real, no inventes
2. confidence debe reflejar certeza real (0.5 si dudas)
3. key_sections solo secciones que REALMENTE existen en el documento
4. suggested_agents: 2-4 agentes maximo, ordenados por relevancia
5. Responde SOLO con el JSON, sin texto adicional"""

        try:
            detector = Assistant(
                llm=llm_cfg,
                name="DocumentDetector",
                description="Clasificador de documentos legales experto.",
                system_message="Eres un clasificador de documentos legales experto. Analizas estructura y contenido para determinar el tipo exacto de documento. Responde SOLO con JSON valido.",
            )

            logger.info("Detectando tipo de documento con LLM...")
            response = detector.run([{"role": "user", "content": detection_prompt}])

            # Extract response from Qwen-Agent
            response_text = ""
            for chunk in response:
                if hasattr(chunk, 'content'):
                    response_text += chunk.content
                elif isinstance(chunk, dict) and 'content' in chunk:
                    response_text += chunk['content']
                elif isinstance(chunk, str):
                    response_text += chunk

            # Parse JSON
            import re
            import json
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                detection_data = json.loads(json_match.group())

                doc_type = detection_data.get("document_type", "documento_general")
                doc_type_display = detection_data.get("document_type_display", "Documento")
                confidence = float(detection_data.get("confidence", 0.5))
                key_sections = detection_data.get("key_sections", [])
                suggested_agents = detection_data.get("suggested_agents", ["ContractAgent"])

                valid_agents = {
                    "ContractAgent", "LaborAgent", "ComplianceAgent",
                    "FiscalAgent", "RealEstateAgent", "PrivacyAgent",
                    "EducationAgent", "SummarizerAgent", "SearchAgent",
                    "AnalystAgent"
                }
                suggested_agents = [a for a in suggested_agents if a in valid_agents]
                if not suggested_agents:
                    suggested_agents = ["ContractAgent"]

                if "SummarizerAgent" not in suggested_agents:
                    suggested_agents.append("SummarizerAgent")

                analysis_type = self.DOCUMENT_TYPE_TO_ANALYSIS.get(
                    doc_type.lower().replace(" ", "_"),
                    "legal"
                )

                result = {
                    "document_type": doc_type,
                    "document_type_display": doc_type_display,
                    "confidence": confidence,
                    "key_sections": key_sections[:10],
                    "suggested_agents": suggested_agents,
                    "analysis_type": analysis_type,
                }

                logger.info(f"Documento detectado: {doc_type_display} (confianza: {confidence:.2f})")
                logger.info(f"   Secciones: {', '.join(key_sections[:5])}...")
                logger.info(f"   Agentes sugeridos: {', '.join(suggested_agents)}")

                return result

        except Exception as e:
            logger.warning(f"Error detectando tipo de documento: {e}")

        return self._default_detection_result()

    def _default_detection_result(self) -> dict:
        """Resultado de deteccion por defecto cuando falla el LLM."""
        return {
            "document_type": "documento_general",
            "document_type_display": "Documento General",
            "confidence": 0.3,
            "key_sections": [],
            "suggested_agents": ["ContractAgent", "ComplianceAgent", "SummarizerAgent"],
            "analysis_type": "legal",
        }

    async def generate_dynamic_plan(
        self,
        document_content: str,
        task: str,
        tenant_id: str,
        document_id: str,
        llm_cfg: dict,
        document_type_info: dict = None,
    ) -> str:
        """
        Genera un plan dinamico basado en el contenido del documento usando LLM.

        El LLM analiza el documento y genera pasos especificos segun:
        - Tipo de documento detectado (si se proporciona document_type_info)
        - Clausulas y secciones presentes
        - Posibles riesgos identificados

        Args:
            document_content: Contenido del documento (truncado a 8000 chars)
            task: Tarea solicitada por el usuario
            tenant_id: ID del tenant
            document_id: ID del documento
            llm_cfg: LLM configuration dict for Qwen-Agent
            document_type_info: Resultado de detect_document_type() (opcional)

        Returns:
            ID del plan generado
        """
        from qwen_agent.agents import Assistant

        content_preview = document_content[:8000] if document_content else ""

        type_context = ""
        if document_type_info:
            doc_type = document_type_info.get("document_type_display", "Documento")
            confidence = document_type_info.get("confidence", 0.5)
            sections = document_type_info.get("key_sections", [])
            suggested = document_type_info.get("suggested_agents", [])

            type_context = f"""
TIPO DE DOCUMENTO DETECTADO:
- Tipo: {doc_type} (confianza: {confidence:.0%})
- Secciones identificadas: {', '.join(sections[:7]) if sections else 'No identificadas'}
- Agentes sugeridos: {', '.join(suggested)}

IMPORTANTE: Usa esta informacion para generar un plan ESPECIFICO para este tipo de documento.
"""

        planning_prompt = f"""Genera un plan de analisis especifico para el siguiente documento.
{type_context}
DOCUMENTO (primeros 8000 caracteres):
---
{content_preview}
---

TAREA SOLICITADA: {task}

AGENTES DISPONIBLES (usa EXACTAMENTE estos nombres):
- ContractAgent: Analisis de clausulas contractuales, partes, obligaciones
- LaborAgent: Derecho laboral, periodo de prueba, jornada, Art. 14 ET, convenios
- ComplianceAgent: Cumplimiento normativo, RGPD, proteccion de datos
- FiscalAgent: Aspectos fiscales, tributarios, IVA, retenciones
- RealEstateAgent: Contratos inmobiliarios, arrendamiento, compraventa
- PrivacyAgent: Privacidad, cookies, consentimientos, derechos ARCO
- EducationAgent: Normativa educativa, becas, matriculas
- SummarizerAgent: Resumenes ejecutivos (SIEMPRE incluir al final)

GENERA UN PLAN con 3-6 pasos en formato JSON:
```json
{{
  "document_type": "tipo detectado",
  "steps": [
    {{"description": "Paso especifico con referencia a articulos/clausulas reales", "agent": "NombreAgente"}},
    ...
  ]
}}
```

REGLAS CRITICAS:
1. CADA paso debe ser ESPECIFICO para ESTE documento, mencionando clausulas/articulos reales
2. NO uses descripciones genericas como "Analizar estructura" - se especifico
3. Si es contrato laboral: menciona articulos del ET especificos (Art. 14 periodo prueba, Art. 34 jornada)
4. Si hay clausulas de penalizacion, exclusividad, no competencia: analizalas explicitamente
5. SummarizerAgent SIEMPRE es el ultimo paso
6. Maximo 6 pasos para eficiencia
7. Responde SOLO con el JSON"""

        try:
            planner = Assistant(
                llm=llm_cfg,
                name="PlannerAgent",
                description="Experto en analisis de documentos legales.",
                system_message="Eres un experto en analisis de documentos legales. Generas planes de analisis estructurados en JSON.",
            )

            logger.info("Generando plan dinamico con LLM...")
            response = planner.run([{"role": "user", "content": planning_prompt}])

            response_text = ""
            for chunk in response:
                if hasattr(chunk, 'content'):
                    response_text += chunk.content
                elif isinstance(chunk, dict) and 'content' in chunk:
                    response_text += chunk['content']
                elif isinstance(chunk, str):
                    response_text += chunk

            import re
            import json
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                plan_data = json.loads(json_match.group())

                document_type = plan_data.get("document_type", "documento")
                steps_data = plan_data.get("steps", [])

                if steps_data:
                    valid_agents = {
                        "ContractAgent", "LaborAgent", "ComplianceAgent",
                        "FiscalAgent", "RealEstateAgent", "PrivacyAgent",
                        "EducationAgent", "SummarizerAgent", "SearchAgent",
                        "AnalystAgent"
                    }

                    steps = []
                    for step in steps_data:
                        agent = step.get("agent", "ContractAgent")
                        desc = step.get("description", "Analizar documento")

                        if agent not in valid_agents:
                            logger.warning(f"Agente invalido '{agent}', usando ContractAgent")
                            agent = "ContractAgent"

                        steps.append((desc, agent))

                    if steps and steps[-1][1] != "SummarizerAgent":
                        steps.append(("Generar resumen ejecutivo con hallazgos", "SummarizerAgent"))

                    logger.info(f"Plan dinamico generado: {document_type} con {len(steps)} pasos")

                    return self.create_plan(
                        title=f"Analisis de {document_type}",
                        steps=steps,
                        analysis_type="dynamic",
                        tenant_id=tenant_id,
                        document_id=document_id,
                    )

        except Exception as e:
            logger.warning(f"Error generando plan dinamico: {e}, usando plan predefinido")

        fallback_analysis_type = "legal"
        if document_type_info:
            fallback_analysis_type = document_type_info.get("analysis_type", "legal")
            logger.info(f"Fallback inteligente: usando plan '{fallback_analysis_type}' basado en tipo detectado")
        else:
            logger.info("Usando plan 'legal' predefinido como fallback")

        return self.create_plan_for_analysis(
            analysis_type=fallback_analysis_type,
            tenant_id=tenant_id,
            document_id=document_id,
            task_description=task,
        )


# Singleton para uso global
_planning_tool_instance = None


def get_planning_tool() -> PlanningTool:
    """Obtiene la instancia singleton del PlanningTool."""
    global _planning_tool_instance
    if _planning_tool_instance is None:
        _planning_tool_instance = PlanningTool()
    return _planning_tool_instance
