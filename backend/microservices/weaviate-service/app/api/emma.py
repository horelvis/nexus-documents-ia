"""Emma API endpoints for advanced agentic RAG"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List, Optional, AsyncGenerator
import logging
import base64
import uuid
import json
import asyncio

from app.core.security import verify_api_key
from app.services.emma_service import emma_service
from app.services.pdf_annotation_service import pdf_annotation_service
from app.services.document_text_service import document_text_service
from app.services.pdf_markdown_service import get_pdf_markdown_service
from app.schemas.emma import (
    EmmaQuery, EmmaResponse, ToolExecution, DecisionTreeState,
    FeedbackRequest, VisualizationRequest,
    AnalyzeWithAnnotationsRequest, AnnotatedPDFResponse,
    AnalysisRisk, AnalysisRecommendation, DocumentAnalysisResult,
    PDFAnnotation, AnnotationRect,
    MarkdownPage, DocumentMarkdownResponse, AnalysisWithMarkdownResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/query", response_model=EmmaResponse)
async def emma_query(
    query: EmmaQuery,
    _: bool = Depends(verify_api_key)
):
    """Execute Emma agentic query with decision trees"""
    try:
        # Enhanced logging for debug mode
        if query.enable_debug:
            logger.info(f"🧠 DEBUG MODE ENABLED for query: {query.query[:100]}...")
            logger.info(f"📊 Debug parameters: tenant_id={query.tenant_id}, session_id={query.session_id}")

        response = await emma_service.execute_query(query)

        if query.enable_debug and response.data:
            logger.info(f"🔍 Chain of thought data generated: {len(response.data.get('decision_trace', []))} decision steps")

        return response
    except Exception as e:
        logger.error(f"❌ Emma query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/stream")
async def emma_query_stream(
    query: EmmaQuery,
    _: bool = Depends(verify_api_key)
):
    """
    Execute Emma query with Server-Sent Events (SSE) streaming.

    Returns real-time progress updates as agents execute.

    SSE Event format:
    - event: start | planning | plan_created | step_start | step_complete | step_error | consolidating | complete
    - data: JSON with progress info

    Example events:
    ```
    event: step_start
    data: {"step": 1, "total_steps": 4, "agent": "ContractAgent", "progress": 25}

    event: step_complete
    data: {"step": 1, "findings_count": 3, "progress": 30}

    event: complete
    data: {"success": true, "final_result": {...}, "progress": 100}
    ```
    """
    async def generate_sse() -> AsyncGenerator[str, None]:
        try:
            async for event in emma_service.execute_query_stream(query):
                event_type = event.get("event", "message")
                event_data = event.get("data", {})

                # Format as SSE
                yield f"event: {event_type}\n"
                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"❌ Stream error: {e}")
            yield f"event: error\n"
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )

@router.post("/tools/execute", response_model=Dict[str, Any])
async def execute_tool(
    tool_execution: ToolExecution,
    _: bool = Depends(verify_api_key)
):
    """Execute a specific tool through Emma decision tree"""
    try:
        result = await emma_service.execute_tool(tool_execution)
        return result
    except Exception as e:
        logger.error(f"❌ Tool execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tools")
async def list_available_tools(_: bool = Depends(verify_api_key)):
    """List all available Emma tools"""
    try:
        tools = await emma_service.list_tools()
        return {"tools": tools}
    except Exception as e:
        logger.error(f"❌ Failed to list tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/decision-tree/{session_id}/state", response_model=DecisionTreeState)
async def get_decision_tree_state(
    session_id: str,
    _: bool = Depends(verify_api_key)
):
    """Get current decision tree state for a session"""
    try:
        state = await emma_service.get_decision_tree_state(session_id)
        return state
    except Exception as e:
        logger.error(f"❌ Failed to get decision tree state: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/visualize")
async def create_visualization(
    viz_request: VisualizationRequest,
    _: bool = Depends(verify_api_key)
):
    """Create dynamic visualization based on data type"""
    try:
        visualization = await emma_service.create_visualization(viz_request)
        return visualization
    except Exception as e:
        logger.error(f"❌ Visualization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/feedback")
async def submit_feedback(
    feedback: FeedbackRequest,
    _: bool = Depends(verify_api_key)
):
    """Submit feedback for learning and improvement"""
    try:
        result = await emma_service.process_feedback(feedback)
        return {"status": "success", "feedback_id": result}
    except Exception as e:
        logger.error(f"❌ Feedback processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/session/{session_id}")
async def get_session_analytics(
    session_id: str,
    _: bool = Depends(verify_api_key)
):
    """Get analytics for a specific Emma session"""
    try:
        analytics = await emma_service.get_session_analytics(session_id)
        return analytics
    except Exception as e:
        logger.error(f"❌ Failed to get session analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def emma_health_check():
    """Emma service health check"""
    try:
        status = await emma_service.health_check()
        return status
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@router.get("/concurrency/stats")
async def get_concurrency_stats(_: bool = Depends(verify_api_key)):
    """
    Get concurrency statistics for monitoring.

    Returns current LLM slot usage, queue depth, and per-tenant stats.
    Useful for monitoring system load and debugging capacity issues.
    """
    from app.core.concurrency import get_concurrency_manager

    try:
        manager = get_concurrency_manager()
        stats = await manager.get_stats()
        return {
            "status": "ok",
            "concurrency": stats
        }
    except Exception as e:
        logger.error(f"❌ Failed to get concurrency stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prompts/reload")
async def reload_prompts(_: bool = Depends(verify_api_key)):
    """
    Reload Emma prompts from YAML configuration file.

    Use this after editing config/prompts/emma_prompts.yaml
    to apply changes without restarting the service.
    """
    try:
        from app.services.rag.prompt_loader import reload_prompts, list_available_prompts
        success = reload_prompts()
        if success:
            available = list_available_prompts()
            return {
                "status": "success",
                "message": "Prompts reloaded successfully",
                "available_prompts": available
            }
        else:
            return {
                "status": "warning",
                "message": "Prompt file not found, using defaults"
            }
    except Exception as e:
        logger.error(f"❌ Failed to reload prompts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/prompts")
async def get_available_prompts(_: bool = Depends(verify_api_key)):
    """List available prompts in the configuration file"""
    try:
        from app.services.rag.prompt_loader import list_available_prompts, load_prompts
        available = list_available_prompts()
        prompts = load_prompts()
        return {
            "available_prompts": available,
            "prompt_count": len(available),
            "prompts_preview": {k: v[:200] + "..." if len(v) > 200 else v for k, v in prompts.items()}
        }
    except Exception as e:
        logger.error(f"❌ Failed to list prompts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/migrate-from-qdrant")
async def migrate_from_qdrant(
    source_collection: str,
    target_collection: str,
    tenant_id: str,
    batch_size: int = 100,
    _: bool = Depends(verify_api_key)
):
    """Migrate data from Qdrant to Weaviate (TRANSITION HELPER)"""
    try:
        result = await emma_service.migrate_from_qdrant(
            source_collection, target_collection, tenant_id, batch_size
        )
        return {
            "status": "success",
            "migrated_documents": result.get("migrated", 0),
            "migration_id": result.get("migration_id"),
            "collection": target_collection
        }
    except Exception as e:
        logger.error(f"❌ Migration from Qdrant failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-with-annotations", response_model=AnnotatedPDFResponse)
async def analyze_document_with_annotations(
    document_id: str = Form(...),
    tenant_id: str = Form(...),
    analysis_type: str = Form("legal"),
    file: Optional[UploadFile] = File(None),
    _: bool = Depends(verify_api_key)
):
    """
    Analyze a document and return the PDF with native annotations (highlights).

    This endpoint uses the DocumentAnalysisFlow (SwarmWorkflow native) with specialized agents:
    1. Receives PDF (either uploaded or fetched from storage by document_id)
    2. Extracts text with page markers [PÁGINA N] using DocumentTextService
    3. Runs SwarmWorkflow analysis with specialized agents (ContractAgent, ComplianceAgent, etc.)
    4. Uses fuzzy matching to locate quotes in the PDF
    5. Adds native PDF annotations with OCG layers at the exact locations
    6. Returns base64-encoded annotated PDF plus annotation metadata

    The annotations are native PDF highlights with toggleable layers that work in any PDF viewer.
    Each highlight has a popup with title, severity, and description.

    Args:
        document_id: Document ID in the system
        tenant_id: Tenant ID for isolation
        analysis_type: Type of analysis ("legal", "compliance", "financial", "general")
        file: Optional PDF file upload (if not provided, fetched from storage)

    Returns:
        AnnotatedPDFResponse with:
        - annotated_pdf: Base64-encoded PDF with highlights
        - annotations: List of annotation metadata with page numbers and rects
        - analysis: Full analysis result (summary, risks, recommendations)
    """
    from app.agents.flows.document_analysis_flow import get_document_analysis_flow

    try:
        logger.info(f"📄 Analyzing document {document_id} for tenant {tenant_id} (type: {analysis_type})")

        # 1. Get PDF bytes
        if file:
            pdf_bytes = await file.read()
            logger.info(f"📥 Received uploaded PDF: {len(pdf_bytes)} bytes")
        else:
            # Fetch from storage service
            pdf_bytes = await _fetch_document_from_storage(document_id, tenant_id)
            if not pdf_bytes:
                raise HTTPException(
                    status_code=404,
                    detail=f"Document {document_id} not found"
                )
            logger.info(f"📥 Fetched PDF from storage: {len(pdf_bytes)} bytes")

        # 2. Extract text with page markers using DocumentTextService
        doc_content = document_text_service.extract_document_content(
            pdf_bytes,
            include_page_markers=True,
            max_chars=50000,  # Generous limit for large documents
        )

        if not doc_content.full_text:
            raise HTTPException(
                status_code=400,
                detail="Could not extract text from PDF"
            )

        logger.info(
            f"📝 Text extracted: {doc_content.total_pages} pages, "
            f"{doc_content.total_chars} chars with page markers"
        )

        # 3. Run analysis with DocumentAnalysisFlow (SwarmWorkflow native)
        flow = get_document_analysis_flow()
        result = await flow.execute(
            task=f"Analizar documento {document_id}",
            tenant_id=tenant_id,
            document_id=document_id,
            document_content=doc_content.full_text,  # Text with [PÁGINA N] markers
            analysis_type=analysis_type,
        )

        logger.info(
            f"🤖 DocumentAnalysisFlow completed: success={result.success}, "
            f"agents_used={result.agents_used}, execution_time={result.execution_time_ms}ms"
        )

        # 4. Convert analysis result to annotation items with fuzzy matching
        annotation_items = []

        for risk in result.risks:
            quote = risk.get("quote", "")
            item = {
                "id": risk.get("id", f"risk_{len(annotation_items)}"),
                "type": "risk",
                "severity": risk.get("severity", "medium"),
                "title": risk.get("title", ""),
                "description": risk.get("description", ""),
                "quote": quote,
                "clause": risk.get("clause"),
            }

            # Use cross-block search for better localization
            if quote:
                match = document_text_service.find_text_position_cross_block(
                    doc_content, quote, max_block_span=3,
                    page_hint=risk.get("page_hint")
                )
                if match:
                    item["page_hint"] = match.page_number
                    item["match_confidence"] = match.confidence
                    item["match_type"] = match.match_type
                    # Add bbox for position_data
                    if match.bbox and match.bbox[2] > match.bbox[0]:
                        item["bbox_start_x0"] = match.bbox[0]
                        item["bbox_start_y0"] = match.bbox[1]
                        item["bbox_start_x1"] = match.bbox[2]
                        item["bbox_start_y1"] = match.bbox[3]
                        item["page_start"] = match.page_number
                        item["page_end"] = match.page_number
                    logger.debug(
                        f"Quote located: page {match.page_number}, "
                        f"confidence {match.confidence:.2f} ({match.match_type})"
                    )

            annotation_items.append(item)

        for rec in result.recommendations:
            quote = rec.get("quote", "")
            item = {
                "id": rec.get("id", f"rec_{len(annotation_items)}"),
                "type": "recommendation",
                "severity": rec.get("priority", "medium"),  # Use priority as severity
                "title": rec.get("title", ""),
                "description": rec.get("description", ""),
                "quote": quote,
            }

            # Use cross-block search for better localization
            if quote:
                match = document_text_service.find_text_position_cross_block(
                    doc_content, quote, max_block_span=3,
                    page_hint=rec.get("page_hint")
                )
                if match:
                    item["page_hint"] = match.page_number
                    item["match_confidence"] = match.confidence
                    item["match_type"] = match.match_type
                    # Add bbox for position_data
                    if match.bbox and match.bbox[2] > match.bbox[0]:
                        item["bbox_start_x0"] = match.bbox[0]
                        item["bbox_start_y0"] = match.bbox[1]
                        item["bbox_start_x1"] = match.bbox[2]
                        item["bbox_start_y1"] = match.bbox[3]
                        item["page_start"] = match.page_number
                        item["page_end"] = match.page_number

            annotation_items.append(item)

        logger.info(f"📝 Prepared {len(annotation_items)} items for annotation")

        # 5. Deduplicate annotation items by quote to avoid overlapping annotations
        seen_quotes = set()
        unique_items = []
        for item in annotation_items:
            quote = item.get("quote", "").strip()[:100]  # Normalize: first 100 chars
            if quote and quote not in seen_quotes:
                seen_quotes.add(quote)
                unique_items.append(item)
            elif not quote:
                unique_items.append(item)  # Keep items without quotes

        if len(unique_items) < len(annotation_items):
            logger.info(
                f"🔄 Deduplicated: {len(annotation_items)} → {len(unique_items)} items "
                f"({len(annotation_items) - len(unique_items)} duplicates removed)"
            )
        annotation_items = unique_items

        # 6. Add annotations to PDF with OCG layers
        annotation_result = pdf_annotation_service.annotate_pdf(pdf_bytes, annotation_items)

        # 6. Build response with converted types
        risks = []
        for r in result.risks:
            risks.append(AnalysisRisk(
                id=r.get("id", f"risk_{uuid.uuid4().hex[:8]}"),
                type="risk",
                severity=r.get("severity", "medium"),
                title=r.get("title", "Riesgo identificado"),
                description=r.get("description", ""),
                quote=r.get("quote"),
                clause=r.get("clause"),
                recommendation=r.get("recommendation"),
            ))

        recommendations = []
        for r in result.recommendations:
            recommendations.append(AnalysisRecommendation(
                id=r.get("id", f"rec_{uuid.uuid4().hex[:8]}"),
                type="recommendation",
                title=r.get("title", "Recomendación"),
                description=r.get("description", ""),
                quote=r.get("quote"),
                priority=r.get("priority", "medium"),
                action_required=r.get("action_required"),
            ))

        analysis = DocumentAnalysisResult(
            document_id=document_id,
            summary=result.summary or "Análisis completado",
            risks=risks,
            recommendations=recommendations,
            confidence_score=result.confidence_score or 0.8,
            analysis_type=analysis_type,
        )

        # Build annotation response
        annotations = []
        for ann in annotation_result.annotations:
            rect_data = ann.get("rect", {})
            annotations.append(PDFAnnotation(
                id=ann.get("id", ""),
                type=ann.get("type", "risk"),
                severity=ann.get("severity"),
                title=ann.get("title", ""),
                description=ann.get("description", ""),
                page_number=ann.get("page_number", 1),
                rect=AnnotationRect(
                    x0=rect_data.get("x0", 0),
                    y0=rect_data.get("y0", 0),
                    x1=rect_data.get("x1", 0),
                    y1=rect_data.get("y1", 0),
                ),
                text_found=ann.get("text_found", ""),
                confidence=ann.get("confidence", 0.0),
            ))

        response = AnnotatedPDFResponse(
            annotated_pdf=base64.b64encode(annotation_result.pdf_bytes).decode("utf-8"),
            annotations=annotations,
            pages_annotated=annotation_result.pages_annotated,
            total_annotations=annotation_result.total_annotations,
            failed_annotations=annotation_result.failed_annotations,
            analysis=analysis,
        )

        logger.info(
            f"✅ Document analyzed: {annotation_result.total_annotations} annotations, "
            f"{annotation_result.pages_annotated} pages, {annotation_result.failed_annotations} failed, "
            f"agents={result.agents_used}, execution_time={result.execution_time_ms:.0f}ms"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Analysis with annotations failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis/{job_id}")
async def get_analysis_by_id(
    job_id: str,
    _: bool = Depends(verify_api_key)
):
    """
    Get a completed analysis by job ID.

    Returns the full analysis data including summary, risks, recommendations,
    findings, and annotations. Use this to display previously completed analyses.

    Returns 404 if job not found, or the analysis data if found.
    """
    from app.services.analysis_persistence_service import get_persistence_service

    try:
        persistence = get_persistence_service()
        result = await persistence.get_analysis(job_id)

        if not result:
            raise HTTPException(status_code=404, detail=f"Analysis job {job_id} not found")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Failed to get analysis {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-with-annotations/stream")
async def analyze_document_with_annotations_stream(
    document_id: str = Form(...),
    tenant_id: str = Form(...),
    analysis_type: str = Form("legal"),
    job_id: Optional[str] = Form(None),  # Optional: existing job ID to update
    file: Optional[UploadFile] = File(None),
    _: bool = Depends(verify_api_key)
):
    """
    Analyze a document with real-time streaming progress.

    Returns Server-Sent Events (SSE) with progress updates as each agent executes.
    The final event contains the annotated PDF.

    If job_id is provided, updates the existing job in the database.
    Otherwise, creates a new job for persistence.

    SSE Events:
    - start: Analysis started
    - extracting: Extracting text from PDF
    - planning: Creating analysis plan
    - plan_created: Plan ready with steps
    - step_start: Agent starting execution
    - step_complete: Agent finished with findings
    - annotating: Adding highlights to PDF
    - complete: Final result with annotated PDF
    - error: Error occurred
    """
    from app.agents.flows.document_analysis_flow import get_document_analysis_flow
    from app.services.analysis_persistence_service import get_persistence_service

    persistence = get_persistence_service()

    async def generate_sse() -> AsyncGenerator[str, None]:
        pdf_bytes = None
        doc_content = None
        current_job_id = job_id
        start_time = asyncio.get_event_loop().time()

        # Helper to yield and flush immediately
        async def flush():
            await asyncio.sleep(0)

        try:
            # Create or get job ID for persistence
            if not current_job_id:
                current_job_id = await persistence.create_job(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    analysis_type=analysis_type
                )

            # Mark job as started
            if current_job_id:
                await persistence.mark_started(current_job_id)

            # 1. Get PDF bytes
            yield f"event: start\ndata: {json.dumps({'message': 'Voy a revisar este documento, dame un momento...', 'progress': 0, 'job_id': current_job_id})}\n\n"
            await flush()

            if file:
                pdf_bytes = await file.read()
                logger.info(f"📥 Received uploaded PDF: {len(pdf_bytes)} bytes")
            else:
                pdf_bytes = await _fetch_document_from_storage(document_id, tenant_id)
                if not pdf_bytes:
                    if current_job_id:
                        await persistence.mark_failed(current_job_id, "Document not found")
                    yield f"event: error\ndata: {json.dumps({'error': 'Document not found'})}\n\n"
                    return

            # 2. Extract text
            yield f"event: extracting\ndata: {json.dumps({'message': 'Extrayendo texto del documento...', 'progress': 5})}\n\n"
            await flush()

            doc_content = document_text_service.extract_document_content(
                pdf_bytes,
                include_page_markers=True,
                max_chars=50000,
            )

            if not doc_content.full_text:
                if current_job_id:
                    await persistence.mark_failed(current_job_id, "Could not extract text from PDF")
                yield f"event: error\ndata: {json.dumps({'error': 'Could not extract text from PDF'})}\n\n"
                return

            yield f"event: extracted\ndata: {json.dumps({'message': f'Texto extraído: {doc_content.total_pages} páginas', 'pages': doc_content.total_pages, 'chars': doc_content.total_chars, 'progress': 10})}\n\n"
            await flush()

            # Update progress in database
            if current_job_id:
                await persistence.update_progress(current_job_id, 10, "Texto extraído")

            # 3. Stream document analysis with native Agent Framework
            flow = get_document_analysis_flow()
            all_findings = []
            final_result = {}

            async for event in flow.execute_stream(
                task=f"Analizar documento {document_id}",
                tenant_id=tenant_id,
                document_id=document_id,
                document_content=doc_content.full_text,
                analysis_type=analysis_type,
            ):
                event_type = event.get("event", "message")
                event_data = event.get("data", {})

                # Skip duplicate events - we handle these ourselves
                # 'start' - we already sent one above
                # 'complete' - we'll send our own with annotated PDF data
                if event_type in ("start", "complete"):
                    # For 'complete', capture the final_result before skipping
                    if event_type == "complete":
                        final_result = event_data.get("final_result", {})
                    continue

                # Adjust progress range (10-85% for analysis)
                if "progress" in event_data:
                    original_progress = event_data["progress"]
                    event_data["progress"] = 10 + int(original_progress * 0.75)

                # Collect findings from step completions
                if event_type == "step_complete":
                    findings = event_data.get("findings", [])
                    if findings:
                        all_findings.extend(findings)

                # Update progress in database for key events
                if current_job_id and event_type in ("plan_created", "step_start", "step_complete"):
                    progress = event_data.get("progress", 0)
                    step = event_data.get("step", 0)
                    total = event_data.get("total_steps", 0)
                    current_step = event_data.get("description") or event_data.get("agent", "")
                    await persistence.update_progress(
                        current_job_id,
                        progress=progress,
                        current_step=current_step[:200] if current_step else None,
                        total_steps=total if total > 0 else None,
                        steps_completed=step if step > 0 else None
                    )

                yield f"event: {event_type}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                await flush()  # Force immediate send to client

            # 4. Annotate PDF
            yield f"event: annotating\ndata: {json.dumps({'message': 'Añadiendo anotaciones al PDF...', 'progress': 88})}\n\n"
            await flush()

            # Prepare annotation items - PARALLELIZED for performance
            async def locate_item(item_data: dict, item_type: str, idx: int) -> dict:
                """Locate a single item's quote in the document (runs in thread pool)."""
                quote = item_data.get("quote", "")
                item = {
                    "id": item_data.get("id", f"{item_type}_{idx}"),
                    "type": "risk" if item_type == "risk" else "recommendation",
                    "severity": item_data.get("severity" if item_type == "risk" else "priority", "medium"),
                    "title": item_data.get("title", ""),
                    "description": item_data.get("description", ""),
                    "quote": quote,
                }
                if quote:
                    # Run sync function in thread pool for parallelization
                    match = await asyncio.to_thread(
                        document_text_service.find_text_position_cross_block,
                        doc_content, quote, 3, item_data.get("page_hint")
                    )
                    if match:
                        item["page_hint"] = match.page_number
                        item["match_confidence"] = match.confidence
                        item["match_type"] = match.match_type
                        if match.bbox and match.bbox[2] > match.bbox[0]:
                            item["bbox_start_x0"] = match.bbox[0]
                            item["bbox_start_y0"] = match.bbox[1]
                            item["bbox_start_x1"] = match.bbox[2]
                            item["bbox_start_y1"] = match.bbox[3]
                            item["page_start"] = match.page_number
                            item["page_end"] = match.page_number
                return item

            # Create tasks for all items (risks + recommendations)
            locate_tasks = []
            for idx, risk in enumerate(final_result.get("risks", [])):
                locate_tasks.append(locate_item(risk, "risk", idx))
            for idx, rec in enumerate(final_result.get("recommendations", [])):
                locate_tasks.append(locate_item(rec, "rec", idx))

            # Execute all localization in parallel
            annotation_items = await asyncio.gather(*locate_tasks)

            # Deduplicate annotation items by quote to avoid overlapping annotations
            seen_quotes = set()
            unique_items = []
            for item in annotation_items:
                quote = item.get("quote", "").strip()[:100]  # Normalize: first 100 chars
                if quote and quote not in seen_quotes:
                    seen_quotes.add(quote)
                    unique_items.append(item)
                elif not quote:
                    unique_items.append(item)

            duplicates_removed = len(annotation_items) - len(unique_items)
            if duplicates_removed > 0:
                logger.info(f"🔄 Deduplicated: {len(annotation_items)} → {len(unique_items)} items")
            annotation_items = unique_items

            # Add annotations to PDF
            annotation_result = pdf_annotation_service.annotate_pdf(pdf_bytes, annotation_items)

            yield f"event: annotated\ndata: {json.dumps({'message': f'{annotation_result.total_annotations} anotaciones añadidas', 'total': annotation_result.total_annotations, 'pages': annotation_result.pages_annotated, 'duplicates_removed': duplicates_removed, 'progress': 95})}\n\n"
            await flush()

            # 5. Build final response
            risks = []
            for r in final_result.get("risks", []):
                risks.append({
                    "id": r.get("id", f"risk_{uuid.uuid4().hex[:8]}"),
                    "type": "risk",
                    "severity": r.get("severity", "medium"),
                    "title": r.get("title", "Riesgo identificado"),
                    "description": r.get("description", ""),
                    "quote": r.get("quote"),
                    "clause": r.get("clause"),
                })

            recommendations = []
            for r in final_result.get("recommendations", []):
                recommendations.append({
                    "id": r.get("id", f"rec_{uuid.uuid4().hex[:8]}"),
                    "type": "recommendation",
                    "title": r.get("title", "Recomendación"),
                    "description": r.get("description", ""),
                    "quote": r.get("quote"),
                    "priority": r.get("priority", "medium"),
                })

            # Build annotations for response
            annotations = []
            for ann in annotation_result.annotations:
                rect_data = ann.get("rect", {})
                annotations.append({
                    "id": ann.get("id", ""),
                    "type": ann.get("type", "risk"),
                    "severity": ann.get("severity"),
                    "title": ann.get("title", ""),
                    "description": ann.get("description", ""),
                    "page_number": ann.get("page_number", 1),
                    "rect": {
                        "x0": rect_data.get("x0", 0),
                        "y0": rect_data.get("y0", 0),
                        "x1": rect_data.get("x1", 0),
                        "y1": rect_data.get("y1", 0),
                    },
                    "confidence": ann.get("confidence", 0.0),
                })

            # Final complete event with all data
            complete_data = {
                "success": True,
                "progress": 100,
                "annotated_pdf": base64.b64encode(annotation_result.pdf_bytes).decode("utf-8"),
                "annotations": annotations,
                "pages_annotated": annotation_result.pages_annotated,
                "total_annotations": annotation_result.total_annotations,
                "failed_annotations": annotation_result.failed_annotations,
                "analysis": {
                    "document_id": document_id,
                    "summary": final_result.get("summary", "Análisis completado"),
                    "risks": risks,
                    "recommendations": recommendations,
                    "confidence_score": final_result.get("confidence_score", 0.8),
                    "analysis_type": analysis_type,
                },
            }

            # Calculate execution time
            end_time = asyncio.get_event_loop().time()
            execution_time_ms = int((end_time - start_time) * 1000)

            # Persist final results to database
            if current_job_id:
                # Convert annotations to serializable format
                annotations_for_db = []
                for ann in annotation_result.annotations:
                    rect_data = ann.get("rect", {})
                    annotations_for_db.append({
                        "id": ann.get("id", ""),
                        "type": ann.get("type", "risk"),
                        "severity": ann.get("severity"),
                        "title": ann.get("title", ""),
                        "description": ann.get("description", ""),
                        "page_number": ann.get("page_number", 1),
                        "rect": {
                            "x0": rect_data.get("x0", 0),
                            "y0": rect_data.get("y0", 0),
                            "x1": rect_data.get("x1", 0),
                            "y1": rect_data.get("y1", 0),
                        },
                        "confidence": ann.get("confidence", 0.0),
                    })

                await persistence.mark_completed(
                    job_id=current_job_id,
                    summary=final_result.get("summary", "Análisis completado"),
                    risks=risks,
                    recommendations=recommendations,
                    findings=all_findings,
                    annotations=annotations_for_db,
                    confidence_score=final_result.get("confidence_score", 0.8),
                    execution_time_ms=execution_time_ms,
                )

            # Add job_id and execution_time to complete_data
            complete_data["job_id"] = current_job_id
            complete_data["execution_time_ms"] = execution_time_ms

            yield f"event: complete\ndata: {json.dumps(complete_data, ensure_ascii=False)}\n\n"

            logger.info(f"✅ Streaming analysis complete: {annotation_result.total_annotations} annotations, persisted to job {current_job_id}")

        except Exception as e:
            logger.exception(f"❌ Streaming analysis failed: {e}")
            # Persist error to database
            if current_job_id:
                await persistence.mark_failed(current_job_id, str(e))
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


