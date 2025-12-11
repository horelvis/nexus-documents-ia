"""
API endpoints para el sistema de agentes.

Este módulo expone endpoints REST para:
- Orquestación de análisis de documentos
- Análisis con anotaciones PDF
- Consulta de progreso de planes

Mejoras de localización de texto:
- Usa DocumentTextService para extraer texto con marcadores de página
- Los agentes reciben texto con [PÁGINA N] para contexto
- Búsqueda fuzzy para encontrar quotes aproximados
"""
import logging
import base64
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File
import fitz  # PyMuPDF

from app.core.security import verify_api_key
from app.agents.flows.planning_flow import PlanningFlow, get_planning_flow
from app.agents.tools.planning_tool import get_planning_tool
from app.services.pdf_annotation_service import pdf_annotation_service
from app.services.document_text_service import document_text_service, DocumentContent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/orchestrate")
async def orchestrate_analysis(
    document_id: str = Form(...),
    tenant_id: str = Form(...),
    analysis_type: str = Form("legal"),
    task: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    _: bool = Depends(verify_api_key),
):
    """
    Orquesta análisis de documento usando PlanningFlow estilo OpenManus.

    El orquestador:
    1. Crea un plan con pasos específicos según el tipo de análisis
    2. Asigna agentes especializados a cada paso
    3. Ejecuta secuencialmente monitoreando progreso
    4. Devuelve resultado consolidado con riesgos y recomendaciones

    Args:
        document_id: ID del documento a analizar
        tenant_id: ID del tenant
        analysis_type: Tipo de análisis (legal, compliance, financial, general)
        task: Descripción adicional de la tarea (opcional)
        file: Archivo PDF (opcional, si no se proporciona se obtiene del storage)

    Returns:
        - success: Si el análisis se completó correctamente
        - plan_id: ID del plan de ejecución
        - progress: Progreso del plan (ej: "4/4")
        - analysis: Resultado del análisis con riesgos y recomendaciones
        - execution_log: Log detallado de ejecución
    """
    try:
        # Extraer contenido del documento con marcadores de página
        pdf_bytes = None
        document_content = None

        if file:
            pdf_bytes = await file.read()
            # Usar DocumentTextService para extracción con posiciones
            doc_content = document_text_service.extract_document_content(
                pdf_bytes,
                include_page_markers=True,  # Incluir [PÁGINA N]
                max_chars=50000,  # Límite generoso para documentos grandes
            )
            document_content = doc_content.full_text
            logger.info(
                f"Contenido extraído: {doc_content.total_pages} páginas, "
                f"{len(document_content)} caracteres con marcadores"
            )
        else:
            # Obtener de storage
            document_content = await _get_document_content(document_id, tenant_id)

        if not document_content:
            raise HTTPException(
                status_code=400,
                detail="No se pudo obtener el contenido del documento"
            )

        # Ejecutar flow con texto marcado
        flow = get_planning_flow()
        result = await flow.execute(
            task=task or f"Analizar documento {document_id}",
            tenant_id=tenant_id,
            document_id=document_id,
            document_content=document_content,
            analysis_type=analysis_type,
        )

        return {
            "success": result.success,
            "plan_id": result.plan_id,
            "progress": f"{result.steps_completed}/{result.total_steps}",
            "analysis": result.final_result,
            "execution_log": result.execution_log,
            "execution_time_ms": result.execution_time_ms,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error en orquestación: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/orchestrate-with-annotations")
async def orchestrate_with_annotations(
    document_id: str = Form(...),
    tenant_id: str = Form(...),
    analysis_type: str = Form("legal"),
    file: Optional[UploadFile] = File(None),
    _: bool = Depends(verify_api_key),
):
    """
    Orquesta análisis y genera PDF con anotaciones nativas.

    Combina PlanningFlow + PDFAnnotationService + DocumentTextService para:
    1. Extraer texto con marcadores de página [PÁGINA N]
    2. Analizar el documento con el orquestador
    3. Usar búsqueda fuzzy para localizar citas
    4. Añadir highlights con capas OCG en el PDF
    5. Devolver el PDF anotado en base64

    Args:
        document_id: ID del documento a analizar
        tenant_id: ID del tenant
        analysis_type: Tipo de análisis (legal, compliance, financial, general)
        file: Archivo PDF (requerido para anotaciones)

    Returns:
        - success: Si el análisis se completó correctamente
        - plan_id: ID del plan de ejecución
        - annotated_pdf: PDF con highlights en base64
        - annotations: Lista de anotaciones con ubicaciones
        - pages_annotated: Número de páginas con anotaciones
        - total_annotations: Total de anotaciones añadidas
        - analysis: Resultado del análisis
    """
    try:
        # Obtener PDF
        if file:
            pdf_bytes = await file.read()
        else:
            pdf_bytes = await _fetch_pdf(document_id, tenant_id)

        if not pdf_bytes:
            raise HTTPException(
                status_code=400,
                detail="Se requiere el archivo PDF para generar anotaciones"
            )

        # Extraer texto con marcadores de página usando DocumentTextService
        doc_content = document_text_service.extract_document_content(
            pdf_bytes,
            include_page_markers=True,
            max_chars=50000,
        )

        logger.info(
            f"PDF cargado: {len(pdf_bytes)} bytes, {doc_content.total_pages} páginas, "
            f"{doc_content.total_chars} caracteres"
        )

        # Ejecutar análisis con orquestador usando texto con marcadores
        flow = get_planning_flow()
        result = await flow.execute(
            task=f"Analizar documento {document_id}",
            tenant_id=tenant_id,
            document_id=document_id,
            document_content=doc_content.full_text,  # Texto con [PÁGINA N]
            analysis_type=analysis_type,
        )

        # Preparar items para anotación, enriqueciendo con búsqueda de posición
        annotation_items = []

        for risk in result.final_result.get("risks", []):
            quote = risk.get("quote", "")
            item = {
                "id": risk.get("id", f"risk_{len(annotation_items)}"),
                "type": "risk",
                "severity": risk.get("severity", "medium"),
                "title": risk.get("title", ""),
                "description": risk.get("description", ""),
                "quote": quote,
            }

            # Buscar posición exacta con fuzzy matching
            if quote:
                match = document_text_service.find_text_position(
                    doc_content, quote, use_fuzzy=True
                )
                if match:
                    item["page_hint"] = match.page_number
                    item["match_confidence"] = match.confidence
                    item["match_type"] = match.match_type
                    logger.debug(
                        f"Quote encontrado: página {match.page_number}, "
                        f"confianza {match.confidence:.2f} ({match.match_type})"
                    )

            annotation_items.append(item)

        for rec in result.final_result.get("recommendations", []):
            quote = rec.get("quote", "")
            item = {
                "id": rec.get("id", f"rec_{len(annotation_items)}"),
                "type": "recommendation",
                "title": rec.get("title", ""),
                "description": rec.get("description", ""),
                "quote": quote,
            }

            # Buscar posición exacta
            if quote:
                match = document_text_service.find_text_position(
                    doc_content, quote, use_fuzzy=True
                )
                if match:
                    item["page_hint"] = match.page_number
                    item["match_confidence"] = match.confidence
                    item["match_type"] = match.match_type

            annotation_items.append(item)

        logger.info(f"Preparando {len(annotation_items)} anotaciones para el PDF")

        # Anotar PDF con el servicio mejorado (capas OCG)
        annotation_result = pdf_annotation_service.annotate_pdf(pdf_bytes, annotation_items)

        return {
            "success": result.success,
            "plan_id": result.plan_id,
            "annotated_pdf": base64.b64encode(annotation_result.pdf_bytes).decode(),
            "annotations": annotation_result.annotations,
            "pages_annotated": annotation_result.pages_annotated,
            "total_annotations": annotation_result.total_annotations,
            "failed_annotations": annotation_result.failed_annotations,
            "analysis": result.final_result,
            "execution_time_ms": result.execution_time_ms,
            "document_info": {
                "total_pages": doc_content.total_pages,
                "total_chars": doc_content.total_chars,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error en análisis con anotaciones: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plans/{plan_id}/progress")
async def get_plan_progress(
    plan_id: str,
    _: bool = Depends(verify_api_key),
):
    """
    Obtiene el progreso de un plan de ejecución.

    Args:
        plan_id: ID del plan

    Returns:
        Información de progreso incluyendo pasos y estados
    """
    planning_tool = get_planning_tool()
    progress = planning_tool.get_progress(plan_id)

    if "error" in progress:
        raise HTTPException(status_code=404, detail=progress["error"])

    return progress


@router.get("/plans/{plan_id}/progress/text")
async def get_plan_progress_text(
    plan_id: str,
    _: bool = Depends(verify_api_key),
):
    """
    Obtiene el progreso de un plan en formato texto.

    Args:
        plan_id: ID del plan

    Returns:
        Texto formateado con el progreso
    """
    planning_tool = get_planning_tool()
    text = planning_tool.format_progress_text(plan_id)

    if text == "Plan no encontrado":
        raise HTTPException(status_code=404, detail=text)

    return {"progress_text": text}


@router.get("/analysis-types")
async def get_analysis_types(
    _: bool = Depends(verify_api_key),
):
    """
    Lista los tipos de análisis disponibles.

    Returns:
        Lista de tipos de análisis con sus descripciones
    """
    from app.agents.tools.planning_tool import PlanningTool

    return {
        "analysis_types": [
            {
                "id": "legal",
                "name": "Análisis Legal",
                "description": "Análisis de contratos y documentos legales",
                "steps": len(PlanningTool.PREDEFINED_PLANS.get("legal", [])),
            },
            {
                "id": "compliance",
                "name": "Cumplimiento Normativo",
                "description": "Verificación GDPR/RGPD y normativas de protección de datos",
                "steps": len(PlanningTool.PREDEFINED_PLANS.get("compliance", [])),
            },
            {
                "id": "financial",
                "name": "Análisis Financiero",
                "description": "Revisión de términos financieros y obligaciones de pago",
                "steps": len(PlanningTool.PREDEFINED_PLANS.get("financial", [])),
            },
            {
                "id": "general",
                "name": "Análisis General",
                "description": "Análisis general del documento",
                "steps": len(PlanningTool.PREDEFINED_PLANS.get("general", [])),
            },
        ]
    }


# =============================================================================
# Funciones auxiliares
# =============================================================================

async def _get_document_content(document_id: str, tenant_id: str) -> Optional[str]:
    """
    Obtiene el contenido de un documento del storage.

    Args:
        document_id: ID del documento
        tenant_id: ID del tenant

    Returns:
        Contenido del documento o None
    """
    try:
        # Intentar obtener del servicio de Weaviate
        from app.services.weaviate_service import weaviate_service

        # Buscar documento en Weaviate
        result = await weaviate_service.get_document_by_id(
            document_id=document_id,
            tenant_id=tenant_id,
        )

        if result and result.get("content"):
            return result["content"]

        logger.warning(f"Documento {document_id} no encontrado en Weaviate")
        return None

    except Exception as e:
        logger.error(f"Error obteniendo documento {document_id}: {e}")
        return None


async def _fetch_pdf(document_id: str, tenant_id: str) -> Optional[bytes]:
    """
    Obtiene el PDF de un documento del storage-service.

    Args:
        document_id: ID del documento
        tenant_id: ID del tenant

    Returns:
        Bytes del PDF o None
    """
    try:
        import httpx
        from app.core.config import settings

        # Primero obtener el path del documento desde Weaviate
        from app.services.weaviate_service import weaviate_service

        doc_info = await weaviate_service.get_document_by_id(
            document_id=document_id,
            tenant_id=tenant_id,
        )

        if not doc_info:
            logger.warning(f"Documento {document_id} no encontrado en Weaviate")
            return None

        # Buscar el storage_path en los metadatos del documento
        storage_path = doc_info.get("storage_path") or doc_info.get("file_path")

        if not storage_path:
            logger.warning(f"No storage_path found for document {document_id}")
            return None

        logger.info(f"Obteniendo PDF desde storage: {storage_path}")

        # Llamar al storage-service para descargar el PDF
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{settings.storage_service_url}/storage/proxy/{storage_path}",
                headers={
                    "X-API-Key": settings.MICROSERVICES_API_KEY,
                    "X-Tenant-ID": tenant_id,
                }
            )

            if response.status_code == 200:
                logger.info(f"PDF obtenido exitosamente: {len(response.content)} bytes")
                return response.content
            else:
                logger.error(f"Storage service returned {response.status_code} for {storage_path}")
                return None

    except Exception as e:
        logger.error(f"Error obteniendo PDF {document_id}: {e}")
        return None
