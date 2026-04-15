"""
Emma ReAct Agent — Document Forge Tool

Thin client to document-forge-service for template-based document modification.
Unlike generate_document (which LLM-rewrites the entire text), forge_document
preserves original DOCX formatting by detecting variable fields and replacing
only those values.

Conversational flow:
  Turn 1: "Renueva el contrato de Juan Garcia"
    → smart_search → finds doc ID
    → forge_document(action="analyze", ...) → detected fields
    → Emma asks user: "He detectado 8 campos. Que valores quieres cambiar?"

  Turn 2: "Cambia fecha fin a 31/12/2026 y sube el salario a 35000"
    → forge_document(action="render", session_id=..., field_values={...})
    → Returns download links

  Turn 3 (optional): "Guardalo en el sistema"
    → forge_document(action="persist", session_id=...)
"""

import logging
from typing import Any, Dict, Type

from pydantic import BaseModel, Field

from .base import EmmaTool, ToolResult

logger = logging.getLogger(__name__)


class ForgeDocumentInput(BaseModel):
    """Input for the forge_document tool."""

    action: str = Field(
        description="Accion a realizar: 'analyze' (detectar campos), "
        "'render' (generar documento con nuevos valores), "
        "'persist' (guardar permanentemente en el sistema)."
    )
    document_id: str = Field(
        default="",
        description="ID del documento fuente (para action=analyze). "
        "Obtenlo previamente con smart_search.",
    )
    user_intent: str = Field(
        default="modification",
        description="Intencion: 'renewal' (renovacion), 'modification' (cambio), "
        "'new_copy' (nueva copia).",
    )
    session_id: str = Field(
        default="",
        description="ID de sesion forge (devuelto por analyze, requerido para render/persist).",
    )
    field_values: dict = Field(
        default_factory=dict,
        description="Mapa de campo → nuevo valor para action=render. "
        "Ejemplo: {'fecha_fin': '31/12/2026', 'salario_anual': '35000 EUR'}.",
    )
    output_format: str = Field(
        default="both",
        description="Formato de salida: 'docx', 'pdf', o 'both'.",
    )
    document_title: str = Field(
        default="",
        description="Titulo para el documento generado.",
    )