async def _fetch_document_from_storage(
    document_id: str,
    tenant_id: str
) -> Optional[bytes]:
    """
    Fetch document PDF from storage service.

    The storage-service requires:
    - X-API-Key: microservice auth
    - X-Tenant-ID: tenant for path construction
    - X-User-ID: user who owns the document (created_by)

    The storage path is constructed internally as:
    tenant-{tenant_id}/user-{user_id}/{filename}
    """
    try:
        import httpx
        from app.core.config import settings

        # Step 1: Get document info from PostgreSQL directly
        # (Main API requires Bearer token which we don't have in microservice context)
        file_path = None
        user_id = None

        try:
            import asyncpg
            import os

            # Parse database URL for asyncpg
            # Format: postgresql+asyncpg://user:pass@host:port/db
            db_url = settings.database_url
            # Convert SQLAlchemy URL to asyncpg format
            if "postgresql+asyncpg://" in db_url:
                db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

            conn = await asyncpg.connect(db_url)
            try:
                row = await conn.fetchrow(
                    """
                    SELECT file_path, created_by
                    FROM documents
                    WHERE id = $1 AND tenant_id = $2
                    """,
                    document_id, tenant_id
                )
                if row:
                    file_path = row["file_path"]
                    user_id = row["created_by"]
                    logger.info(f"Got document info from DB: file_path={file_path}, user_id={user_id}")
                else:
                    logger.warning(f"Document {document_id} not found in database")
                    return None
            finally:
                await conn.close()

        except Exception as db_error:
            logger.error(f"Database query failed: {db_error}")
            return None

        if not file_path:
            logger.warning(f"No file_path for document {document_id}")
            return None

        if not user_id:
            logger.warning(f"No created_by in document {document_id}, trying with 'system'")
            user_id = "system"

        # Step 2: Download from storage-service with proper headers
        async with httpx.AsyncClient(timeout=60.0) as client:
            # The storage-service /proxy/{path} endpoint constructs the full path:
            # tenant-{tenant_id}/user-{user_id}/{path}
            response = await client.get(
                f"{settings.storage_service_url}/api/v1/storage/proxy/{file_path}",
                headers={
                    "X-API-Key": settings.MICROSERVICES_API_KEY,
                    "X-Tenant-ID": tenant_id,
                    "X-User-ID": str(user_id),
                }
            )

            if response.status_code == 200:
                logger.info(f"PDF fetched successfully: {len(response.content)} bytes")
                return response.content

            logger.warning(f"Proxy endpoint failed: {response.status_code}")

            # Fallback: Try /download/ endpoint
            response = await client.get(
                f"{settings.storage_service_url}/api/v1/storage/download/{file_path}",
                headers={
                    "X-API-Key": settings.MICROSERVICES_API_KEY,
                    "X-Tenant-ID": tenant_id,
                    "X-User-ID": str(user_id),
                }
            )

            if response.status_code == 200:
                logger.info(f"PDF fetched via download endpoint: {len(response.content)} bytes")
                return response.content

            logger.error(f"All storage endpoints failed for {file_path}: {response.status_code}")
            return None

    except Exception as e:
        logger.error(f"Error fetching document from storage: {e}")
        return None


