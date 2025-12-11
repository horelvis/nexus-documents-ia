"""
Document Analysis Flow - Native Microsoft Agent Framework Implementation

This module provides a document analysis workflow that uses the native
Microsoft Agent Framework (SwarmWorkflow) while emitting events compatible
with the existing frontend format.

Replaces PlanningFlow for document analysis with better parallelization
and native agent handoffs.
"""

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from app.agents import get_orchestrator
from app.agents.config import agent_config, WorkflowType

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result from document analysis."""
    success: bool
    summary: str
    risks: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    agents_used: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    error: Optional[str] = None


class DocumentAnalysisFlow:
    """
    Document Analysis using Native Microsoft Agent Framework.

    This flow uses SwarmWorkflow for parallel agent execution while
    emitting events in the format expected by the frontend:
    - start
    - plan_created
    - step_start
    - step_complete
    - complete

    Benefits over PlanningFlow:
    - Native agent handoffs (SwarmBuilder)
    - Better parallelization
    - Simpler architecture
    """

    def __init__(self):
        self._orchestrator = None
        self._initialized = False

    def _ensure_initialized(self):
        """Lazy initialization of orchestrator."""
        if not self._initialized:
            self._orchestrator = get_orchestrator()
            self._initialized = True

    async def execute(
        self,
        task: str,
        tenant_id: str,
        document_id: str,
        document_content: str,
        analysis_type: str = "general",
        **kwargs
    ) -> AnalysisResult:
        """
        Execute document analysis (non-streaming).

        Consumes the streaming execution and returns final result.

        Args:
            task: Analysis task description
            tenant_id: Tenant identifier
            document_id: Document being analyzed
            document_content: Full text of the document
            analysis_type: Type of analysis

        Returns:
            AnalysisResult with findings and metadata
        """
        start_time = time.time()
        final_result = {}
        agents_used = []
        error = None

        try:
            async for event in self.execute_stream(
                task=task,
                tenant_id=tenant_id,
                document_id=document_id,
                document_content=document_content,
                analysis_type=analysis_type,
                **kwargs
            ):
                event_type = event.get("event", "")

                if event_type == "complete":
                    data = event.get("data", {})
                    final_result = data.get("final_result", {})
                    agents_used = data.get("agents_used", [])

                elif event_type == "error":
                    error = event.get("data", {}).get("error", "Unknown error")

        except Exception as e:
            error = str(e)
            logger.exception(f"Document analysis execution error: {e}")

        execution_time = (time.time() - start_time) * 1000

        return AnalysisResult(
            success=error is None,
            summary=final_result.get("summary", ""),
            risks=final_result.get("risks", []),
            recommendations=final_result.get("recommendations", []),
            confidence_score=final_result.get("confidence_score", 0.0),
            agents_used=agents_used,
            execution_time_ms=execution_time,
            error=error,
        )

    async def execute_stream(
        self,
        task: str,
        tenant_id: str,
        document_id: str,
        document_content: str,
        analysis_type: str = "general",
        **kwargs
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute document analysis with streaming events.

        Emits events compatible with the existing frontend format.

        Args:
            task: Analysis task description
            tenant_id: Tenant identifier
            document_id: Document being analyzed
            document_content: Full text of the document
            analysis_type: Type of analysis (general, contract, compliance, etc.)

        Yields:
            Events in format: {"event": "...", "data": {...}}
        """
        self._ensure_initialized()
        start_time = time.time()

        # Emit start event
        yield {
            "event": "start",
            "data": {
                "message": "Iniciando análisis con agentes especializados...",
                "document_id": document_id,
                "analysis_type": analysis_type,
            }
        }

        # Create synthetic plan for frontend compatibility
        plan_steps = self._create_analysis_plan(analysis_type)

        yield {
            "event": "plan_created",
            "data": {
                "message": f"Plan de análisis creado: {len(plan_steps)} pasos",
                "steps": plan_steps,
                "total_steps": len(plan_steps),
                "progress": 5,
            }
        }

        try:
            # Build the analysis task with document context
            analysis_task = self._build_analysis_task(
                task=task,
                tenant_id=tenant_id,
                document_id=document_id,
                document_content=document_content,
                analysis_type=analysis_type,
            )

            # Track agent activity and findings
            total_steps = len(plan_steps)
            findings = {"risks": [], "recommendations": [], "summary": ""}
            agents_seen = set()
            last_agent = None
            last_step_index = -1  # Track which plan step we're on
            accumulated_content = ""

            # Build agent -> plan index mapping for consistent step_index
            agent_to_plan_index = {}
            for step in plan_steps:
                agent_name_lower = step.get("agent", "").lower()
                agent_to_plan_index[agent_name_lower] = step.get("index", 0)
                # Also add partial matches (e.g., "triage" matches "TriageAgent")
                for key in ["triage", "search", "contract", "compliance", "labor", "fiscal", "legal", "tax", "summarizer"]:
                    if key in agent_name_lower:
                        agent_to_plan_index[key] = step.get("index", 0)

            def get_plan_index(agent_name: str) -> int:
                """Get plan index for an agent, with fuzzy matching."""
                name_lower = agent_name.lower()
                # Direct match
                if name_lower in agent_to_plan_index:
                    return agent_to_plan_index[name_lower]
                # Partial match
                for key, idx in agent_to_plan_index.items():
                    if key in name_lower or name_lower in key:
                        return idx
                # Default: use last known index + 1, capped at total_steps - 1
                return min(last_step_index + 1, total_steps - 1) if last_step_index >= 0 else 0

            # SYNTHETIC PROGRESS: Track if we received any intermediate events
            # If not, we'll emit synthetic progress based on the plan
            received_any_events = False

            # Execute using orchestrator with SWARM workflow
            async for event in self._orchestrator.execute_stream(
                query=analysis_task,
                tenant_id=tenant_id,
                workflow_type=WorkflowType.SWARM,
            ):
                event_type = event.get("type", "")
                logger.debug(f"[DocumentAnalysisFlow] Received event: type={event_type}, keys={list(event.keys())}")

                if event_type == "message":
                    received_any_events = True
                    agent_name = event.get("agent", "unknown")
                    content = event.get("content", "")

                    # Detect agent changes (handoffs)
                    if agent_name != last_agent and agent_name != "unknown":
                        # Get the plan index for this agent
                        step_index = get_plan_index(agent_name)
                        logger.info(f"[DocumentAnalysisFlow] Agent change: {last_agent} -> {agent_name} (step_index={step_index})")

                        # Complete previous step if there was one
                        if last_agent and last_step_index >= 0:
                            step_findings = self._extract_findings(accumulated_content)
                            findings["risks"].extend(step_findings.get("risks", []))
                            findings["recommendations"].extend(step_findings.get("recommendations", []))

                            yield {
                                "event": "step_complete",
                                "data": {
                                    "step": last_step_index + 1,  # 1-indexed for display
                                    "step_index": last_step_index,  # 0-indexed for frontend state
                                    "agent": last_agent,
                                    "findings": step_findings.get("risks", []) + step_findings.get("recommendations", []),
                                    "findings_count": len(step_findings.get("risks", [])) + len(step_findings.get("recommendations", [])),
                                    "progress": int(10 + ((last_step_index + 1) / total_steps) * 70),
                                }
                            }
                            accumulated_content = ""

                        # Start new step
                        agents_seen.add(agent_name)
                        last_agent = agent_name
                        last_step_index = step_index

                        # Find matching plan step or use agent name
                        step_desc = self._get_step_description(agent_name, plan_steps, step_index)

                        yield {
                            "event": "step_start",
                            "data": {
                                "step": step_index + 1,  # 1-indexed for display
                                "step_index": step_index,  # 0-indexed for frontend state
                                "total_steps": total_steps,
                                "agent": agent_name,
                                "description": step_desc,
                                "progress": int(10 + (step_index / total_steps) * 70),
                            }
                        }

                    # Accumulate content for finding extraction
                    accumulated_content += content + "\n"

                elif event_type == "final":
                    # Final response from orchestrator
                    final_content = event.get("content", "")
                    accumulated_content += final_content
                    logger.info(f"[DocumentAnalysisFlow] Received final event, content length: {len(final_content)}")

                elif event_type == "error":
                    yield {
                        "event": "error",
                        "data": {
                            "message": event.get("content", "Error en análisis"),
                            "error": str(event.get("content", "")),
                        }
                    }

            # If we didn't receive any intermediate events, emit synthetic progress
            if not received_any_events:
                logger.warning("[DocumentAnalysisFlow] No intermediate events received, emitting synthetic progress")
                for step_idx in range(total_steps):
                    step = plan_steps[step_idx]
                    # Emit step_start
                    yield {
                        "event": "step_start",
                        "data": {
                            "step": step_idx + 1,
                            "step_index": step_idx,
                            "total_steps": total_steps,
                            "agent": step.get("agent", "Agent"),
                            "description": step.get("description", "Procesando..."),
                            "progress": int(10 + (step_idx / total_steps) * 70),
                        }
                    }
                    await asyncio.sleep(0.5)  # Brief delay for visual feedback
                    # Emit step_complete
                    yield {
                        "event": "step_complete",
                        "data": {
                            "step": step_idx + 1,
                            "step_index": step_idx,
                            "agent": step.get("agent", "Agent"),
                            "findings": [],
                            "findings_count": 0,
                            "progress": int(10 + ((step_idx + 1) / total_steps) * 70),
                        }
                    }
                    agents_seen.add(step.get("agent", "Agent"))

            # Complete final step
            if accumulated_content:
                step_findings = self._extract_findings(accumulated_content)
                findings["risks"].extend(step_findings.get("risks", []))
                findings["recommendations"].extend(step_findings.get("recommendations", []))
                findings["summary"] = step_findings.get("summary", "")

                if last_step_index >= 0:
                    yield {
                        "event": "step_complete",
                        "data": {
                            "step": last_step_index + 1,  # 1-indexed for display
                            "step_index": last_step_index,  # 0-indexed for frontend state
                            "agent": last_agent or "Summarizer",
                            "findings": step_findings.get("risks", []) + step_findings.get("recommendations", []),
                            "findings_count": len(step_findings.get("risks", [])) + len(step_findings.get("recommendations", [])),
                            "progress": 85,
                        }
                    }

            execution_time = (time.time() - start_time) * 1000

            # Emit complete event with final results
            yield {
                "event": "complete",
                "data": {
                    "message": "Análisis completado",
                    "progress": 100,
                    "execution_time_ms": execution_time,
                    "agents_used": list(agents_seen),
                    "final_result": {
                        "summary": findings.get("summary", "Análisis completado."),
                        "risks": findings["risks"],
                        "recommendations": findings["recommendations"],
                        "confidence_score": 0.85,
                        "analysis_type": analysis_type,
                    }
                }
            }

        except asyncio.TimeoutError:
            yield {
                "event": "error",
                "data": {
                    "message": "Timeout en análisis",
                    "error": "El análisis excedió el tiempo límite",
                }
            }
        except Exception as e:
            logger.exception(f"Document analysis error: {e}")
            yield {
                "event": "error",
                "data": {
                    "message": f"Error en análisis: {str(e)}",
                    "error": str(e),
                }
            }

    def _create_analysis_plan(self, analysis_type: str) -> List[Dict[str, Any]]:
        """
        Create a synthetic plan for frontend display.

        NOTE: Uses 0-based index for consistency with step_index in events.
        The frontend expects step_index to match the array index of currentPlan.
        """
        base_steps = [
            {"index": 0, "description": "Triaje y clasificación del documento", "agent": "TriageAgent"},
            {"index": 1, "description": "Búsqueda de contexto relevante", "agent": "SearchAgent"},
        ]

        if analysis_type in ("contract", "general"):
            base_steps.append({
                "index": len(base_steps),
                "description": "Análisis de cláusulas contractuales",
                "agent": "ContractAgent"
            })

        if analysis_type in ("compliance", "general"):
            base_steps.append({
                "index": len(base_steps),
                "description": "Verificación de cumplimiento normativo",
                "agent": "ComplianceAgent"
            })

        base_steps.append({
            "index": len(base_steps),
            "description": "Síntesis y recomendaciones finales",
            "agent": "SummarizerAgent"
        })

        return base_steps

    def _build_analysis_task(
        self,
        task: str,
        tenant_id: str,
        document_id: str,
        document_content: str,
        analysis_type: str,
    ) -> str:
        """Build the complete analysis task for the orchestrator."""
        # Truncate content if too long (8000 chars ≈ 2000-3000 tokens)
        # This leaves room for system prompt + response within 16K context
        max_content = 8000
        if len(document_content) > max_content:
            document_content = document_content[:max_content] + "\n\n[... contenido truncado ...]"

        # Definir el flujo de agentes según el tipo de análisis
        workflow_instructions = self._get_workflow_instructions(analysis_type)

        return f"""TAREA: Analizar documento en profundidad

TIPO DE ANÁLISIS: {analysis_type}
DOCUMENTO ID: {document_id}
TENANT: {tenant_id}

{workflow_instructions}

INSTRUCCIONES DE ANÁLISIS:
1. Analiza el documento completo identificando riesgos
2. Para cada riesgo, indica:
   - Título descriptivo
   - Descripción del riesgo
   - Severidad (high, medium, low)
   - Cita textual del documento (quote)
3. Proporciona recomendaciones concretas
4. Al finalizar, incluye un resumen ejecutivo

FORMATO DE SALIDA:
Estructura tu respuesta con secciones claras:
- RIESGOS: Lista de riesgos identificados
- RECOMENDACIONES: Lista de acciones sugeridas
- RESUMEN: Conclusión general del análisis

=== DOCUMENTO ===
{document_content}
=== FIN DOCUMENTO ===

Cuando hayas completado el análisis, incluye "TASK_COMPLETE" al final.
"""

    def _get_workflow_instructions(self, analysis_type: str) -> str:
        """Get workflow instructions based on analysis type."""
        if analysis_type == "contract":
            return """FLUJO DE AGENTES REQUERIDO:
1. TriageAgent: Clasifica el documento como CONTRATO
2. ContractAgent: Analiza cláusulas, obligaciones, plazos, penalizaciones y riesgos contractuales
3. SummarizerAgent: Genera resumen ejecutivo con hallazgos principales

IMPORTANTE: Este es un documento de tipo CONTRATO. Debes hacer handoff a ContractAgent para el análisis principal."""

        elif analysis_type == "legal":
            return """FLUJO DE AGENTES REQUERIDO:
1. TriageAgent: Clasifica el documento como LEGAL/JUDICIAL
2. LegalAgent: Analiza resoluciones, sentencias, demandas, recursos y actos administrativos
3. SummarizerAgent: Genera resumen ejecutivo con hallazgos principales

IMPORTANTE: Este es un documento LEGAL/JUDICIAL. Debes hacer handoff a LegalAgent para el análisis principal."""

        elif analysis_type == "tax" or analysis_type == "irpf":
            return """FLUJO DE AGENTES REQUERIDO:
1. TriageAgent: Clasifica el documento como DECLARACIÓN DE LA RENTA
2. TaxDeclarationAgent: Analiza rendimientos, deducciones, retenciones y resultado de la declaración
3. SummarizerAgent: Genera resumen ejecutivo con oportunidades de optimización fiscal

IMPORTANTE: Este es un documento de DECLARACIÓN DE LA RENTA (IRPF). Debes hacer handoff a TaxDeclarationAgent."""

        elif analysis_type == "compliance":
            return """FLUJO DE AGENTES REQUERIDO:
1. TriageAgent: Clasifica el documento para análisis de CUMPLIMIENTO
2. ComplianceAgent: Verifica cumplimiento GDPR/RGPD, protección de datos, políticas de privacidad
3. SummarizerAgent: Genera resumen ejecutivo con hallazgos de cumplimiento

IMPORTANTE: Este documento requiere análisis de CUMPLIMIENTO NORMATIVO. Debes hacer handoff a ComplianceAgent."""

        elif analysis_type == "labor":
            return """FLUJO DE AGENTES REQUERIDO:
1. TriageAgent: Clasifica el documento como LABORAL
2. LaborAgent: Analiza contratos de trabajo, nóminas, bajas IT, despidos, finiquitos, Seguridad Social
3. SummarizerAgent: Genera resumen ejecutivo con hallazgos laborales

IMPORTANTE: Este es un documento LABORAL. Debes hacer handoff a LaborAgent para el análisis completo."""

        else:  # general
            return """FLUJO DE AGENTES REQUERIDO:
1. TriageAgent: Clasifica el tipo de documento según su contenido
2. Agente especializado según tipo detectado:
   - Documentos laborales (nóminas, contratos trabajo, bajas, despidos) → LaborAgent
   - Contratos comerciales (arrendamiento, servicios) → ContractAgent
   - Documentos judiciales/legales → LegalAgent
   - Declaraciones de renta/IRPF → TaxDeclarationAgent
   - Cumplimiento/privacidad → ComplianceAgent
3. SummarizerAgent: Genera resumen ejecutivo

IMPORTANTE: Lee el contenido del documento para identificar el tipo y usar el agente correcto."""

    def _get_step_description(
        self,
        agent_name: str,
        plan_steps: List[Dict],
        current_step: int
    ) -> str:
        """Get step description from plan or generate from agent name."""
        # Try to find matching step in plan
        for step in plan_steps:
            if step.get("agent", "").lower() in agent_name.lower():
                return step.get("description", agent_name)

        # Fallback descriptions based on agent name
        agent_descriptions = {
            "triage": "Clasificando tipo de documento",
            "search": "Buscando contexto relevante",
            "contract": "Analizando cláusulas contractuales",
            "compliance": "Verificando cumplimiento normativo",
            "labor": "Analizando aspectos laborales",
            "fiscal": "Revisando implicaciones fiscales",
            "summarizer": "Generando resumen y recomendaciones",
        }

        for key, desc in agent_descriptions.items():
            if key in agent_name.lower():
                return desc

        return f"Procesando con {agent_name}"

    def _extract_findings(self, content: str) -> Dict[str, Any]:
        """
        Extract risks, recommendations, and summary from agent output.

        Parses structured LLM output looking for risk/recommendation items
        with Title, Description, Severity, and Quote fields.
        """
        findings = {
            "risks": [],
            "recommendations": [],
            "summary": "",
        }

        if not content:
            return findings

        # Extract summary
        summary_match = re.search(r'(?:RESUMEN|Resumen|Summary)[:\s]*([^\n]+(?:\n(?![A-Z]{3,})[^\n]+)*)', content)
        if summary_match:
            findings["summary"] = summary_match.group(1).strip()

        # Pattern to match structured risk/recommendation items
        # Look for items with Título/Title and optionally Cita/Quote
        item_pattern = re.compile(
            r'(?:^|\n)\s*[-•*]?\s*\**(?:Título|Title|Riesgo|Risk)\**[:\s]*\*?([^*\n]+)\*?'
            r'(?:.*?(?:Descripción|Description)[:\s]*([^\n]+))?'
            r'(?:.*?(?:Severidad|Severity)[:\s]*\*?(\w+)\*?)?'
            r'(?:.*?(?:Cita|Quote)[:\s]*["\']?([^"\'\n]+)["\']?)?',
            re.IGNORECASE | re.DOTALL
        )

        # Also try simpler pattern for numbered items
        simple_pattern = re.compile(
            r'(?:^|\n)\s*\d+[.)]\s*\**([^:*\n]+)\**[:\s]*([^\n]+)',
            re.MULTILINE
        )

        # Extract from structured format
        for match in item_pattern.finditer(content):
            title = match.group(1).strip() if match.group(1) else ""
            description = match.group(2).strip() if match.group(2) else title
            severity = match.group(3).strip().lower() if match.group(3) else "medium"
            quote = match.group(4).strip() if match.group(4) else ""

            # Skip metadata lines (these are not real findings)
            if self._is_metadata_line(title):
                continue

            # Validate severity
            if severity not in ("high", "medium", "low"):
                severity = "medium"

            # Only add if we have a meaningful title
            if title and len(title) > 5:
                item = {
                    "id": f"r_{uuid.uuid4().hex[:8]}",
                    "type": "risk",
                    "title": title[:100],
                    "description": description[:500] if description else title,
                    "severity": severity,
                    "quote": quote if quote and not self._is_metadata_line(quote) else "",
                }
                findings["risks"].append(item)

        # If no structured items found, try simple extraction
        if not findings["risks"]:
            for match in simple_pattern.finditer(content):
                title = match.group(1).strip()
                description = match.group(2).strip()

                if self._is_metadata_line(title):
                    continue

                if title and len(title) > 5:
                    findings["risks"].append({
                        "id": f"r_{uuid.uuid4().hex[:8]}",
                        "type": "risk",
                        "title": title[:100],
                        "description": description[:500],
                        "severity": "medium",
                        "quote": "",
                    })

        return findings

    def _is_metadata_line(self, text: str) -> bool:
        """Check if text is a metadata label rather than actual content."""
        if not text:
            return True

        text_lower = text.lower().strip()

        # Metadata patterns to filter out
        metadata_patterns = [
            r'^título\**:?',
            r'^descripción\**:?',
            r'^severidad\**:?',
            r'^cita\**:?',
            r'^quote\**:?',
            r'^severity\**:?',
            r'^\[?\d+\]\**',  # Citation references like [1]**
            r'^\*{2,}',  # Lines starting with **
            r'^high\*?$',
            r'^medium\*?$',
            r'^low\*?$',
        ]

        for pattern in metadata_patterns:
            if re.match(pattern, text_lower):
                return True

        # Too short to be meaningful
        if len(text) < 5:
            return True

        return False


# Singleton instance
_document_analysis_flow: Optional[DocumentAnalysisFlow] = None


def get_document_analysis_flow() -> DocumentAnalysisFlow:
    """Get or create the document analysis flow singleton."""
    global _document_analysis_flow
    if _document_analysis_flow is None:
        _document_analysis_flow = DocumentAnalysisFlow()
    return _document_analysis_flow
