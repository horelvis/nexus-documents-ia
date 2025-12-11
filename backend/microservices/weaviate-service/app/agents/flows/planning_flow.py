"""
PlanningFlow - Orquestador con planificación dinámica.

Basado en el patrón OpenManus:
https://github.com/FoundationAgents/OpenManus/blob/main/app/flow/planning.py

Este módulo implementa un orquestador que:
1. Analiza la tarea y genera un plan con pasos
2. Asigna agentes especializados a cada paso
3. Ejecuta pasos secuencialmente, monitoreando estado
4. Genera resultado consolidado

FRAMEWORK: Microsoft Agent Framework
Los agentes usan ChatAgent con prompts configurados desde YAML (emma_prompts.yaml).
"""
import asyncio
import logging
import json
import time
from typing import Dict, Any, List, Optional, AsyncGenerator, Union
from dataclasses import dataclass, field

from ..tools.planning_tool import PlanningTool, PlanStepStatus, get_planning_tool
from ..model_client import get_chat_client
from ..config import agent_config
from .legal_context import search_legal_context, get_topics_for_agent

# Import all agent creators
from ..agents import (
    # Existing agents
    create_search_agent,
    create_analyst_agent,
    create_contract_agent,
    create_compliance_agent,
    create_summarizer_agent,
    # New specialized agents
    create_labor_agent,
    create_fiscal_agent,
    create_real_estate_agent,
    create_privacy_agent,
    create_education_agent,
)

logger = logging.getLogger(__name__)

# Agents that should receive legal context from BOE before execution
LEGAL_CONTEXT_AGENTS = [
    "ContractAgent",
    "ComplianceAgent",
    "LaborAgent",
    "FiscalAgent",
    "RealEstateAgent",
    "PrivacyAgent",
    "EducationAgent",
]

# Token budgets per model type (matching context_assembler.py)
# These represent safe context sizes leaving room for response generation
TOKEN_BUDGETS = {
    "vllm": 50000,       # vLLM with Ministral-3-14B (65K context - reserve 15K for response)
    "openai": 8000,      # GPT-4o-mini and above
    "anthropic": 8000,   # Claude models
    "ollama": 4000,      # Legacy/conservative for local models
    "default": 8000,
}

# Token estimation: ~4 chars per token for Spanish/English text
CHARS_PER_TOKEN = 4

# Map agent names to their factory functions
AGENT_CREATORS = {
    # Existing agents
    "SearchAgent": create_search_agent,
    "AnalystAgent": create_analyst_agent,
    "ContractAgent": create_contract_agent,
    "ComplianceAgent": create_compliance_agent,
    "SummarizerAgent": create_summarizer_agent,
    # New specialized agents
    "LaborAgent": create_labor_agent,
    "FiscalAgent": create_fiscal_agent,
    "RealEstateAgent": create_real_estate_agent,
    "PrivacyAgent": create_privacy_agent,
    "EducationAgent": create_education_agent,
}


@dataclass
class StepResult:
    """Resultado de un paso individual."""
    step_index: int
    agent: str
    success: bool
    summary: str = ""
    findings: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.5
    execution_time_ms: float = 0
    error: Optional[str] = None


@dataclass
class FlowResult:
    """Resultado completo de la ejecución del flow."""
    success: bool
    plan_id: str
    steps_completed: int
    total_steps: int
    final_result: Dict[str, Any]
    execution_log: List[Dict[str, Any]]
    execution_time_ms: float = 0