async def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text content from PDF using PyMuPDF."""
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text_parts = []

        for page in doc:
            text_parts.append(page.get_text())

        doc.close()
        return "\n\n".join(text_parts)
    except Exception as e:
        logger.error(f"Error extracting PDF text: {e}")
        return ""


async def _run_document_analysis(
    document_id: str,
    tenant_id: str,
    text_content: str,
    analysis_type: str
) -> DocumentAnalysisResult:
    """
    Run document analysis using LLM with structured JSON output.

    This calls the LLM directly with the document content and a specialized
    prompt that returns JSON with exact quotes for PDF annotation.

    The system prompt is loaded from config/prompts/emma_prompts.yaml (document_analysis_json)
    """
    import json
    import re
    import httpx
    from app.services.rag.prompt_loader import load_prompts
    from app.core.config import settings

    try:
        # Load prompt from YAML configuration
        prompts = load_prompts("emma_prompts.yaml")
        system_prompt = prompts.get("document_analysis_json", "")

        if not system_prompt:
            logger.warning("⚠️ document_analysis_json prompt not found in YAML, using fallback")
            system_prompt = """Eres un analista legal. Analiza el documento y devuelve JSON con:
- summary: resumen ejecutivo
- risks: lista de riesgos con id, severity, title, description, quote (cita exacta del documento)
- recommendations: lista de recomendaciones
- confidence_score: 0-1"""

        # Truncate content for context (to fit in context window)
        max_context_len = 12000
        if len(text_content) > max_context_len:
            half = max_context_len // 2
            truncated_content = text_content[:half] + "\n\n[...contenido intermedio...]\n\n" + text_content[-half:]
        else:
            truncated_content = text_content

        # Build the user prompt with document content
        user_prompt = f"""DOCUMENTO A ANALIZAR (ID: {document_id}):
