"""
Meta Agent Generator — LLM generates Python forward() code.

Four generation modes:
1. Seed:       Initial baselines (iteration 0)
2. Mutate:     Modify one aspect of a top strategy
3. Crossover:  Combine approaches from two strategies
4. LLM-guided: Invent new approach from scratch with archive context

Uses the strong LLM (Qwen3-235B via OpenRouter or configurable judge model)
to write code. The generated code is validated by ASTValidator before use.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from app.core.config import settings
from .sandbox import ASTValidator, SecurityError
from .schemas import ArchiveEntry, EvaluationMetrics, StrategyCandidate

logger = logging.getLogger(__name__)


class StrategyGenerator:
    """Generates forward() code via LLM."""

    def __init__(self):
        self._validator = ASTValidator()

    # ─── Public methods ──────────────────────────────────────────────────────

    async def generate_seeds(
        self,
        intent_target: str,
        sector_target: Optional[str] = None,
        available_tools: Optional[List[str]] = None,
    ) -> List[StrategyCandidate]:
        """Generate initial seed strategies (iteration 0).

        Creates 3 baseline approaches:
        - Direct search + synthesize
        - Multi-hop (search → refine → synthesize)
        - Domain-specialized (uses analyze_domain)
        """
        tools_str = ", ".join(available_tools) if available_tools else (
            "search_documents, search_legislation, get_document_content, "
            "structural_query, analyze_domain, list_sources, terminate"
        )

        strategies = []
        seed_prompts = self._get_seed_prompts(intent_target, sector_target, tools_str)

        for i, (name, prompt) in enumerate(seed_prompts):
            try:
                code = await self._generate_code(prompt, intent_target, sector_target, tools_str)
                if code:
                    candidate = StrategyCandidate(
                        name=name,
                        code=code,
                        intent_target=intent_target,
                        sector_target=sector_target,
                        description=f"Seed strategy #{i+1}: {name}",
                        generation=0,
                    )
                    strategies.append(candidate)
                    logger.info(f"Generated seed strategy: {name}")
            except Exception as e:
                logger.warning(f"Failed to generate seed '{name}': {e}")

        return strategies

    async def mutate(
        self,
        parent: ArchiveEntry,
        available_tools: Optional[List[str]] = None,
    ) -> Optional[StrategyCandidate]:
        """Mutate a strategy to improve its weakest metric."""
        tools_str = ", ".join(available_tools) if available_tools else ""

        weakest = self._find_weakest_metric(parent.metrics)
        prompt = await self._get_mutate_prompt(parent, weakest, tools_str)

        try:
            code = await self._generate_code(
                prompt,
                parent.strategy.intent_target,
                parent.strategy.sector_target,
                tools_str,
            )
            if code:
                return StrategyCandidate(
                    name=f"Mutation of {parent.strategy.name}",
                    code=code,
                    intent_target=parent.strategy.intent_target,
                    sector_target=parent.strategy.sector_target,
                    description=f"Mutated to improve {weakest}",
                    parent_id=parent.strategy.id,
                    generation=parent.strategy.generation + 1,
                )
        except Exception as e:
            logger.warning(f"Mutation failed: {e}")

        return None

    async def crossover(
        self,
        parent_a: ArchiveEntry,
        parent_b: ArchiveEntry,
        available_tools: Optional[List[str]] = None,
    ) -> Optional[StrategyCandidate]:
        """Combine approaches from two strategies."""
        tools_str = ", ".join(available_tools) if available_tools else ""

        prompt = await self._get_crossover_prompt(parent_a, parent_b, tools_str)

        try:
            code = await self._generate_code(
                prompt,
                parent_a.strategy.intent_target,
                parent_a.strategy.sector_target,
                tools_str,
            )
            if code:
                gen = max(parent_a.strategy.generation, parent_b.strategy.generation) + 1
                return StrategyCandidate(
                    name=f"Crossover: {parent_a.strategy.name} x {parent_b.strategy.name}",
                    code=code,
                    intent_target=parent_a.strategy.intent_target,
                    sector_target=parent_a.strategy.sector_target,
                    description=(
                        f"Crossover of {parent_a.strategy.name} "
                        f"(score={parent_a.metrics.composite_score:.3f}) and "
                        f"{parent_b.strategy.name} "
                        f"(score={parent_b.metrics.composite_score:.3f})"
                    ),
                    parent_id=parent_a.strategy.id,
                    generation=gen,
                )
        except Exception as e:
            logger.warning(f"Crossover failed: {e}")

        return None

    async def guided_generation(
        self,
        intent_target: str,
        sector_target: Optional[str] = None,
        archive_context: str = "",
        failure_examples: str = "",
        available_tools: Optional[List[str]] = None,
    ) -> Optional[StrategyCandidate]:
        """Generate a new strategy guided by archive context and failures."""
        tools_str = ", ".join(available_tools) if available_tools else ""

        prompt = await self._get_generator_prompt(
            intent_target, sector_target, tools_str, archive_context, failure_examples
        )

        try:
            code = await self._generate_code(prompt, intent_target, sector_target, tools_str)
            if code:
                return StrategyCandidate(
                    name="LLM-guided discovery",
                    code=code,
                    intent_target=intent_target,
                    sector_target=sector_target,
                    description="LLM-guided generation with archive + failure context",
                    generation=0,
                )
        except Exception as e:
            logger.warning(f"Guided generation failed: {e}")

        return None

    # ─── Code generation via LLM ─────────────────────────────────────────────

    async def _generate_code(
        self,
        user_prompt: str,
        intent_target: str,
        sector_target: Optional[str],
        available_tools: str,
    ) -> Optional[str]:
        """Call LLM to generate forward() code, validate, and return."""
        system_prompt = await self._get_generator_system_prompt(
            intent_target, sector_target, available_tools
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        from app.agents.llm_router import get_llm_router
        router = await get_llm_router()

        # Retry up to 2 times on empty responses (OpenRouter intermittent failures)
        text = ""
        for attempt in range(2):
            response = await router.chat(
                messages=messages,
                provider_override="openrouter",
                temperature=0.7,
                max_tokens=2048,
            )

            # Try content first, then thinking (Qwen3 sometimes puts code in <think> tags)
            text = response.content
            if not text and hasattr(response, "thinking") and response.thinking:
                text = response.thinking

            if text:
                break
            logger.warning(f"Empty LLM response (attempt {attempt+1}/2), retrying...")

        code = self._extract_code(text)
        if not code:
            logger.warning(
                "LLM response contained no valid Python code. "
                f"Content: {response.content[:150]} | "
                f"Thinking: {(getattr(response, 'thinking', '') or '')[:150]}"
            )
            return None

        # Validate AST
        try:
            self._validator.validate(code)
        except SecurityError as e:
            logger.warning(f"Generated code failed AST validation: {e}")
            return None

        return code

    def _extract_code(self, text: str) -> Optional[str]:
        """Extract Python code from LLM response.

        Handles multiple LLM output formats:
        - Markdown code blocks (```python, ```py, ```)
        - <think>...</think> prefixed content (Qwen3 thinking mode)
        - Raw code without fencing
        - Trailing explanation after the function body
        """
        # Strip Qwen3 thinking tags if present
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        # Try markdown code blocks with various languages
        patterns = [
            r"```(?:python|py)\s*\n(.*?)```",
            r"```\s*\n(.*?)```",
        ]
        for pattern in patterns:
            match = re.search(pattern, cleaned, re.DOTALL)
            if match:
                code = match.group(1).strip()
                if "async def forward" in code:
                    return code

        # Try raw code (no markdown): extract from async def forward to end of function
        if "async def forward" in cleaned:
            lines = cleaned.split("\n")
            code_lines = []
            in_function = False
            function_indent = 0

            for line in lines:
                stripped = line.strip()
                if stripped.startswith("async def forward"):
                    in_function = True
                    function_indent = len(line) - len(line.lstrip())

                if in_function:
                    # Detect end of function: unindented non-empty line after body starts
                    if code_lines and stripped and not line.startswith(" "):
                        current_indent = len(line) - len(line.lstrip())
                        if current_indent <= function_indent and not stripped.startswith("async def forward"):
                            break
                    code_lines.append(line)

            if code_lines:
                # Dedent if the function was indented (e.g., inside a markdown explanation)
                if function_indent > 0:
                    code_lines = [
                        line[function_indent:] if len(line) > function_indent else line
                        for line in code_lines
                    ]
                return "\n".join(code_lines).rstrip()

        return None

    # ─── Prompt builders ─────────────────────────────────────────────────────

    async def _get_generator_system_prompt(
        self,
        intent_target: str,
        sector_target: Optional[str],
        available_tools: str,
    ) -> str:
        """Get the generator system prompt."""
        # Try Langfuse first
        try:
            from app.services.langfuse_prompt_client import get_langfuse_prompt_client
            client = get_langfuse_prompt_client()
            prompt = await client.get_prompt(
                "emma_meta_generator",
                variables={
                    "intent_target": intent_target,
                    "sector_target": sector_target or "generic",
                    "available_tools": available_tools,
                },
            )
            if prompt:
                return prompt.content
        except Exception:
            pass

        max_llm = settings.meta_agent_max_llm_calls
        max_tool = settings.meta_agent_max_tool_calls

        return (
            "Eres un meta-agente que escribe agentes de IA en Python.\n"
            "Tu tarea: generar una función `async def forward(query: str, ctx: AgentContext) -> AgentResult`.\n\n"
            "## Primitivas disponibles\n\n"
            "ctx.llm.chat(messages: List[Dict], tools: List[Dict] = None) → LLMResponse\n"
            "  - .content: str (respuesta del LLM)\n"
            "  - .tool_calls: List[ToolCall] (si tools fue proporcionado)\n\n"
            "ctx.tools.execute(name: str, args: Dict) → ToolResult\n"
            "  - .output: str (texto para el LLM)\n"
            "  - .sources: List[Dict] (fuentes citables)\n"
            "  - .success: bool\n\n"
            "ctx.tools.list_names() → List[str]\n"
            f"  Herramientas disponibles: {available_tools}\n\n"
            "ctx.state.query → str\n"
            "ctx.state.sector → Optional[str]\n"
            "ctx.log(message: str) → None  # registra paso de razonamiento\n\n"
            "AgentResult(answer=str, sources=List[Dict])\n\n"
            "## Fuentes de datos disponibles\n"
            "- search_documents: Busca en documentos del tenant (contratos, informes, actas)\n"
            "- search_legislation: Busca legislación española del BOE (ET, LOPDGDD, RGPD, CC, LSC...)\n"
            "  args: {\"query\": str, \"domain\": str (laboral/fiscal/mercantil/civil/compliance/proteccion_datos)}\n"
            "- search_jurisprudence: Busca sentencias del CENDOJ (Tribunal Supremo, Audiencia Nacional)\n"
            "  args: {\"query\": str, \"court\": \"TS\"|\"AN\", \"max_results\": int}\n"
            "- analyze_domain: Análisis especializado por dominio (legal, labor, fiscal, contract, compliance, privacy, docgen)\n"
            "  args: {\"domain\": str, \"question\": str, \"context\": str}\n"
            "- get_document_content: Lee contenido completo de un documento por ID\n"
            "- structural_query: Consultas estructurales (listar, contar, filtrar)\n"
            "- web_search: Búsqueda web general\n\n"
            "## Restricciones de seguridad\n"
            "- NO uses import, exec, eval, open, getattr\n"
            "- NO accedas a atributos que empiecen con _\n"
            "- SOLO usa las primitivas de ctx\n"
            "- La función DEBE retornar AgentResult\n\n"
            f"## Presupuesto de recursos (MUY IMPORTANTE)\n"
            f"- Máximo {max_llm} llamadas LLM (ctx.llm.chat)\n"
            f"- Máximo {max_tool} llamadas a herramientas (ctx.tools.execute)\n"
            f"- Si excedes estos límites, la estrategia FALLA con ResourceLimitError\n"
            f"- NO iteres sobre resultados de búsqueda llamando herramientas por cada resultado\n"
            f"- Usa UNA búsqueda amplia en vez de múltiples búsquedas granulares\n"
            f"- Planifica tus llamadas: típicamente 3-5 herramientas + 1-2 LLM es suficiente\n\n"
            f"## Contexto\n"
            f"Intención objetivo: {intent_target}\n"
            f"Sector: {sector_target or 'generic'}\n\n"
            "Genera SOLO el código Python (async def forward...), sin explicación."
        )

    def _get_seed_prompts(
        self,
        intent_target: str,
        sector_target: Optional[str],
        tools_str: str,
    ) -> List[tuple]:
        """Generate seed prompt variants."""
        budget = (
            f"PRESUPUESTO: máximo {settings.meta_agent_max_llm_calls} LLM + "
            f"{settings.meta_agent_max_tool_calls} herramientas. "
            f"NO iteres llamando herramientas por cada resultado."
        )

        # Context about available data sources for richer strategies
        sources_info = (
            f"\n\n## Fuentes de datos disponibles\n"
            f"- search_documents: Documentos del tenant (contratos, informes, actas) en Weaviate\n"
            f"- search_legislation: Legislación española consolidada del BOE (ET, LOPDGDD, RGPD, LSC, CC...)\n"
            f"- search_jurisprudence: Jurisprudencia del CENDOJ (sentencias del TS y AN) — si está habilitada\n"
            f"- analyze_domain: Análisis especializado (legal, labor, fiscal, contract, compliance, privacy, docgen)\n"
            f"- get_document_content: Leer contenido completo de un documento específico\n"
            f"- structural_query: Consultas estructurales (listar, contar, filtrar documentos)\n"
            f"- web_search: Búsqueda web (si está habilitada)\n"
        )

        is_legal = sector_target and "legal" in sector_target.lower()

        return [
            (
                "Direct Search",
                f"Genera una estrategia SIMPLE para intención '{intent_target}':\n"
                f"1. Busca documentos relevantes (1 llamada)\n"
                f"2. Sintetiza la respuesta con el LLM (1 llamada)\n"
                f"Herramientas: {tools_str}\n{budget}"
            ),
            (
                "Multi-source Legal Research" if is_legal else "Multi-hop Research",
                (
                    f"Genera una función forward() que use search_documents Y search_legislation.\n"
                    f"Ejemplo de estructura (NO copies exactamente, mejóralo):\n\n"
                    f"```python\n"
                    f"async def forward(query: str, ctx: AgentContext) -> AgentResult:\n"
                    f"    docs = await ctx.tools.execute(\"search_documents\", {{\"query\": query}})\n"
                    f"    leg = await ctx.tools.execute(\"search_legislation\", {{\"query\": query}})\n"
                    f"    combined = docs.output + \"\\n---\\n\" + leg.output\n"
                    f"    resp = await ctx.llm.chat([\n"
                    f"        {{\"role\": \"system\", \"content\": \"Eres un asistente legal experto. Responde en español citando artículos de ley y documentos.\"}},\n"
                    f"        {{\"role\": \"user\", \"content\": f\"Consulta: {{query}}\\nFuentes:\\n{{combined}}\"}}\n"
                    f"    ])\n"
                    f"    return AgentResult(answer=resp.content, sources=docs.sources + leg.sources)\n"
                    f"```\n\n"
                    f"Mejora el ejemplo: añade mejor prompt, manejo de errores, o más herramientas.\n"
                    f"{budget}"
                ) if is_legal else (
                    f"Genera una estrategia MULTI-HOP para intención '{intent_target}':\n"
                    f"1. Busca documentos iniciales (1 llamada search_documents)\n"
                    f"2. Si hay referencias a legislación, búscala también (1 llamada search_legislation)\n"
                    f"3. Combina todas las fuentes para una respuesta completa (1 LLM)\n"
                    f"Total: ~3 herramientas + 1 LLM\n"
                    f"Herramientas: {tools_str}\n{budget}"
                ),
            ),
            (
                "Legal Compliance Analyzer" if is_legal else "Structured Analysis",
                (
                    f"Genera una función forward() que use search_documents, search_legislation Y analyze_domain.\n"
                    f"Ejemplo de estructura (NO copies exactamente, mejóralo):\n\n"
                    f"```python\n"
                    f"async def forward(query: str, ctx: AgentContext) -> AgentResult:\n"
                    f"    docs = await ctx.tools.execute(\"search_documents\", {{\"query\": query}})\n"
                    f"    leg = await ctx.tools.execute(\"search_legislation\", {{\"query\": query}})\n"
                    f"    analysis = await ctx.tools.execute(\"analyze_domain\", {{\"domain\": \"compliance\", \"question\": query, \"context\": docs.output + leg.output}})\n"
                    f"    resp = await ctx.llm.chat([\n"
                    f"        {{\"role\": \"system\", \"content\": \"Eres un experto en cumplimiento normativo. Genera un informe de cumplimiento en español.\"}},\n"
                    f"        {{\"role\": \"user\", \"content\": f\"Consulta: {{query}}\\nDocumentos: {{docs.output}}\\nLegislación: {{leg.output}}\\nAnálisis: {{analysis.output}}\"}}\n"
                    f"    ])\n"
                    f"    all_sources = docs.sources + leg.sources + analysis.sources\n"
                    f"    return AgentResult(answer=resp.content, sources=all_sources)\n"
                    f"```\n\n"
                    f"Mejora el ejemplo: mejor prompt, estructura del informe, o manejo de errores.\n"
                    f"{budget}"
                ) if is_legal else (
                    f"Genera una estrategia con ANÁLISIS ESTRUCTURADO para intención '{intent_target}':\n"
                    f"1. Busca documentos (1 herramienta search_documents)\n"
                    f"2. Pide al LLM que extraiga 3-5 puntos clave (1 LLM)\n"
                    f"3. Haz UNA búsqueda adicional enfocada en los puntos clave (1 herramienta)\n"
                    f"4. Sintetiza con todas las evidencias (1 LLM)\n"
                    f"Total: ~2 herramientas + 2 LLM\n"
                    f"Herramientas: {tools_str}\n{budget}"
                ),
            ),
        ]

    async def _get_mutate_prompt(
        self,
        parent: ArchiveEntry,
        weakest_metric: str,
        tools_str: str,
    ) -> str:
        """Build mutation prompt."""
        metrics_str = (
            f"answer_quality={parent.metrics.answer_quality:.2f}, "
            f"source_accuracy={parent.metrics.source_accuracy:.2f}, "
            f"instruction_following={parent.metrics.instruction_following:.2f}, "
            f"efficiency={parent.metrics.efficiency:.2f}"
        )

        max_llm = settings.meta_agent_max_llm_calls
        max_tool = settings.meta_agent_max_tool_calls

        return (
            f"Modifica la siguiente estrategia para mejorar su puntuación.\n"
            f"Puntuaciones actuales: {metrics_str}\n"
            f"Debilidad principal: {weakest_metric}\n\n"
            f"Código actual:\n```python\n{parent.strategy.code}\n```\n\n"
            f"Herramientas disponibles: {tools_str}\n\n"
            f"Aplica UNA de estas mutaciones:\n"
            f"- Agregar search_legislation (legislación BOE) si no la usa\n"
            f"- Agregar analyze_domain para análisis especializado\n"
            f"- Cambiar el prompt del sistema a español con instrucciones de citar fuentes\n"
            f"- Agregar validación de resultados (feedback loop)\n"
            f"- Mejorar la combinación de fuentes antes de la síntesis\n\n"
            f"PRESUPUESTO: máximo {max_llm} llamadas LLM + {max_tool} herramientas.\n"
            f"NO iteres sobre resultados llamando herramientas por cada uno.\n\n"
            f"Genera SOLO el código Python modificado."
        )

    async def _get_crossover_prompt(
        self,
        parent_a: ArchiveEntry,
        parent_b: ArchiveEntry,
        tools_str: str,
    ) -> str:
        """Build crossover prompt."""
        return (
            f"Combina los mejores aspectos de estas dos estrategias:\n\n"
            f"--- Estrategia A ({parent_a.strategy.name}, score={parent_a.metrics.composite_score:.3f}) ---\n"
            f"```python\n{parent_a.strategy.code}\n```\n\n"
            f"--- Estrategia B ({parent_b.strategy.name}, score={parent_b.metrics.composite_score:.3f}) ---\n"
            f"```python\n{parent_b.strategy.code}\n```\n\n"
            f"Genera una NUEVA estrategia que combine las fortalezas de ambas.\n"
            f"Genera SOLO el código Python."
        )

    async def _get_generator_prompt(
        self,
        intent_target: str,
        sector_target: Optional[str],
        tools_str: str,
        archive_context: str,
        failure_examples: str,
    ) -> str:
        """Build guided generation prompt."""
        parts = [
            f"Genera una estrategia NUEVA y CREATIVA para intención '{intent_target}'.\n"
        ]

        if archive_context:
            parts.append(f"\n## Estrategias previas (mejores)\n{archive_context}\n")

        if failure_examples:
            parts.append(f"\n## Fallos recientes\n{failure_examples}\n")

        parts.append(
            "\nInventa un enfoque DIFERENTE a los anteriores. "
            "Considera: ensemble voting, verificación cruzada, "
            "razonamiento iterativo, descomposición de consulta.\n\n"
            "Genera SOLO el código Python."
        )

        return "\n".join(parts)

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _find_weakest_metric(self, metrics: EvaluationMetrics) -> str:
        """Find the lowest-scoring metric dimension."""
        scored = {
            "answer_quality": metrics.answer_quality,
            "source_accuracy": metrics.source_accuracy,
            "instruction_following": metrics.instruction_following,
            "efficiency": metrics.efficiency,
        }
        return min(scored, key=scored.get)