class PlanningFlow:
    """
    Orquestador estilo OpenManus con planificación dinámica.

    Proceso:
    1. Analiza la tarea y genera un plan con pasos
    2. Asigna agentes especializados ChatAgent a cada paso
    3. Ejecuta pasos secuencialmente, monitoreando estado
    4. Genera resultado consolidado

    FRAMEWORK: Microsoft Agent Framework
    Los agentes usan ChatAgent con prompts cargados desde YAML (emma_prompts.yaml).
    """

    def __init__(self):
        """Inicializa el PlanningFlow."""
        self.planning_tool = get_planning_tool()
        self._chat_client = None
        self._agents: Dict[str, Any] = {}
        logger.info("PlanningFlow initialized (using Agent Framework ChatAgent)")

    def _get_chat_client_for_agent(self, agent_name: str):
        """
        Crea un cliente de chat con temperatura específica para el agente.

        Args:
            agent_name: Nombre del agente para obtener su temperatura

        Returns:
            OpenAIChatClient configurado con temperatura del agente
        """
        chat_client = get_chat_client(agent_config, agent_name=agent_name)
        temp = agent_config.get_temperature_for_agent(agent_name)
        logger.info(f"✅ Chat client created for {agent_name}: temperature={temp}")
        return chat_client

    def _get_agent(self, agent_name: str) -> Optional[Any]:
        """
        Obtiene o crea un agente ChatAgent por nombre.

        Cada agente tiene su propio cliente con temperatura específica:
        - Agentes legales (ContractAgent, LaborAgent, etc.): temp=0.1
        - Agentes de resumen (SummarizerAgent): temp=0.3

        Args:
            agent_name: Nombre del agente (ContractAgent, LaborAgent, etc.)

        Returns:
            ChatAgent configurado o None si no existe
        """
        if agent_name not in self._agents:
            creator = AGENT_CREATORS.get(agent_name)
            if creator:
                # Cada agente obtiene su propio cliente con temperatura específica
                chat_client = self._get_chat_client_for_agent(agent_name)
                self._agents[agent_name] = creator(chat_client)
                logger.info(f"✅ ChatAgent creado: {agent_name}")
            else:
                logger.warning(f"⚠️ Agente desconocido: {agent_name}")
                return None

        return self._agents.get(agent_name)

    async def execute(
        self,
        task: str,
        tenant_id: str,
        document_id: str = None,
        document_content: str = None,
        analysis_type: str = "legal",
    ) -> FlowResult:
        """
        Ejecuta una tarea completa con planificación.

        Args:
            task: Descripción de la tarea
            tenant_id: ID del tenant
            document_id: ID del documento a analizar
            document_content: Contenido del documento (si ya está extraído)
            analysis_type: Tipo de análisis (legal, compliance, financial, general)

        Returns:
            FlowResult con el resultado completo
        """
        start_time = time.time()
        execution_log = []
        document_type_info = None

        # Fase 1: Detección de tipo de documento
        logger.info(f"📋 Creando plan para: {task[:100]}...")

        if document_content and len(document_content) > 100:
            # Fase 1a: Detectar tipo de documento
            logger.info("🔍 Fase 1: Detectando tipo de documento...")
            try:
                chat_client = self._get_chat_client_for_agent("DocumentDetector")
                document_type_info = await self.planning_tool.detect_document_type(
                    document_content=document_content,
                    chat_client=chat_client,
                )
                execution_log.append({
                    "phase": "detection",
                    "document_type": document_type_info.get("document_type_display", "Unknown"),
                    "confidence": document_type_info.get("confidence", 0),
                    "suggested_agents": document_type_info.get("suggested_agents", []),
                })
            except Exception as e:
                logger.warning(f"⚠️ Detección de tipo falló: {e}, continuando sin tipo")
                document_type_info = None

            # Fase 1b: Generar plan dinámico basado en tipo detectado
            logger.info("🤖 Fase 2: Generando plan DINÁMICO basado en tipo y contenido...")
            try:
                chat_client = self._get_chat_client_for_agent("PlannerAgent")
                plan_id = await self.planning_tool.generate_dynamic_plan(
                    document_content=document_content,
                    task=task,
                    tenant_id=tenant_id,
                    document_id=document_id or "",
                    chat_client=chat_client,
                    document_type_info=document_type_info,
                )
            except Exception as e:
                logger.warning(f"⚠️ Plan dinámico falló: {e}, usando predefinido")
                # Fallback inteligente: usar tipo detectado si existe
                fallback_type = analysis_type
                if document_type_info:
                    fallback_type = document_type_info.get("analysis_type", analysis_type)
                plan_id = self.planning_tool.create_plan_for_analysis(
                    analysis_type=fallback_type,
                    tenant_id=tenant_id,
                    document_id=document_id or "",
                    task_description=task,
                )
        else:
            # Sin contenido, usar plan predefinido
            logger.info("📋 Sin contenido de documento, usando plan predefinido")
            plan_id = self.planning_tool.create_plan_for_analysis(
                analysis_type=analysis_type,
                tenant_id=tenant_id,
                document_id=document_id or "",
                task_description=task,
            )

        plan = self.planning_tool.get_plan(plan_id)
        execution_log.append({
            "phase": "planning",
            "plan_id": plan_id,
            "steps": [s.to_dict() for s in plan.steps],
        })

        logger.info(f"📋 Plan creado con {plan.total_steps} pasos")

        # Fase 2: Ejecutar pasos
        results: List[StepResult] = []

        for step in plan.steps:
            step_start = time.time()
            logger.info(f"▶️ Ejecutando paso {step.index + 1}/{plan.total_steps}: {step.description}")

            self.planning_tool.mark_step_in_progress(step.index, plan_id)

            try:
                step_result = await self._execute_step(
                    step_index=step.index,
                    step_description=step.description,
                    agent_name=step.agent,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    document_content=document_content,
                    previous_results=results,
                )

                step_result.execution_time_ms = (time.time() - step_start) * 1000
                results.append(step_result)

                if step_result.success:
                    findings_count = len(step_result.findings)
                    self.planning_tool.mark_step_completed(
                        step.index,
                        note=f"Completado: {findings_count} hallazgos",
                        result={"findings": step_result.findings, "summary": step_result.summary},
                        plan_id=plan_id,
                    )
                    execution_log.append({
                        "phase": "execution",
                        "step": step.index,
                        "agent": step.agent,
                        "status": "completed",
                        "findings_count": findings_count,
                        "execution_time_ms": step_result.execution_time_ms,
                    })
                else:
                    self.planning_tool.mark_step_blocked(
                        step.index,
                        error=step_result.error or "Error desconocido",
                        plan_id=plan_id,
                    )
                    execution_log.append({
                        "phase": "execution",
                        "step": step.index,
                        "agent": step.agent,
                        "status": "error",
                        "error": step_result.error,
                    })

            except Exception as e:
                logger.error(f"❌ Error en paso {step.index + 1}: {e}")
                self.planning_tool.mark_step_blocked(step.index, error=str(e), plan_id=plan_id)

                results.append(StepResult(
                    step_index=step.index,
                    agent=step.agent,
                    success=False,
                    error=str(e),
                    execution_time_ms=(time.time() - step_start) * 1000,
                ))

                execution_log.append({
                    "phase": "execution",
                    "step": step.index,
                    "agent": step.agent,
                    "status": "error",
                    "error": str(e),
                })

        # Fase 3: Consolidar resultados
        progress = self.planning_tool.get_progress(plan_id)
        final_result = self._consolidate_results(results, analysis_type)

        total_time = (time.time() - start_time) * 1000

        logger.info(
            f"✅ Flow completado: {progress['completed_steps']}/{progress['total_steps']} pasos, "
            f"{len(final_result.get('risks', []))} riesgos, "
            f"{len(final_result.get('recommendations', []))} recomendaciones"
        )

        return FlowResult(
            success=progress["completed_steps"] == progress["total_steps"],
            plan_id=plan_id,
            steps_completed=progress["completed_steps"],
            total_steps=progress["total_steps"],
            final_result=final_result,
            execution_log=execution_log,
            execution_time_ms=total_time,
        )

    async def execute_stream(
        self,
        task: str,
        tenant_id: str,
        document_id: str = None,
        document_content: str = None,
        analysis_type: str = "legal",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Ejecuta una tarea con streaming de progreso.

        Yields eventos SSE con el progreso de cada paso.

        Args:
            task: Descripción de la tarea
            tenant_id: ID del tenant
            document_id: ID del documento a analizar
            document_content: Contenido del documento
            analysis_type: Tipo de análisis

        Yields:
            Dict con tipo de evento y datos
        """
        start_time = time.time()
        execution_log = []
        results: List[StepResult] = []

        # Evento inicial
        yield {
            "event": "start",
            "data": {
                "message": "Voy a analizar este documento, un momento...",
                "analysis_type": analysis_type,
            }
        }

        # Fase 1: Crear plan (dinámico si hay contenido)
        yield {
            "event": "planning",
            "data": {
                "message": "Analizando documento y creando plan...",
                "progress": 5,
            }
        }

        if document_content and len(document_content) > 100:
            # Usar LLM para generar plan basado en el contenido
            logger.info("🤖 Generando plan DINÁMICO (streaming)...")
            try:
                chat_client = self._get_chat_client_for_agent("PlannerAgent")
                plan_id = await self.planning_tool.generate_dynamic_plan(
                    document_content=document_content,
                    task=task,
                    tenant_id=tenant_id,
                    document_id=document_id or "",
                    chat_client=chat_client,
                )
            except Exception as e:
                logger.warning(f"⚠️ Plan dinámico falló: {e}, usando predefinido")
                plan_id = self.planning_tool.create_plan_for_analysis(
                    analysis_type=analysis_type,
                    tenant_id=tenant_id,
                    document_id=document_id or "",
                    task_description=task,
                )
        else:
            plan_id = self.planning_tool.create_plan_for_analysis(
                analysis_type=analysis_type,
                tenant_id=tenant_id,
                document_id=document_id or "",
                task_description=task,
            )

        plan = self.planning_tool.get_plan(plan_id)
        total_steps = plan.total_steps

        yield {
            "event": "plan_created",
            "data": {
                "plan_id": plan_id,
                "total_steps": total_steps,
                "analysis_type": plan.analysis_type,
                "title": plan.title,
                "steps": [{"index": s.index, "description": s.description, "agent": s.agent} for s in plan.steps],
                "progress": 10,
            }
        }

        execution_log.append({
            "phase": "planning",
            "plan_id": plan_id,
            "steps": [s.to_dict() for s in plan.steps],
        })

        # Fase 2: Ejecutar pasos
        base_progress = 10
        step_progress_range = 80  # 10% to 90%

        for step in plan.steps:
            step_start = time.time()
            step_progress = base_progress + int((step.index / total_steps) * step_progress_range)

            # Notificar inicio del paso
            yield {
                "event": "step_start",
                "data": {
                    "step": step.index + 1,
                    "step_index": step.index,  # 0-based index for frontend tracking
                    "total_steps": total_steps,
                    "description": step.description,
                    "agent": step.agent,
                    "message": f"▶️ {step.agent}: {step.description}",
                    "progress": step_progress,
                }
            }

            self.planning_tool.mark_step_in_progress(step.index, plan_id)

            try:
                # Execute step with intermediate events
                async for event in self._execute_step_stream(
                    step_index=step.index,
                    step_description=step.description,
                    agent_name=step.agent,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    document_content=document_content,
                    previous_results=results,
                    base_progress=step_progress,
                    total_steps=total_steps,
                ):
                    # Check if this is the final result event
                    if event.get("event") == "_step_result":
                        step_result = event.get("data")
                        break
                    else:
                        # Forward intermediate events
                        yield event

                step_result.execution_time_ms = (time.time() - step_start) * 1000
                results.append(step_result)

                step_end_progress = base_progress + int(((step.index + 1) / total_steps) * step_progress_range)

                if step_result.success:
                    findings_count = len(step_result.findings)
                    self.planning_tool.mark_step_completed(
                        step.index,
                        note=f"Completado: {findings_count} hallazgos",
                        result={"findings": step_result.findings, "summary": step_result.summary},
                        plan_id=plan_id,
                    )

                    # Include actual findings in step_complete event
                    yield {
                        "event": "step_complete",
                        "data": {
                            "step": step.index + 1,
                            "step_index": step.index,  # 0-based index for frontend tracking
                            "total_steps": total_steps,
                            "agent": step.agent,
                            "findings_count": findings_count,
                            "findings": step_result.findings[:5],  # First 5 findings for preview
                            "execution_time_ms": step_result.execution_time_ms,
                            "message": f"✅ {step.agent}: {findings_count} hallazgos encontrados",
                            "progress": step_end_progress,
                        }
                    }

                    execution_log.append({
                        "phase": "execution",
                        "step": step.index,
                        "agent": step.agent,
                        "status": "completed",
                        "findings_count": findings_count,
                        "execution_time_ms": step_result.execution_time_ms,
                    })
                else:
                    self.planning_tool.mark_step_blocked(
                        step.index,
                        error=step_result.error or "Error desconocido",
                        plan_id=plan_id,
                    )

                    yield {
                        "event": "step_error",
                        "data": {
                            "step": step.index + 1,
                            "step_index": step.index,  # 0-based index for frontend tracking
                            "total_steps": total_steps,
                            "agent": step.agent,
                            "error": step_result.error,
                            "message": f"❌ {step.agent}: {step_result.error}",
                            "progress": step_end_progress,
                        }
                    }

                    execution_log.append({
                        "phase": "execution",
                        "step": step.index,
                        "agent": step.agent,
                        "status": "error",
                        "error": step_result.error,
                    })

            except Exception as e:
                logger.error(f"❌ Error en paso {step.index + 1}: {e}")
                self.planning_tool.mark_step_blocked(step.index, error=str(e), plan_id=plan_id)

                results.append(StepResult(
                    step_index=step.index,
                    agent=step.agent,
                    success=False,
                    error=str(e),
                    execution_time_ms=(time.time() - step_start) * 1000,
                ))

                yield {
                    "event": "step_error",
                    "data": {
                        "step": step.index + 1,
                        "step_index": step.index,  # 0-based index for frontend tracking
                        "total_steps": total_steps,
                        "agent": step.agent,
                        "error": str(e),
                        "message": f"❌ Error: {str(e)}",
                        "progress": base_progress + int(((step.index + 1) / total_steps) * step_progress_range),
                    }
                }

                execution_log.append({
                    "phase": "execution",
                    "step": step.index,
                    "agent": step.agent,
                    "status": "error",
                    "error": str(e),
                })

        # Fase 3: Consolidar resultados
        yield {
            "event": "consolidating",
            "data": {
                "message": "Consolidando resultados...",
                "progress": 92,
            }
        }

        progress = self.planning_tool.get_progress(plan_id)
        final_result = self._consolidate_results(results, analysis_type)
        total_time = (time.time() - start_time) * 1000

        # Evento final con resultado completo
        yield {
            "event": "complete",
            "data": {
                "success": progress["completed_steps"] == progress["total_steps"],
                "plan_id": plan_id,
                "steps_completed": progress["completed_steps"],
                "total_steps": progress["total_steps"],
                "final_result": final_result,
                "execution_time_ms": total_time,
                "message": f"Análisis completado: {len(final_result.get('risks', []))} riesgos, {len(final_result.get('recommendations', []))} recomendaciones",
                "progress": 100,
            }
        }

    async def _execute_step(
        self,
        step_index: int,
        step_description: str,
        agent_name: str,
        tenant_id: str,
        document_id: str,
        document_content: str,
        previous_results: List[StepResult],
    ) -> StepResult:
        """
        Ejecuta un paso individual con un ChatAgent.

        Args:
            step_index: Índice del paso
            step_description: Descripción del paso
            agent_name: Nombre del agente a usar
            tenant_id: ID del tenant
            document_id: ID del documento
            document_content: Contenido del documento
            previous_results: Resultados de pasos anteriores

        Returns:
            StepResult con el resultado del paso
        """
        agent = self._get_agent(agent_name)

        if agent is None:
            return StepResult(
                step_index=step_index,
                agent=agent_name,
                success=False,
                error=f"Agente no disponible: {agent_name}",
            )

        # Construir contexto para el agente
        context = self._build_step_context(
            step_description=step_description,
            tenant_id=tenant_id,
            document_id=document_id,
            document_content=document_content,
            previous_results=previous_results,
        )

        # Buscar contexto legal relevante del BOE (PublicKnowledge)
        legal_context = ""
        if agent_name in LEGAL_CONTEXT_AGENTS:
            logger.info(f"📚 Buscando legislación relevante para {agent_name}...")
            search_query = self._extract_legal_search_query(step_description, document_content)
            topics = get_topics_for_agent(agent_name)
            # Con 32K tokens disponibles, podemos incluir 5 referencias legales
            legal_context = await search_legal_context(
                query=search_query,
                topics=topics,
                limit=5,
            )
            if legal_context:
                logger.info(f"📚 Encontrada legislación relevante ({len(legal_context)} chars)")

        try:
            # Construir tarea completa para el agente
            full_task = f"{legal_context}\n\n{context}" if legal_context else context

            # Token estimation: 1 token ≈ 4 chars for Spanish/English text
            estimated_tokens = len(full_task) // CHARS_PER_TOKEN
            token_budget = TOKEN_BUDGETS.get("vllm", TOKEN_BUDGETS["default"])

            logger.info(f"📊 Contexto para {agent_name}: {len(full_task)} chars (~{estimated_tokens} tokens estimados, límite: {token_budget})")

            # Hard limit enforcement: truncate document content if over budget
            if estimated_tokens > token_budget:
                logger.warning(f"⚠️ Contexto excede límite para {agent_name}: {estimated_tokens} > {token_budget} tokens. Truncando documento...")

                # Calculate how much we need to reduce
                legal_tokens = len(legal_context) // CHARS_PER_TOKEN if legal_context else 0
                base_context_tokens = 2000  # Reserve for prompt template and instructions
                available_doc_tokens = token_budget - legal_tokens - base_context_tokens
                max_doc_chars = available_doc_tokens * CHARS_PER_TOKEN

                logger.info(f"📊 Ajustando: legal={legal_tokens}t, disponible_doc={available_doc_tokens}t ({max_doc_chars} chars)")

                # Rebuild context with truncated document
                context = self._build_step_context(
                    step_description=step_description,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    document_content=document_content[:max_doc_chars] if document_content else "",
                    previous_results=previous_results,
                    max_content_length=max_doc_chars,
                )
                full_task = f"{legal_context}\n\n{context}" if legal_context else context

                # Verify new size
                new_estimated_tokens = len(full_task) // CHARS_PER_TOKEN
                logger.info(f"📊 Contexto ajustado para {agent_name}: {len(full_task)} chars (~{new_estimated_tokens} tokens)")

            # Ejecutar ChatAgent (Agent Framework)
            # ChatAgent.run() devuelve el contenido directamente
            result = await agent.run(full_task)

            # Extraer contenido de la respuesta
            content = self._extract_agent_response(result)

            # Parsear resultado
            parsed = self._parse_agent_content(content)

            return StepResult(
                step_index=step_index,
                agent=agent_name,
                success=True,
                summary=parsed.get("summary", ""),
                findings=parsed.get("findings", []),
                confidence=parsed.get("confidence", 0.5),
            )

        except Exception as e:
            logger.error(f"Error ejecutando agente {agent_name}: {e}")
            return StepResult(
                step_index=step_index,
                agent=agent_name,
                success=False,
                error=str(e),
            )

    async def _execute_step_stream(
        self,
        step_index: int,
        step_description: str,
        agent_name: str,
        tenant_id: str,
        document_id: str,
        document_content: str,
        previous_results: List[StepResult],
        base_progress: int,
        total_steps: int,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Ejecuta un paso con eventos intermedios (streaming).

        Yields eventos SSE intermedios y finalmente un evento "_step_result"
        con el StepResult.
        """
        agent = self._get_agent(agent_name)

        if agent is None:
            yield {
                "event": "_step_result",
                "data": StepResult(
                    step_index=step_index,
                    agent=agent_name,
                    success=False,
                    error=f"Agente no disponible: {agent_name}",
                )
            }
            return

        # Construir contexto para el agente
        context = self._build_step_context(
            step_description=step_description,
            tenant_id=tenant_id,
            document_id=document_id,
            document_content=document_content,
            previous_results=previous_results,
        )

        # Buscar contexto legal relevante del BOE (PublicKnowledge)
        legal_context = ""
        if agent_name in LEGAL_CONTEXT_AGENTS:
            yield {
                "event": "searching_legal",
                "data": {
                    "agent": agent_name,
                    "message": f"📚 Buscando legislación relevante para {agent_name}...",
                    "progress": base_progress + 2,
                }
            }

            search_query = self._extract_legal_search_query(step_description, document_content)
            topics = get_topics_for_agent(agent_name)
            # Con 32K tokens disponibles, podemos incluir 5 referencias legales
            legal_context = await search_legal_context(
                query=search_query,
                topics=topics,
                limit=5,
            )

            if legal_context:
                yield {
                    "event": "legal_found",
                    "data": {
                        "agent": agent_name,
                        "message": f"📚 Legislación encontrada ({len(legal_context)} caracteres)",
                        "legal_chars": len(legal_context),
                        "progress": base_progress + 4,
                    }
                }
            else:
                yield {
                    "event": "legal_found",
                    "data": {
                        "agent": agent_name,
                        "message": "📚 No se encontró legislación específica",
                        "legal_chars": 0,
                        "progress": base_progress + 4,
                    }
                }

        try:
            # Notify that we're executing the agent
            yield {
                "event": "agent_executing",
                "data": {
                    "agent": agent_name,
                    "message": f"🤖 Ejecutando {agent_name}...",
                    "progress": base_progress + 6,
                }
            }

            # Construir tarea completa para el agente
            full_task = f"{legal_context}\n\n{context}" if legal_context else context

            # Token estimation: 1 token ≈ 4 chars for Spanish/English text
            estimated_tokens = len(full_task) // CHARS_PER_TOKEN
            token_budget = TOKEN_BUDGETS.get("vllm", TOKEN_BUDGETS["default"])

            logger.info(f"📊 Contexto para {agent_name}: {len(full_task)} chars (~{estimated_tokens} tokens estimados, límite: {token_budget})")

            # Hard limit enforcement: truncate document content if over budget
            if estimated_tokens > token_budget:
                logger.warning(f"⚠️ Contexto excede límite para {agent_name}: {estimated_tokens} > {token_budget} tokens. Truncando documento...")

                # Calculate how much we need to reduce
                legal_tokens = len(legal_context) // CHARS_PER_TOKEN if legal_context else 0
                base_context_tokens = 2000  # Reserve for prompt template and instructions
                available_doc_tokens = token_budget - legal_tokens - base_context_tokens
                max_doc_chars = available_doc_tokens * CHARS_PER_TOKEN

                logger.info(f"📊 Ajustando: legal={legal_tokens}t, disponible_doc={available_doc_tokens}t ({max_doc_chars} chars)")

                # Rebuild context with truncated document
                context = self._build_step_context(
                    step_description=step_description,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    document_content=document_content[:max_doc_chars] if document_content else "",
                    previous_results=previous_results,
                    max_content_length=max_doc_chars,
                )
                full_task = f"{legal_context}\n\n{context}" if legal_context else context

                # Verify new size
                new_estimated_tokens = len(full_task) // CHARS_PER_TOKEN
                logger.info(f"📊 Contexto ajustado para {agent_name}: {len(full_task)} chars (~{new_estimated_tokens} tokens)")

            # Ejecutar ChatAgent con control de concurrencia
            from app.core.concurrency import get_concurrency_manager

            concurrency = get_concurrency_manager()
            async with concurrency.acquire_llm_slot(tenant_id, f"{agent_name}:{step_description[:30]}"):
                result = await agent.run(full_task)

            # Extraer contenido de la respuesta del ChatAgent
            content = self._extract_agent_response(result)

            # Parsear resultado
            parsed = self._parse_agent_content(content)

            yield {
                "event": "_step_result",
                "data": StepResult(
                    step_index=step_index,
                    agent=agent_name,
                    success=True,
                    summary=parsed.get("summary", ""),
                    findings=parsed.get("findings", []),
                    confidence=parsed.get("confidence", 0.5),
                )
            }

        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Timeout waiting for LLM slot: {agent_name}")
            yield {
                "event": "_step_result",
                "data": StepResult(
                    step_index=step_index,
                    agent=agent_name,
                    success=False,
                    error="Sistema ocupado, intente de nuevo en unos minutos",
                )
            }

        except Exception as e:
            logger.error(f"Error ejecutando agente {agent_name}: {e}")
            yield {
                "event": "_step_result",
                "data": StepResult(
                    step_index=step_index,
                    agent=agent_name,
                    success=False,
                    error=str(e),
                )
            }

    def _extract_agent_response(self, result: Any) -> str:
        """
        Extract text content from Agent Framework ChatAgent response.

        Args:
            result: Response from ChatAgent.run()

        Returns:
            String content from the agent's response
        """
        try:
            # Agent Framework ChatAgent puede devolver diferentes formatos

            # 1. Resultado directo como string
            if isinstance(result, str):
                return result

            # 2. Objeto con atributo 'content'
            if hasattr(result, 'content'):
                return str(result.content)

            # 3. Objeto con atributo 'text'
            if hasattr(result, 'text'):
                return str(result.text)

            # 4. Dict con 'content'
            if isinstance(result, dict):
                if 'content' in result:
                    return str(result['content'])
                if 'text' in result:
                    return str(result['text'])
                if 'message' in result:
                    return str(result['message'])

            # 5. Lista de mensajes (compatibilidad)
            if hasattr(result, 'messages') and result.messages:
                for msg in reversed(result.messages):
                    if hasattr(msg, 'content') and msg.content:
                        return str(msg.content)

            # Fallback: convertir a string
            return str(result)

        except Exception as e:
            logger.warning(f"Could not extract agent response: {e}")
            return str(result)

    def _extract_legal_search_query(self, step_description: str, document_content: str) -> str:
        """
        Extrae una query de búsqueda para encontrar legislación relevante.

        Args:
            step_description: Descripción del paso
            document_content: Contenido del documento

        Returns:
            Query para buscar en PublicKnowledge
        """
        # Extraer keywords relevantes del contenido
        legal_keywords = [
            "contrato", "laboral", "trabajador", "empleado", "jornada",
            "vacaciones", "despido", "indemnización", "salario", "horas extra",
            "datos personales", "privacidad", "consentimiento", "RGPD", "LOPD",
            "protección de datos", "confidencialidad", "propiedad intelectual",
            "responsabilidad", "penalización", "incumplimiento", "rescisión",
            "arrendamiento", "alquiler", "fianza", "vivienda", "hipoteca",
            "IVA", "IRPF", "factura", "impuesto", "tributario",
            "educación", "escolar", "alumno", "LOMLOE", "LOE",
        ]

        content_lower = document_content.lower()[:3000] if document_content else ""

        # Encontrar keywords que aparecen en el documento
        found_keywords = [kw for kw in legal_keywords if kw.lower() in content_lower]

        # Construir query
        query_parts = [step_description]
        if found_keywords:
            query_parts.extend(found_keywords[:5])  # Limitar a 5 keywords

        return " ".join(query_parts)

    def _build_step_context(
        self,
        step_description: str,
        tenant_id: str,
        document_id: str,
        document_content: str,
        previous_results: List[StepResult],
        max_content_length: Optional[int] = None,
    ) -> str:
        """
        Construye el contexto para un paso.

        Args:
            step_description: Descripción del paso
            tenant_id: ID del tenant
            document_id: ID del documento
            document_content: Contenido del documento
            previous_results: Resultados previos
            max_content_length: Límite de caracteres para el documento (opcional, calcula dinámicamente)

        Returns:
            Contexto formateado como string
        """
        # Limitar contenido del documento
        # Default: ~80K chars = ~20K tokens, leaving room for legal context + prompt + response
        # This can be overridden by max_content_length when token budget is tight
        if max_content_length is None:
            max_content_length = 80000  # Default: ~20K tokens for document
        content_preview = document_content[:max_content_length] if document_content else "No disponible"
        if document_content and len(document_content) > max_content_length:
            content_preview += "\n\n[... documento truncado ...]"

        # Log para monitorear tamaño del contexto
        logger.debug(f"📊 Contexto: documento={len(content_preview)} chars (límite: {max_content_length})")

        # Resumir resultados previos
        previous_summary = ""
        if previous_results:
            summaries = [r.summary for r in previous_results[-2:] if r.summary]
            if summaries:
                previous_summary = "\n".join(f"- {s}" for s in summaries)

        context = f"""Tenant ID: {tenant_id}
Document ID: {document_id}

TAREA ACTUAL: {step_description}

CONTENIDO DEL DOCUMENTO:
---
{content_preview}
---

{f"RESULTADOS DE PASOS ANTERIORES:{chr(10)}{previous_summary}" if previous_summary else ""}

INSTRUCCIONES:
1. Analiza el documento según la tarea asignada
2. Identifica hallazgos relevantes (riesgos, recomendaciones, información clave)
3. Para cada hallazgo incluye una cita textual EXACTA del documento
4. Cita la legislación aplicable con referencia específica (Art. X, BOE-A-XXXX)

FORMATO DE RESPUESTA (JSON):
{{
  "summary": "Resumen del análisis realizado",
  "findings": [
    {{
      "type": "risk|recommendation|info",
      "severity": "high|medium|low",
      "title": "Título del hallazgo",
      "description": "Descripción detallada",
      "quote": "Cita textual exacta del documento (mínimo 15 palabras)",
      "legal_reference": "Art. X de Ley Y (BOE-A-XXXX-XXXXX)",
      "legal_basis": "Explicación de por qué aplica esta ley"
    }}
  ],
  "confidence": 0.85
}}

Finaliza tu respuesta con "TASK_COMPLETE" cuando hayas terminado.
"""
        return context

    def _parse_agent_content(self, content: str) -> Dict[str, Any]:
        """
        Parsea el contenido de respuesta de un agente.

        Args:
            content: String de respuesta del agente

        Returns:
            Diccionario con summary, findings, confidence
        """
        if not content:
            return {"summary": "", "findings": [], "confidence": 0.3}

        # Intentar parsear como JSON
        try:
            json_match = self._extract_json(content)
            if json_match:
                parsed = json.loads(json_match)
                return {
                    "summary": parsed.get("summary", ""),
                    "findings": parsed.get("findings", []),
                    "confidence": parsed.get("confidence", 0.5),
                }
        except json.JSONDecodeError:
            pass

        # Si no es JSON, extraer información del texto
        return {
            "summary": content[:500] if content else "",
            "findings": [],
            "confidence": 0.3,
        }

    def _extract_json(self, text: str) -> Optional[str]:
        """
        Extrae JSON de un texto.

        Args:
            text: Texto que puede contener JSON

        Returns:
            String JSON o None
        """
        if not text:
            return None

        # Buscar JSON entre llaves
        start = text.find('{')
        if start == -1:
            return None

        # Encontrar el cierre correspondiente
        depth = 0
        for i, char in enumerate(text[start:], start):
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]

        return None

    def _consolidate_results(
        self,
        results: List[StepResult],
        analysis_type: str,
    ) -> Dict[str, Any]:
        """
        Consolida resultados de todos los pasos.

        Args:
            results: Lista de resultados de pasos
            analysis_type: Tipo de análisis

        Returns:
            Diccionario con resultado consolidado
        """
        all_risks = []
        all_recommendations = []
        all_info = []

        for result in results:
            for finding in result.findings:
                finding_type = finding.get("type", "info")

                # Asegurar campos requeridos
                finding["id"] = finding.get("id", f"{finding_type}_{len(all_risks) + len(all_recommendations) + len(all_info)}")

                if finding_type == "risk":
                    all_risks.append(finding)
                elif finding_type == "recommendation":
                    all_recommendations.append(finding)
                else:
                    all_info.append(finding)

        # Ordenar riesgos por severidad
        severity_order = {"high": 0, "medium": 1, "low": 2}
        all_risks.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 2))

        # Calcular confianza promedio (filtrar None y valores no numéricos)
        confidences = [
            r.confidence for r in results
            if r.success and r.confidence is not None and isinstance(r.confidence, (int, float))
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

        # Construir resumen
        summaries = [r.summary for r in results if r.summary]
        final_summary = summaries[-1] if summaries else "Análisis completado"

        return {
            "analysis_type": analysis_type,
            "summary": final_summary,
            "risks": all_risks,
            "recommendations": all_recommendations,
            "info": all_info,
            "total_findings": len(all_risks) + len(all_recommendations) + len(all_info),
            "confidence_score": avg_confidence,
        }

    def get_progress(self, plan_id: str = None) -> Dict[str, Any]:
        """
        Obtiene el progreso de un plan.

        Args:
            plan_id: ID del plan

        Returns:
            Diccionario con información de progreso
        """
        return self.planning_tool.get_progress(plan_id)

    def format_progress(self, plan_id: str = None) -> str:
        """
        Formatea el progreso como texto.

        Args:
            plan_id: ID del plan

        Returns:
            Texto formateado
        """
        return self.planning_tool.format_progress_text(plan_id)


# Singleton
_planning_flow_instance = None


def get_planning_flow() -> PlanningFlow:
    """Obtiene la instancia singleton del PlanningFlow."""
    global _planning_flow_instance
    if _planning_flow_instance is None:
        _planning_flow_instance = PlanningFlow()
    return _planning_flow_instance