---
{truncated_content}
---

Analiza este documento e identifica todos los riesgos y recomendaciones.
IMPORTANTE: Para cada hallazgo, incluye una cita textual EXACTA del documento (campo "quote")."""

        logger.info(f"🧠 Running direct LLM analysis for document {document_id} (content: {len(text_content)} chars)")

        # Call LLM directly (vLLM - OpenAI compatible API)
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.vllm_base_url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "model": settings.vllm_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "stream": False,
                    "temperature": 0.3,
                    "max_tokens": 4000,
                }
            )
            response.raise_for_status()
            result = response.json()
            answer = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        logger.info(f"📝 LLM response length: {len(answer)} chars")

        # Parse JSON from Emma's response
        parsed = _parse_analysis_json(answer)

        if parsed:
            logger.info(f"✅ Parsed analysis: {len(parsed.get('risks', []))} risks, {len(parsed.get('recommendations', []))} recommendations")

            risks = []
            for r in parsed.get("risks", []):
                risks.append(AnalysisRisk(
                    id=r.get("id", f"risk_{uuid.uuid4().hex[:8]}"),
                    type="risk",
                    severity=r.get("severity", "medium"),
                    title=r.get("title", "Riesgo identificado"),
                    description=r.get("description", ""),
                    quote=r.get("quote"),
                    clause=r.get("clause"),
                    recommendation=r.get("recommendation"),
                ))

            recommendations = []
            for r in parsed.get("recommendations", []):
                recommendations.append(AnalysisRecommendation(
                    id=r.get("id", f"rec_{uuid.uuid4().hex[:8]}"),
                    type="recommendation",
                    title=r.get("title", "Recomendación"),
                    description=r.get("description", ""),
                    quote=r.get("quote"),
                    priority=r.get("priority", "medium"),
                    action_required=r.get("action_required"),
                ))

            return DocumentAnalysisResult(
                document_id=document_id,
                summary=parsed.get("summary", "Análisis completado"),
                risks=risks,
                recommendations=recommendations,
                confidence_score=parsed.get("confidence_score", 0.7),
                analysis_type=analysis_type,
            )

        # Fallback: Parse natural language response for risks
        logger.warning(f"⚠️ JSON parsing failed, attempting natural language extraction")
        return _extract_from_natural_language(document_id, answer, analysis_type)

    except Exception as e:
        logger.exception(f"Error running document analysis: {e}")
        return DocumentAnalysisResult(
            document_id=document_id,
            summary=f"Error en el análisis: {str(e)}",
            risks=[],
            recommendations=[],
            confidence_score=0.0,
            analysis_type=analysis_type,
        )


def _parse_analysis_json(answer: str) -> Optional[dict]:
    """Parse JSON from Emma's response using multiple strategies."""
    import json
    import re

    def clean_json_string(s: str) -> str:
        """Clean JSON string by fixing common LLM issues."""
        # Remove control characters except \n, \r, \t
        s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', s)
        # Fix trailing commas before ] or }
        s = re.sub(r',\s*([}\]])', r'\1', s)
        # Fix newlines inside strings (replace with space)
        # This is tricky - we need to find strings and fix them
        # Simple approach: replace literal newlines in quoted strings
        def fix_string_newlines(match):
            content = match.group(1)
            # Replace actual newlines with \n escape or space
            content = content.replace('\n', ' ').replace('\r', ' ')
            # Remove multiple spaces
            content = re.sub(r' +', ' ', content)
            return f'"{content}"'
        # Match strings and fix newlines inside them
        s = re.sub(r'"([^"]*(?:\\"[^"]*)*)"', fix_string_newlines, s)
        return s

    # Strategy 1: Direct JSON parse
    try:
        return json.loads(answer.strip())
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract from markdown code block
    json_block = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', answer)
    if json_block:
        try:
            cleaned = clean_json_string(json_block.group(1))
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    # Strategy 3: Find JSON object and clean it
    json_match = re.search(r'\{[\s\S]*\}', answer)
    if json_match:
        try:
            json_str = clean_json_string(json_match.group())
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed after cleaning: {e}")
            # Strategy 4: Try to parse with more aggressive cleaning
            try:
                # Remove all newlines and extra spaces
                json_str = re.sub(r'\s+', ' ', json_match.group())
                json_str = clean_json_string(json_str)
                return json.loads(json_str)
            except json.JSONDecodeError as e2:
                logger.warning(f"JSON parse failed (aggressive): {e2}")
                logger.debug(f"Attempted JSON: {json_str[:500]}...")

    return None


