"""
Emma ReAct Agent --- Document Generator Tool

Generates new documents based on existing ones with field modifications.
The core use case: an expired contract becomes the "template" for a new one
with updated dates, parties, or clauses.

Flow:
1. LLM reads the source document via get_document_content
2. LLM calls generate_document with source_document_id + modifications
3. This tool retrieves the full source text, asks the LLM to rewrite it
   with the requested changes, and renders the result as a downloadable DOCX
4. The generated DOCX is stored in Redis (TTL 1h) with a unique ID
5. Returns a download URL for the user

The generated document is NOT indexed --- it's a temporary artifact for
the user to review, download, and optionally send via email.
"""

import json
import logging
import re
import uuid
from io import BytesIO
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel, Field

from .base import EmmaTool, ToolResult

logger = logging.getLogger(__name__)

# Redis key prefix for generated documents
GENERATED_DOC_PREFIX = "emma:generated_doc:"
GENERATED_DOC_TTL = 3600  # 1 hour


class GenerateDocumentInput(BaseModel):
    """Input for document generation from an existing source."""
    source_document_id: str = Field(
        description="ID del documento fuente (contrato existente, etc.). "
        "Obtenlo previamente con smart_search o get_document_content."
    )
    modifications: str = Field(
        description="Descripcion en lenguaje natural de los cambios a aplicar. "
        "Ejemplo: 'Cambiar fecha de vencimiento a 31/12/2027, "
        "actualizar salario a 35000 euros anuales'."
    )
    document_title: str = Field(
        default="",
        description="Titulo para el nuevo documento. Si no se proporciona, "
        "se genera automaticamente basado en el documento fuente."
    )


