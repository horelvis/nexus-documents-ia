"""POST /convert — standalone DOCX → PDF conversion."""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.config import get_settings
from app.core.security import verify_api_key
from app.services.converter import get_converter

logger = logging.getLogger(__name__)
router = APIRouter()

DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.post("/convert")
async def convert_docx_to_pdf(
    file: UploadFile = File(...),
    _api_key: str = Depends(verify_api_key),
):
    """Convert a DOCX file to PDF (delegates to gotenberg-service)."""
    settings = get_settings()

    content = await file.read()
    if len(content) > settings.max_document_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.max_document_size_mb}MB limit",
        )

    filename = file.filename or "document.docx"

    converter = get_converter()
    try:
        pdf_bytes = await converter.docx_to_pdf(content, filename)
    except Exception as e:
        logger.error("Conversion failed: %s", e)
        raise HTTPException(status_code=502, detail="PDF conversion failed")

    pdf_filename = filename.rsplit(".", 1)[0] + ".pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{pdf_filename}"'},
    )