def _extract_from_natural_language(
    document_id: str,
    answer: str,
    analysis_type: str
) -> DocumentAnalysisResult:
    """Extract risks and recommendations from natural language response."""
    import re

    risks = []
    recommendations = []

    # Look for risk patterns in Spanish
    risk_patterns = [
        r'[Rr]iesgo\s*(?:alto|medio|bajo)?[:\s]+([^.]+\.)',
        r'⚠️\s*([^.]+\.)',
        r'[Pp]roblema[:\s]+([^.]+\.)',
        r'[Ii]ncumplimiento[:\s]+([^.]+\.)',
    ]

    for pattern in risk_patterns:
        matches = re.findall(pattern, answer)
        for i, match in enumerate(matches[:5]):  # Limit to 5 per pattern
            # Try to extract a quote (text in quotes)
            quote_match = re.search(r'"([^"]{15,})"', match)
            quote = quote_match.group(1) if quote_match else None

            risks.append(AnalysisRisk(
                id=f"risk_{i}_{uuid.uuid4().hex[:4]}",
                type="risk",
                severity="medium",
                title=match[:50] + "..." if len(match) > 50 else match,
                description=match,
                quote=quote,
            ))

    # Look for recommendation patterns
    rec_patterns = [
        r'[Rr]ecomendaci[oó]n[:\s]+([^.]+\.)',
        r'[Ss]e\s+recomienda[:\s]+([^.]+\.)',
        r'✅\s*([^.]+\.)',
        r'[Dd]eber[ií]a[:\s]+([^.]+\.)',
    ]

    for pattern in rec_patterns:
        matches = re.findall(pattern, answer)
        for i, match in enumerate(matches[:5]):
            quote_match = re.search(r'"([^"]{15,})"', match)
            quote = quote_match.group(1) if quote_match else None

            recommendations.append(AnalysisRecommendation(
                id=f"rec_{i}_{uuid.uuid4().hex[:4]}",
                type="recommendation",
                title=match[:50] + "..." if len(match) > 50 else match,
                description=match,
                quote=quote,
                priority="medium",
            ))

    # Extract summary (first paragraph or first 300 chars)
    summary_match = re.match(r'^([^.]+\.[^.]+\.)', answer)
    summary = summary_match.group(1) if summary_match else answer[:300]

    return DocumentAnalysisResult(
        document_id=document_id,
        summary=summary,
        risks=risks,
        recommendations=recommendations,
        confidence_score=0.5 if (risks or recommendations) else 0.2,
        analysis_type=analysis_type,
    )