class GenerateDocumentTool(EmmaTool):
    """Generate a new document based on an existing one with modifications.

    Takes an existing document (contract, report, etc.) as template,
    applies the requested modifications via LLM rewriting, and produces
    a downloadable DOCX file.
    """

    @property
    def name(self) -> str:
        return "generate_document"

    @property
    def description(self) -> str:
        return (
            "Genera un documento NUEVO desde cero usando el LLM (redacción completa). "
            "Usa esto SOLO cuando no existe un documento base que modificar, por ejemplo: "
            "redactar un contrato nuevo, crear un informe, escribir una carta. "
            "IMPORTANTE: Si el usuario quiere MODIFICAR un documento existente "
            "(renovar contrato, cambiar fecha, actualizar datos), usa forge_document "
            "en su lugar — es más rápido y preserva el formato original (tablas, estilos, firmas)."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return GenerateDocumentInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        from app.clients.weaviate_client import get_weaviate_client
        from langchain_core.messages import SystemMessage, HumanMessage
        from app.agents.llm_models import get_chat_model

        tenant_id = context.get("tenant_id", "")
        if not tenant_id:
            return ToolResult.from_error("No tenant_id in context")

        source_document_id = arguments["source_document_id"]
        modifications = arguments["modifications"]
        document_title = arguments.get("document_title", "")

        # --- Step 1: Retrieve source document content ---
        client = get_weaviate_client()
        try:
            doc = await client.get_document_content(
                tenant_id=tenant_id,
                document_id=source_document_id,
                include_chunks=False,
            )
        except Exception as e:
            logger.error(f"generate_document: failed to retrieve source: {e}")
            return ToolResult.from_error(
                f"Error leyendo documento fuente {source_document_id}: {e}",
                suggestion="Verifica que el ID del documento es correcto usando smart_search.",
            )

        if not doc or (isinstance(doc, dict) and doc.get("error")):
            return ToolResult.from_error(
                f"Documento fuente no encontrado: {source_document_id}",
                suggestion="Usa smart_search para buscar el documento correcto.",
            )

        source_content = doc.get("content", "")
        source_title = doc.get("title", "Sin titulo")
        source_metadata = doc.get("metadata", {})

        if not source_content or len(source_content.strip()) < 50:
            return ToolResult.from_error(
                f"El documento fuente '{source_title}' no tiene suficiente contenido para usarse como plantilla.",
                suggestion="Busca un documento con mas contenido.",
            )

        # Truncate source to fit within model context (32K total).
        # Budget: ~800 tok system + ~N tok source + ~300 tok instructions + max_tokens completion.
        # We cap completion at 4096 and source at 20000 chars (~6.7K tok at 3 chars/tok).
        # Larger source budget preserves all contract data (names, IDs, amounts, clauses).
        MAX_COMPLETION_TOKENS = 4096
        max_source_chars = 20000
        if len(source_content) > max_source_chars:
            source_content = source_content[:max_source_chars]
            logger.info(f"Source document truncated to {max_source_chars} chars for context fit")

        # --- Step 2: LLM rewrites the document with modifications ---
        if not document_title:
            document_title = f"Nuevo - {source_title}"

        system_prompt = (
            "Eres un experto en generacion de documentos legales y empresariales. "
            "Tu tarea es reescribir un documento existente aplicando las modificaciones solicitadas. "
            "REGLAS IMPORTANTES:\n"
            "1. Mantiene la estructura, formato y estilo del documento original.\n"
            "2. Aplica SOLO las modificaciones solicitadas, sin alterar el resto del contenido.\n"
            "3. PRESERVA TODOS los datos existentes del documento fuente (nombres, direcciones, "
            "DNI/NIF, importes, clausulas, etc.). NUNCA reemplaces datos reales del documento "
            "original con placeholders tipo [NOMBRE] o [PENDIENTE]. Los datos que ya existen "
            "en el documento fuente deben copiarse tal cual al nuevo documento.\n"
            "4. Si el documento tiene clausulas legales, mantenlas intactas a menos que se pida cambiarlas.\n"
            "5. Usa formato Markdown con encabezados (##), listas, y negritas para estructura.\n"
            "6. Usa [PENDIENTE: descripcion] SOLO para datos completamente nuevos que no existen "
            "en el documento fuente y que el usuario no ha proporcionado.\n"
            "7. Responde UNICAMENTE con el documento reescrito, sin comentarios ni explicaciones."
        )

        user_prompt = (
            f"## Documento fuente: {source_title}\n\n"
            f"{source_content}\n\n"
            f"---\n\n"
            f"## Modificaciones a aplicar:\n{modifications}\n\n"
            f"## Titulo del nuevo documento: {document_title}\n\n"
            f"Reescribe el documento completo aplicando las modificaciones indicadas."
        )

        try:
            model = get_chat_model().bind(max_tokens=MAX_COMPLETION_TOKENS)
            response = await model.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
        except Exception as e:
            logger.error(f"generate_document: LLM rewrite failed: {e}")
            return ToolResult.from_error(
                f"Error generando el documento: {e}",
                suggestion="Intenta con modificaciones mas simples.",
            )

        generated_text = response.content or ""

        # Strip thinking tags if present
        if "<think>" in generated_text:
            generated_text = re.sub(
                r"<think>.*?</think>", "", generated_text, flags=re.DOTALL
            ).strip()

        if not generated_text or len(generated_text) < 50:
            return ToolResult.from_error(
                "El LLM no genero contenido suficiente para el documento.",
                suggestion="Reformula las modificaciones o proporciona mas contexto.",
            )

        # --- Step 3: Render as DOCX ---
        try:
            docx_bytes = _render_document_docx(document_title, generated_text, source_title)
        except Exception as e:
            logger.error(f"generate_document: DOCX rendering failed: {e}")
            return ToolResult.from_error(
                f"Error renderizando el documento DOCX: {e}",
                suggestion="El contenido se genero correctamente pero fallo la conversion a DOCX.",
            )

        # --- Step 4: Store in Redis ---
        doc_id = f"gen_{uuid.uuid4().hex[:12]}"
        try:
            import redis.asyncio as aioredis
            from app.core.config import settings

            r = aioredis.from_url(settings.redis_url)
            doc_meta = {
                "title": document_title,
                "source_document_id": source_document_id,
                "source_title": source_title,
                "tenant_id": tenant_id,
                "modifications": modifications,
                "content_text": generated_text[:5000],
                "size_bytes": len(docx_bytes),
            }
            # Store DOCX bytes and metadata separately
            await r.setex(
                f"{GENERATED_DOC_PREFIX}{doc_id}:bytes",
                GENERATED_DOC_TTL,
                docx_bytes,
            )
            await r.setex(
                f"{GENERATED_DOC_PREFIX}{doc_id}:meta",
                GENERATED_DOC_TTL,
                json.dumps(doc_meta),
            )
            await r.aclose()
        except Exception as e:
            logger.error(f"generate_document: Redis storage failed: {e}")
            return ToolResult.from_error(
                f"Documento generado pero fallo el almacenamiento temporal: {e}",
            )

        # --- Step 5: Return result with download info ---
        download_url = f"/emma/generated/{doc_id}/download"
        size_kb = len(docx_bytes) / 1024

        output = (
            f"Documento generado exitosamente:\n\n"
            f"**Titulo**: {document_title}\n"
            f"**Basado en**: {source_title}\n"
            f"**Formato**: DOCX ({size_kb:.1f} KB)\n"
            f"**ID de descarga**: {doc_id}\n"
            f"**URL de descarga**: {download_url}\n"
            f"**Disponible durante**: 1 hora\n\n"
            f"**Modificaciones aplicadas**:\n{modifications}\n\n"
            f"El usuario puede descargar el documento o solicitar su envio por email."
        )

        return ToolResult(
            output=output,
            sources=[{
                "title": document_title,
                "document_id": doc_id,
                "source_document_id": source_document_id,
                "type": "generated_document",
            }],
            data={
                "generated_doc_id": doc_id,
                "download_url": download_url,
                "title": document_title,
                "source_document_id": source_document_id,
                "size_bytes": len(docx_bytes),
            },
        )


def _render_document_docx(title: str, content: str, source_title: str) -> bytes:
    """Render markdown-like content as a DOCX file.

    Handles basic markdown: ## headings, **bold**, - lists, paragraphs.
    """
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    # Page margins
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    # Title
    heading = doc.add_heading(title, level=1)
    for run in heading.runs:
        run.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)

    # Source reference
    ref = doc.add_paragraph()
    ref.paragraph_format.space_after = Pt(12)
    r = ref.add_run(f"Basado en: {source_title}")
    r.font.size = Pt(9)
    r.italic = True
    r.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    # Parse and render content
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # Headings
        if stripped.startswith("### "):
            h = doc.add_heading(stripped[4:], level=3)
            for run in h.runs:
                run.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)
        elif stripped.startswith("## "):
            h = doc.add_heading(stripped[3:], level=2)
            for run in h.runs:
                run.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)
        elif stripped.startswith("# "):
            h = doc.add_heading(stripped[2:], level=2)
            for run in h.runs:
                run.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)
        # List items
        elif stripped.startswith("- ") or stripped.startswith("* "):
            _add_formatted_paragraph(doc, stripped[2:], list_item=True)
        elif re.match(r"^\d+\.\s", stripped):
            text = re.sub(r"^\d+\.\s", "", stripped)
            _add_formatted_paragraph(doc, text, list_item=True)
        # Horizontal rule
        elif stripped in ("---", "***", "___"):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(6)
            r = p.add_run("_" * 60)
            r.font.size = Pt(8)
            r.font.color.rgb = RGBColor(0xBD, 0xBD, 0xBD)
        # Normal paragraph
        else:
            _add_formatted_paragraph(doc, stripped)

    # Footer
    doc.add_paragraph()
    footer = doc.add_paragraph()
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = footer.add_run("Documento generado por NouxCubeIA")
    r.font.size = Pt(8)
    r.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _add_formatted_paragraph(
    doc: Any,
    text: str,
    list_item: bool = False,
) -> None:
    """Add a paragraph with basic markdown formatting (**bold**)."""
    from docx.shared import Pt

    style = "List Bullet" if list_item else None
    p = doc.add_paragraph(style=style)
    p.paragraph_format.space_after = Pt(4)

    # Split by **bold** markers
    parts = re.split(r"(\*\*.*?\*\*)", text)
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            r = p.add_run(part[2:-2])
            r.bold = True
            r.font.size = Pt(11)
        else:
            r = p.add_run(part)
            r.font.size = Pt(11)
