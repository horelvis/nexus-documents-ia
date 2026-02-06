"""
Emma ReAct Agent — CENDOJ Jurisprudence Reference Tool

Searches the Spanish CENDOJ judicial database for relevant court decisions
and returns references (ROJ, ECLI, court, date, summary) without storing
any content. Results are used as contextual references during document review.

With with_content=True, the agent also downloads PDFs for the top N most
relevant results, extracts text in memory, and includes legal_grounds +
ruling sections as ephemeral LLM context. Nothing is stored in any database.

Architecture:
    ReAct agent calls this tool → spins up an ephemeral Docker container
    with Playwright → container navigates CENDOJ like a human user →
    extracts references from search results → [optional: downloads top N
    PDFs, extracts text in memory via PyPDF2] → container is destroyed →
    references (+ ephemeral content) returned to the agent for citation.

The container approach ensures:
- No persistent storage of judicial data
- Real browser navigation (no API reverse-engineering)
- Sandboxed execution (container is removed after each search)
- The client's on-premise server makes the queries (personal use)
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Type

from pydantic import BaseModel, Field

from .base import EmmaTool, ToolResult

logger = logging.getLogger(__name__)

DOCKER_IMAGE = "nouxcube-cendoj-agent"
CONTAINER_TIMEOUT = 120  # seconds (base)
CONTAINER_TIMEOUT_WITH_CONTENT = 180  # seconds (search + PDF downloads)
VALID_COURTS = {"TS", "AN", "TSJ", "AP"}
MAX_QUERY_LENGTH = 500
DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")


class CendojSearchInput(BaseModel):
    """Input parameters for CENDOJ jurisprudence search."""
    query: str = Field(
        description=(
            "Consulta de búsqueda de jurisprudencia. Usa términos legales "
            "específicos. Ejemplos: 'despido improcedente periodo de prueba', "
            "'responsabilidad patrimonial administración', 'nulidad cláusula suelo'."
        ),
    )
    court: str = Field(
        default="TS",
        description=(
            "Tribunal: 'TS' (Tribunal Supremo) o 'AN' (Audiencia Nacional). "
            "Usa TS para jurisprudencia general y AN para casos especializados."
        ),
    )
    max_results: int = Field(
        default=10,
        description="Número máximo de referencias a devolver (1-20).",
        ge=1, le=20,
    )
    date_from: str = Field(
        default="",
        description="Fecha inicio DD/MM/YYYY (opcional). Ejemplo: '01/01/2020'.",
    )
    date_to: str = Field(
        default="",
        description="Fecha fin DD/MM/YYYY (opcional). Ejemplo: '31/12/2024'.",
    )
    with_content: int = Field(
        default=0,
        description=(
            "Descargar PDFs de las N sentencias más relevantes y extraer texto "
            "como contexto efímero. El texto se usa solo como contexto del LLM, "
            "nunca se almacena. 0 = solo referencias, 1-5 = con contenido."
        ),
        ge=0, le=5,
    )


class CendojSearchTool(EmmaTool):
    """Search CENDOJ for jurisprudence references (no content storage)."""

    @property
    def name(self) -> str:
        return "search_jurisprudence"

    @property
    def description(self) -> str:
        return (
            "Busca jurisprudencia en CENDOJ (Centro de Documentación Judicial). "
            "Devuelve referencias a sentencias relevantes del Tribunal Supremo o "
            "Audiencia Nacional: ROJ, ECLI, fecha, tribunal, resumen breve y "
            "enlace directo a CENDOJ. No almacena contenido — solo referencias. "
            "Usa esto cuando necesites fundamentar un análisis con jurisprudencia "
            "española o verificar si existe doctrina sobre un tema legal. "
            "Con with_content>0, también descarga y extrae texto de las sentencias "
            "más relevantes como contexto efímero (fundamentos de derecho y fallo)."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return CendojSearchInput

    async def execute(
        self, arguments: Dict[str, Any], context: Dict[str, Any]
    ) -> ToolResult:
        query = arguments["query"]
        court = arguments.get("court", "TS")
        max_results = min(arguments.get("max_results", 10), 20)
        date_from = arguments.get("date_from", "")
        date_to = arguments.get("date_to", "")
        with_content = min(arguments.get("with_content", 0), 5)

        # Input validation
        if not query or not query.strip():
            return ToolResult.from_error("La consulta no puede estar vacía.")
        if len(query) > MAX_QUERY_LENGTH:
            return ToolResult.from_error(
                f"Consulta demasiado larga ({len(query)} chars, máx {MAX_QUERY_LENGTH}).",
                suggestion="Usa términos legales más concisos.",
            )
        if court not in VALID_COURTS:
            return ToolResult.from_error(
                f"Tribunal inválido: '{court}'.",
                suggestion=f"Tribunales válidos: {', '.join(sorted(VALID_COURTS))}",
            )
        if date_from and not DATE_PATTERN.match(date_from):
            return ToolResult.from_error(
                f"Formato de fecha inicio inválido: '{date_from}'.",
                suggestion="Usa formato DD/MM/YYYY, ejemplo: '01/01/2020'.",
            )
        if date_to and not DATE_PATTERN.match(date_to):
            return ToolResult.from_error(
                f"Formato de fecha fin inválido: '{date_to}'.",
                suggestion="Usa formato DD/MM/YYYY, ejemplo: '31/12/2024'.",
            )

        # Build docker run command
        timeout = CONTAINER_TIMEOUT_WITH_CONTENT if with_content else CONTAINER_TIMEOUT
        cmd = [
            "docker", "run", "--rm",
            "--network=bridge",
            "--memory=512m",
            "--cpus=1",
            DOCKER_IMAGE,
            "--query", query,
            "--court", court,
            "--max-results", str(max_results),
        ]
        if date_from:
            cmd.extend(["--date-from", date_from])
        if date_to:
            cmd.extend(["--date-to", date_to])
        if with_content > 0:
            cmd.extend(["--with-content", str(with_content)])

        logger.info(
            f"search_jurisprudence: query='{query}' court={court} "
            f"max={max_results} content={with_content} "
            f"dates={date_from or '∞'}→{date_to or '∞'}"
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            # Log container stderr (agent logs)
            if stderr:
                for line in stderr.decode().strip().split("\n"):
                    logger.debug(f"[cendoj-agent] {line}")

            if proc.returncode != 0:
                error_msg = stderr.decode().strip().split("\n")[-1] if stderr else "unknown"
                logger.error(f"CENDOJ agent failed (exit {proc.returncode}): {error_msg}")
                return ToolResult.from_error(
                    f"La búsqueda en CENDOJ falló: {error_msg}",
                    suggestion="Intenta reformular la consulta o cambiar el tribunal.",
                )

            # Parse JSON output
            references = json.loads(stdout.decode())

        except asyncio.TimeoutError:
            logger.error(f"CENDOJ agent timed out after {timeout}s")
            return ToolResult.from_error(
                "La búsqueda en CENDOJ tardó demasiado.",
                suggestion="Intenta una consulta más específica.",
            )
        except json.JSONDecodeError as e:
            logger.error(f"CENDOJ agent returned invalid JSON: {e}")
            return ToolResult.from_error("Error al procesar resultados de CENDOJ.")
        except FileNotFoundError:
            return ToolResult.from_error(
                "Docker no está disponible o la imagen nouxcube-cendoj-agent no existe.",
                suggestion="Verifica que Docker esté instalado y la imagen construida.",
            )
        except Exception as e:
            logger.error(f"CENDOJ search error: {e}", exc_info=True)
            return ToolResult.from_error(f"Error en búsqueda CENDOJ: {e}")

        if not references:
            return ToolResult(
                output=(
                    f"No se encontró jurisprudencia en CENDOJ para: '{query}' "
                    f"(tribunal: {court})"
                ),
                sources=[],
            )

        # Format output for the LLM
        lines = [
            f"Jurisprudencia encontrada en CENDOJ ({len(references)} referencias):\n"
        ]
        sources = []

        for i, ref in enumerate(references, 1):
            roj = ref.get("roj", "N/A")
            ecli = ref.get("ecli", "")
            date = ref.get("date", "")
            court_name = ref.get("court", "")
            chamber = ref.get("chamber", "")
            summary = ref.get("summary", "")
            url = ref.get("cendoj_url", "")
            res_type = ref.get("resolution_type", "Sentencia")
            ponente = ref.get("ponente", "")
            content = ref.get("content")

            lines.append(f"**{i}. {roj}** ({res_type})")
            if ecli:
                lines.append(f"   ECLI: {ecli}")
            if date:
                lines.append(f"   Fecha: {date}")
            if court_name:
                tribunal = f"{court_name} — {chamber}" if chamber else court_name
                lines.append(f"   Tribunal: {tribunal}")
            if ponente:
                lines.append(f"   Ponente: {ponente}")
            if summary:
                lines.append(f"   {summary[:200]}")
            if url:
                lines.append(f"   Consultar: {url}")

            # Include extracted content if available (ephemeral LLM context)
            if content:
                legal_grounds = content.get("legal_grounds", "")
                ruling = content.get("ruling", "")
                if legal_grounds:
                    lines.append(f"   --- Fundamentos de Derecho ---")
                    lines.append(f"   {legal_grounds[:3000]}")
                if ruling:
                    lines.append(f"   --- Fallo ---")
                    lines.append(f"   {ruling[:1000]}")

            lines.append("")

            sources.append({
                "title": f"{roj} — {court_name}" if court_name else roj,
                "url": url,
                "type": "jurisprudencia",
                "roj": roj,
                "ecli": ecli,
                "date": date,
            })

        return ToolResult(
            output="\n".join(lines),
            sources=sources,
            data={
                "result_count": len(references),
                "court": court,
                "content_count": sum(1 for r in references if r.get("content")),
            },
        )