@router.post("/document/markdown", response_model=DocumentMarkdownResponse)
async def get_document_markdown(
    pdf_file: UploadFile = File(...),
    document_id: str = Form(...),
    _: bool = Depends(verify_api_key)
):
    """
    Convert a PDF document to Markdown format using PyMuPDF4LLM.

    This endpoint extracts the document content and converts it to
    LLM-optimized Markdown, preserving structure like headings,
    tables, and lists.

    Returns:
        DocumentMarkdownResponse with full markdown and per-page breakdown
    """
    try:
        pdf_bytes = await pdf_file.read()
        markdown_service = get_pdf_markdown_service()

        # Convert PDF to Markdown with caching
        result = markdown_service.convert_pdf_bytes(
            pdf_bytes,
            cache_key=document_id,
            page_chunks=True
        )

        return DocumentMarkdownResponse(
            document_id=document_id,
            full_markdown=result.full_markdown,
            pages=[
                MarkdownPage(
                    page_number=p.page_number,
                    content=p.content,
                    char_count=p.char_count
                )
                for p in result.pages
            ],
            total_pages=result.total_pages,
            total_chars=result.total_chars,
            metadata=result.metadata
        )

    except Exception as e:
        logger.error(f"Error converting PDF to Markdown: {e}")
        raise HTTPException(status_code=500, detail=f"Error converting PDF: {str(e)}")


