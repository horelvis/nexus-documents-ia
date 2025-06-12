"""
Conversion API endpoints
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import Response
from typing import Optional, Dict, Any
import tempfile
import os

from app.core.security import validate_service_access
from app.services.conversion_service import ConversionService

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    service = ConversionService()
    gotenberg_healthy = await service.health_check()
    
    return {
        "status": "healthy" if gotenberg_healthy else "unhealthy",
        "service": "gotenberg-service",
        "gotenberg_available": gotenberg_healthy
    }

@router.post("/convert/office-to-pdf")
async def convert_office_to_pdf(
    file: UploadFile = File(...),
    landscape: bool = Form(False),
    margin_top: str = Form("0.5"),
    margin_bottom: str = Form("0.5"),
    margin_left: str = Form("0.5"),
    margin_right: str = Form("0.5"),
    security: dict = Depends(validate_service_access)
):
    """Convert Office documents to PDF"""
    try:
        service = ConversionService()
        
        # Validate file format
        if not service.is_supported_format(file.filename):
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported file format: {file.filename}"
            )
        
        # Read file content
        file_content = await file.read()
        
        # Convert to PDF
        options = {
            'landscape': landscape,
            'margin_top': margin_top,
            'margin_bottom': margin_bottom,
            'margin_left': margin_left,
            'margin_right': margin_right,
        }
        
        pdf_content = await service.convert_office_to_pdf(
            file_content=file_content,
            filename=file.filename,
            **options
        )
        
        # Return PDF as response
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={file.filename}.pdf"
            }
        )
        
    except Exception as e:
        logger.error(f"Error converting office document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/convert/html-to-pdf")
async def convert_html_to_pdf(
    html_content: str = Form(...),
    css_content: Optional[str] = Form(None),
    landscape: bool = Form(False),
    margin_top: str = Form("1"),
    margin_bottom: str = Form("1"),
    margin_left: str = Form("1"),
    margin_right: str = Form("1"),
    scale: str = Form("1"),
    security: dict = Depends(validate_service_access)
):
    """Convert HTML to PDF"""
    try:
        service = ConversionService()
        
        options = {
            'landscape': landscape,
            'margin_top': margin_top,
            'margin_bottom': margin_bottom,
            'margin_left': margin_left,
            'margin_right': margin_right,
            'scale': scale,
        }
        
        pdf_content = await service.convert_html_to_pdf(
            html_content=html_content,
            css_content=css_content,
            **options
        )
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=document.pdf"
            }
        )
        
    except Exception as e:
        logger.error(f"Error converting HTML to PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/convert/markdown-to-pdf")
async def convert_markdown_to_pdf(
    markdown_content: str = Form(...),
    css_content: Optional[str] = Form(None),
    landscape: bool = Form(False),
    margin_top: str = Form("1"),
    margin_bottom: str = Form("1"),
    margin_left: str = Form("1"),
    margin_right: str = Form("1"),
    security: dict = Depends(validate_service_access)
):
    """Convert Markdown to PDF"""
    try:
        service = ConversionService()
        
        options = {
            'landscape': landscape,
            'margin_top': margin_top,
            'margin_bottom': margin_bottom,
            'margin_left': margin_left,
            'margin_right': margin_right,
        }
        
        pdf_content = await service.convert_markdown_to_pdf(
            markdown_content=markdown_content,
            css_content=css_content,
            **options
        )
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=document.pdf"
            }
        )
        
    except Exception as e:
        logger.error(f"Error converting Markdown to PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/convert/text-to-pdf")
async def convert_text_to_pdf(
    text_content: str = Form(...),
    title: Optional[str] = Form(None),
    landscape: bool = Form(False),
    margin_top: str = Form("1"),
    margin_bottom: str = Form("1"),
    margin_left: str = Form("1"),
    margin_right: str = Form("1"),
    security: dict = Depends(validate_service_access)
):
    """Convert plain text to PDF"""
    try:
        service = ConversionService()
        
        options = {
            'landscape': landscape,
            'margin_top': margin_top,
            'margin_bottom': margin_bottom,
            'margin_left': margin_left,
            'margin_right': margin_right,
        }
        
        pdf_content = await service.convert_text_to_pdf(
            text_content=text_content,
            title=title,
            **options
        )
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={title or 'document'}.pdf"
            }
        )
        
    except Exception as e:
        logger.error(f"Error converting text to PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/thumbnails/generate-from-pdf")
async def generate_thumbnails_from_pdf(
    file: UploadFile = File(...),
    max_pages: int = Form(5),
    security: dict = Depends(validate_service_access)
):
    """Generate thumbnails from PDF"""
    try:
        service = ConversionService()
        
        # Validate it's a PDF
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="File must be a PDF")
        
        # Read file content
        pdf_content = await file.read()
        
        # Generate thumbnails
        thumbnails = service.generate_thumbnails_from_pdf(pdf_content, max_pages)
        
        return {
            "thumbnails": thumbnails,
            "count": len(thumbnails)
        }
        
    except Exception as e:
        logger.error(f"Error generating PDF thumbnails: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/thumbnails/generate-from-image")
async def generate_thumbnail_from_image(
    file: UploadFile = File(...),
    security: dict = Depends(validate_service_access)
):
    """Generate thumbnail from image"""
    try:
        service = ConversionService()
        
        # Validate it's an image
        supported_formats = service.get_supported_formats()["images"]
        file_ext = f".{file.filename.split('.')[-1].lower()}"
        
        if file_ext not in supported_formats:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported image format: {file_ext}"
            )
        
        # Read file content
        image_content = await file.read()
        
        # Generate thumbnail
        thumbnail = service.generate_image_thumbnail(image_content, file.content_type)
        
        if not thumbnail:
            raise HTTPException(status_code=500, detail="Failed to generate thumbnail")
        
        return {
            "thumbnail": thumbnail,
            "original_filename": file.filename
        }
        
    except Exception as e:
        logger.error(f"Error generating image thumbnail: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/formats/supported")
async def get_supported_formats(security: dict = Depends(validate_service_access)):
    """Get supported file formats"""
    service = ConversionService()
    return {
        "formats": service.get_supported_formats(),
        "service": "gotenberg-service"
    }