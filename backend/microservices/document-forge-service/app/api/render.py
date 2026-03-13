"""POST /prepare and POST /render — template preparation and rendering."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import verify_api_key
from app.schemas.render import (
    OutputInfo,
    PrepareRequest,
    PrepareResponse,
    RenderRequest,
    RenderResponse,
)
from app.schemas.session import SessionStatus
from app.services.converter import get_converter
from app.services.renderer import get_renderer
from app.services.session_store import get_session_store
from app.services.template_preparer import get_template_preparer

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/prepare", response_model=PrepareResponse)
async def prepare_template(
    request: PrepareRequest,
    _api_key: str = Depends(verify_api_key),
):
    """Insert docxtpl markers into the DOCX at detected field positions."""
    store = get_session_store()
    session = await store.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    if session.status not in (SessionStatus.ANALYZED, SessionStatus.PREPARED):
        raise HTTPException(
            status_code=400,
            detail=f"Session in wrong state: {session.status}. Expected: analyzed",
        )

    # Get source DOCX bytes
    source_bytes = await store.get_blob(session.session_id, "source")
    if not source_bytes:
        raise HTTPException(status_code=404, detail="Source document not found in session")

    # Prepare template
    preparer = get_template_preparer()
    template_bytes, inserted, failed = preparer.prepare(
        docx_bytes=source_bytes,
        fields=session.fields,
        fields_to_mark=request.fields_to_mark or None,
        custom_fields=[cf.model_dump() for cf in request.custom_fields] if request.custom_fields else None,
    )

    # Store prepared template
    await store.store_blob(session.session_id, "template", template_bytes)
    session.status = SessionStatus.PREPARED
    await store.update_session(session)

    return PrepareResponse(
        session_id=session.session_id,
        markers_inserted=inserted,
        markers_failed=len(failed),
        failed_fields=failed,
        template_ready=inserted > 0,
    )


@router.post("/render", response_model=RenderResponse)
async def render_document(
    request: RenderRequest,
    _api_key: str = Depends(verify_api_key),
):
    """Fill markers with values and generate final document."""
    store = get_session_store()
    session = await store.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    # Allow rendering from either PREPARED or ANALYZED state
    # If ANALYZED, we auto-prepare first (mark all fields)
    if session.status == SessionStatus.ANALYZED:
        source_bytes = await store.get_blob(session.session_id, "source")
        if not source_bytes:
            raise HTTPException(status_code=404, detail="Source document not found")

        preparer = get_template_preparer()
        # Only mark fields that have values provided
        fields_to_mark = list(request.field_values.keys())
        template_bytes, inserted, failed = preparer.prepare(
            docx_bytes=source_bytes,
            fields=session.fields,
            fields_to_mark=fields_to_mark,
        )
        await store.store_blob(session.session_id, "template", template_bytes)
        session.status = SessionStatus.PREPARED
        await store.update_session(session)
    elif session.status not in (SessionStatus.PREPARED, SessionStatus.RENDERED):
        raise HTTPException(
            status_code=400,
            detail=f"Session in wrong state: {session.status}. Expected: prepared or analyzed",
        )

    # Get prepared template
    template_bytes = await store.get_blob(session.session_id, "template")
    if not template_bytes:
        raise HTTPException(status_code=404, detail="Prepared template not found")

    # Render with docxtpl
    renderer = get_renderer()
    docx_bytes = renderer.render(template_bytes, request.field_values)

    # Store rendered DOCX
    await store.store_blob(session.session_id, "docx", docx_bytes)

    # Determine document title
    doc_title = request.document_title or session.source_title.rsplit(".", 1)[0]

    outputs: dict[str, OutputInfo] = {}

    # Normalize output formats
    formats = set()
    for fmt in request.output_formats:
        if fmt == "both":
            formats.update(["docx", "pdf"])
        else:
            formats.add(fmt)

    # DOCX output
    if "docx" in formats:
        outputs["docx"] = OutputInfo(
            size_bytes=len(docx_bytes),
            download_url=f"/sessions/{session.session_id}/download?format=docx",
        )

    # PDF output
    if "pdf" in formats:
        converter = get_converter()
        try:
            pdf_bytes = await converter.docx_to_pdf(docx_bytes, f"{doc_title}.docx")
            await store.store_blob(session.session_id, "pdf", pdf_bytes)
            outputs["pdf"] = OutputInfo(
                size_bytes=len(pdf_bytes),
                download_url=f"/sessions/{session.session_id}/download?format=pdf",
            )
        except Exception as e:
            logger.error("PDF conversion failed: %s", e)
            # PDF failure is non-fatal — DOCX still available

    # Update session
    session.status = SessionStatus.RENDERED
    session.field_values = request.field_values
    session.document_title = doc_title
    await store.update_session(session)

    return RenderResponse(
        session_id=session.session_id,
        outputs=outputs,
        fields_filled=len(request.field_values),
        document_title=doc_title,
    )