@router.post("/analyze/markdown", response_model=AnalysisWithMarkdownResponse)
async def analyze_document_with_markdown(
    pdf_file: UploadFile = File(...),
    document_id: str = Form(...),
    tenant_id: str = Form(...),
    analysis_type: str = Form(default="legal"),
    _: bool = Depends(verify_api_key)
):
    """
    Analyze a document and return results with Markdown view instead of PDF.

    This combines the analysis workflow with Markdown conversion:
    1. Converts PDF to Markdown using PyMuPDF4LLM
    2. Runs the full analysis pipeline
    3. Injects analysis findings as inline Markdown annotations
    4. Returns both raw and annotated Markdown

    Use this instead of /analyze/with-annotations when you want a
    text-based view rather than PDF rendering.
    """
    try:
        pdf_bytes = await pdf_file.read()
        markdown_service = get_pdf_markdown_service()

        # Step 1: Convert PDF to Markdown
        logger.info(f"Converting PDF to Markdown for document {document_id}")
        md_result = markdown_service.convert_pdf_bytes(
            pdf_bytes,
            cache_key=document_id,
            page_chunks=True
        )

        # Step 2: Run analysis (reuse existing emma service)
        # Extract text for analysis
        text_content = md_result.full_markdown

        # Build analysis query
        query = EmmaQuery(
            query=f"Analiza el siguiente documento legal y extrae riesgos y recomendaciones:\n\n{text_content[:50000]}",
            query_type="analyze",
            tenant_id=tenant_id,
            enable_debug=False
        )

        logger.info(f"Running analysis for document {document_id}")
        analysis_response = await emma_service.execute_query(query)

        # Parse analysis result from Emma response
        analysis_result = _extract_analysis_from_response(
            analysis_response,
            document_id,
            analysis_type
        )

        # Step 3: Build annotation list for frontend compatibility
        annotations: List[PDFAnnotation] = []
        for risk in analysis_result.risks:
            if risk.quote:
                annotations.append(PDFAnnotation(
                    id=risk.id,
                    type="risk",
                    severity=risk.severity,
                    title=risk.title,
                    description=risk.description,
                    page_number=1,  # Will be updated based on quote location
                    rect=AnnotationRect(x0=0, y0=0, x1=0, y1=0),
                    text_found=risk.quote,
                    confidence=0.8
                ))

        for rec in analysis_result.recommendations:
            if rec.quote:
                annotations.append(PDFAnnotation(
                    id=rec.id,
                    type="recommendation",
                    severity=None,
                    title=rec.title,
                    description=rec.description,
                    page_number=1,
                    rect=AnnotationRect(x0=0, y0=0, x1=0, y1=0),
                    text_found=rec.quote,
                    confidence=0.8
                ))

        # Find actual page numbers for annotations by searching markdown pages
        for ann in annotations:
            for page in md_result.pages:
                if ann.text_found and ann.text_found.lower() in page.content.lower():
                    ann.page_number = page.page_number
                    break

        # Step 4: Create annotated markdown with inline highlights
        annotated_markdown = markdown_service.inject_annotations(
            md_result.full_markdown,
            [
                {
                    "id": ann.id,
                    "type": ann.type,
                    "severity": ann.severity,
                    "title": ann.title,
                    "quote": ann.text_found
                }
                for ann in annotations
            ],
            style="highlight"
        )

        return AnalysisWithMarkdownResponse(
            markdown=DocumentMarkdownResponse(
                document_id=document_id,
                full_markdown=md_result.full_markdown,
                pages=[
                    MarkdownPage(
                        page_number=p.page_number,
                        content=p.content,
                        char_count=p.char_count
                    )
                    for p in md_result.pages
                ],
                total_pages=md_result.total_pages,
                total_chars=md_result.total_chars,
                metadata=md_result.metadata
            ),
            annotations=annotations,
            annotated_markdown=annotated_markdown,
            analysis=analysis_result
        )

    except Exception as e:
        logger.error(f"Error in markdown analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


# ========================================================================
# Human-in-the-Loop (HITL) / Clarification Endpoints
# OpenCode-style permission resolution
# ========================================================================

from pydantic import BaseModel


class ClarificationResolutionRequest(BaseModel):
    """Request to resolve a clarification prompt."""
    session_id: str
    tenant_id: str
    request_id: Optional[str] = None  # Optional: specific request ID
    selected_values: List[str]  # User's selected option values
    follow_up_query: Optional[str] = None  # Optional: continue with this query


class ClarificationResolutionResponse(BaseModel):
    """Response after resolving a clarification."""
    success: bool
    message: str
    selected_document: Optional[Dict[str, Any]] = None
    continue_analysis: bool = False


@router.post("/clarification/resolve", response_model=ClarificationResolutionResponse)
async def resolve_clarification(
    request: ClarificationResolutionRequest,
    _: bool = Depends(verify_api_key)
):
    """
    Resolve a pending clarification request with user's selection.

    This endpoint is called when the user makes a selection in the
    clarification UI (e.g., selecting which document to analyze).

    The selection is stored in the session context so the next query
    can continue with the selected document.

    Args:
        request: Contains session_id, selected_values, and optional follow_up_query

    Returns:
        ClarificationResolutionResponse with success status and next steps
    """
    from app.agents.tools.clarification_tools import extract_selected_document
    from app.agents.permissions import get_tool_interceptor

    try:
        logger.info(
            f"🔄 Resolving clarification: session={request.session_id[:16]}..., "
            f"selected={request.selected_values}"
        )

        # If we have a request_id, resolve it in the interceptor
        if request.request_id:
            interceptor = get_tool_interceptor()
            resolved = interceptor.resolve_request(
                request.request_id,
                request.selected_values
            )
            if resolved:
                logger.info(f"✅ Resolved request {request.request_id}")

        # Store the selection in session context for the next query
        # This allows Emma to continue with the selected document
        selected_doc = None
        if request.selected_values:
            selected_value = request.selected_values[0]  # Primary selection

            # Store in Redis for session continuity
            import redis.asyncio as redis
            from app.agents.emma_coordinator import get_redis_pool

            pool = get_redis_pool()
            redis_client = redis.Redis(connection_pool=pool)

            # Store clarification context
            context_key = f"emma:clarification:{request.tenant_id}:{request.session_id}"
            await redis_client.setex(
                context_key,
                3600,  # 1 hour TTL
                json.dumps({
                    "selected_values": request.selected_values,
                    "selected_document_id": selected_value,
                    "timestamp": asyncio.get_event_loop().time(),
                })
            )

            logger.info(f"💾 Stored clarification context: {context_key}")

            selected_doc = {
                "id": selected_value,
                "selected_values": request.selected_values,
            }

        return ClarificationResolutionResponse(
            success=True,
            message="Selección registrada. Puedes continuar con tu consulta.",
            selected_document=selected_doc,
            continue_analysis=request.follow_up_query is not None,
        )

    except Exception as e:
        logger.error(f"❌ Clarification resolution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clarification/pending/{session_id}")
async def get_pending_clarification(
    session_id: str,
    tenant_id: str,
    _: bool = Depends(verify_api_key)
):
    """
    Check if there's a pending clarification for a session.

    Returns any stored clarification context from a previous interaction.
    """
    try:
        import redis.asyncio as redis
        from app.agents.emma_coordinator import get_redis_pool

        pool = get_redis_pool()
        redis_client = redis.Redis(connection_pool=pool)

        context_key = f"emma:clarification:{tenant_id}:{session_id}"
        context_data = await redis_client.get(context_key)

        if context_data:
            return {
                "has_pending": True,
                "context": json.loads(context_data)
            }

        return {
            "has_pending": False,
            "context": None
        }

    except Exception as e:
        logger.error(f"❌ Failed to get pending clarification: {e}")
        raise HTTPException(status_code=500, detail=str(e))