class ForgeDocumentTool(EmmaTool):
    """Modify documents preserving original formatting via template-based rendering.

    Uses document-forge-service to detect variable fields, insert markers,
    and render new document versions keeping tables, styles, and images intact.
    """

    @property
    def name(self) -> str:
        return "forge_document"

    @property
    def description(self) -> str:
        return (
            "Modifica documentos existentes preservando formato (tablas, estilos, firmas). "
            "Usa para renovar contratos, cambiar fechas, actualizar datos en documentos."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return ForgeDocumentInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        from app.clients.forge_client import get_forge_client

        user_id = context.get("user_id") or ""
        if not user_id:
            return ToolResult.from_error("No user_id in context")

        action = arguments.get("action", "")
        client = get_forge_client()

        if action == "analyze":
            return await self._handle_analyze(client, arguments, user_id)
        elif action == "render":
            return await self._handle_render(client, arguments)
        elif action == "persist":
            return await self._handle_persist(client, arguments, user_id)
        else:
            return ToolResult.from_error(
                f"Accion desconocida: '{action}'",
                suggestion="Usa 'analyze', 'render', o 'persist'.",
            )

    async def _handle_analyze(
        self, client, arguments: Dict[str, Any], user_id: str
    ) -> ToolResult:
        """Analyze a document to detect variable fields."""
        document_id = arguments.get("document_id", "")
        if not document_id:
            return ToolResult.from_error(
                "Se requiere document_id para analyze.",
                suggestion="Primero usa smart_search para encontrar el documento.",
            )

        try:
            result = await client.analyze(
                user_id=user_id,
                document_id=document_id,
                user_intent=arguments.get("user_intent", "modification"),
            )
        except Exception as e:
            logger.error("Forge analyze failed: %s", e)
            return ToolResult.from_error(
                f"Error analizando el documento: {e}",
                suggestion="Verifica que el documento existe y es un DOCX valido.",
            )

        fields = result.get("fields", [])
        session_id = result.get("session_id", "")

        if not fields:
            return ToolResult.from_error(
                "No se detectaron campos modificables en el documento.",
                suggestion="El documento puede no tener campos variables claros. "
                "Usa generate_document para una reescritura completa.",
            )

        # Format fields for the LLM to present to the user
        field_lines = []
        for f in fields:
            label = f.get("label", f.get("field_name", ""))
            current = f.get("current_value", "")
            ftype = f.get("field_type", "text")
            required = " (requerido)" if f.get("required") else ""
            field_lines.append(f"  - **{label}** [{ftype}]: `{current}`{required}")

        output = (
            f"Documento analizado: **{result.get('source_title', '')}**\n"
            f"Tipo: {result.get('document_type', 'desconocido')}\n"
            f"Confianza: {result.get('confidence', 0):.0%}\n"
            f"Session ID: `{session_id}`\n\n"
            f"**Campos detectados** ({len(fields)}):\n"
            + "\n".join(field_lines)
            + "\n\nPregunta al usuario que valores quiere cambiar, "
            "luego usa forge_document(action='render', session_id='"
            + session_id
            + "', field_values={...})."
        )

        return ToolResult(
            output=output,
            data={
                "session_id": session_id,
                "fields": fields,
                "source_title": result.get("source_title", ""),
                "document_type": result.get("document_type", ""),
            },
        )

    async def _handle_render(self, client, arguments: Dict[str, Any]) -> ToolResult:
        """Render document with new field values."""
        session_id = arguments.get("session_id", "")
        field_values = arguments.get("field_values", {})

        if not session_id:
            return ToolResult.from_error(
                "Se requiere session_id para render.",
                suggestion="Primero usa forge_document(action='analyze') para obtener un session_id.",
            )
        if not field_values:
            return ToolResult.from_error(
                "Se requieren field_values para render.",
                suggestion="Proporciona un diccionario con los campos y sus nuevos valores.",
            )

        # Normalize output format
        fmt = arguments.get("output_format", "both")
        if fmt == "both":
            output_formats = ["docx", "pdf"]
        else:
            output_formats = [fmt]

        try:
            result = await client.render(
                session_id=session_id,
                field_values=field_values,
                output_formats=output_formats,
                document_title=arguments.get("document_title") or None,
            )
        except Exception as e:
            logger.error("Forge render failed: %s", e)
            return ToolResult.from_error(
                f"Error generando el documento: {e}",
                suggestion="Verifica que la sesion no ha expirado (30 min TTL).",
            )

        outputs = result.get("outputs", {})
        doc_title = result.get("document_title", "documento")

        # Format output for the user
        output_lines = [
            f"Documento generado: **{doc_title}**",
            f"Campos rellenados: {result.get('fields_filled', 0)}",
            "",
        ]
        for fmt_key, info in outputs.items():
            size_kb = info.get("size_bytes", 0) / 1024
            url = info.get("download_url", "")
            output_lines.append(f"- **{fmt_key.upper()}**: {size_kb:.1f} KB — {url}")

        output_lines.append(
            "\nEl usuario puede descargar los documentos o pedir que se guarden "
            "permanentemente con forge_document(action='persist')."
        )

        return ToolResult(
            output="\n".join(output_lines),
            data={
                "session_id": session_id,
                "outputs": outputs,
                "document_title": doc_title,
            },
        )

    async def _handle_persist(
        self, client, arguments: Dict[str, Any], user_id: str
    ) -> ToolResult:
        """Persist generated document to GCS and Weaviate."""
        session_id = arguments.get("session_id", "")
        if not session_id:
            return ToolResult.from_error(
                "Se requiere session_id para persist.",
                suggestion="Primero genera el documento con forge_document(action='render').",
            )

        try:
            result = await client.persist(
                session_id=session_id,
                user_id=user_id,
            )
        except Exception as e:
            logger.error("Forge persist failed: %s", e)
            return ToolResult.from_error(f"Error guardando el documento: {e}")

        gcs_paths = result.get("gcs_paths", {})
        indexed = result.get("weaviate_indexed", False)

        output = (
            "Documento guardado permanentemente:\n"
            + "\n".join(f"- {fmt}: `{path}`" for fmt, path in gcs_paths.items())
            + f"\nIndexado en busqueda: {'si' if indexed else 'no'}"
        )

        return ToolResult(output=output, data=result)
