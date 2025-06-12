"""
Gotenberg Microservice Client
"""
import httpx
import asyncio
import logging
from typing import Optional, Dict, Any, BinaryIO
from pathlib import Path
import tempfile
import os
from app.core.config import settings

logger = logging.getLogger(__name__)

class GotenbergMicroserviceClient:
    """Client for Gotenberg microservice"""
    
    def __init__(self, http_client: httpx.AsyncClient, tenant_id: str = None, user_id: str = None):
        self.http_client = http_client
        self.base_url = settings.GOTENBERG_BASE_URL
        self.tenant_id = tenant_id
        self.user_id = user_id
        
    def _get_auth_headers(self, tenant_id: str = None, user_id: str = None) -> dict:
        """Get authentication headers for microservice requests"""
        headers = {
            "X-API-Key": getattr(settings, 'API_KEY', 'your-secret-api-key-here'),
            "X-Tenant-ID": tenant_id or self.tenant_id or getattr(settings, 'DEFAULT_TENANT', 'default')
        }
        
        user_id_to_use = user_id or self.user_id
        if user_id_to_use:
            headers["X-User-ID"] = user_id_to_use
            
        return headers

    async def health_check(self) -> Dict[str, Any]:
        """Check Gotenberg service health"""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to GotenbergMicroserviceClient.")
        
        try:
            response = await self.http_client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return {"status": "healthy"}
            
        except Exception as e:
            logger.error(f"Gotenberg service health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    async def convert_office_to_pdf(
        self, 
        file_content: bytes = None,
        file_path: str = None, 
        filename: str = None,
        tenant_id: str = None,
        **options
    ) -> bytes:
        """Convert Office documents to PDF using Gotenberg LibreOffice route"""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to GotenbergMicroserviceClient.")
        
        try:
            # Handle both file_path and file_content inputs
            if file_path and not file_content:
                with open(file_path, 'rb') as f:
                    file_content = f.read()
                if not filename:
                    filename = Path(file_path).name
            elif not file_content:
                raise ValueError("Either file_content or file_path must be provided")
            
            files = {
                'files': (filename, file_content, self._get_mime_type(filename))
            }
            
            # Gotenberg uses different parameter names
            data = {
                'landscape': str(options.get('landscape', False)).lower(),
                'marginTop': str(options.get('margin_top', '0.5')),
                'marginBottom': str(options.get('margin_bottom', '0.5')),
                'marginLeft': str(options.get('margin_left', '0.5')),
                'marginRight': str(options.get('margin_right', '0.5')),
            }
            
            # Use official Gotenberg LibreOffice endpoint
            response = await self.http_client.post(
                f"{self.base_url}/forms/libreoffice/convert",
                files=files,
                data=data
            )
            
            response.raise_for_status()
            return response.content
            
        except httpx.HTTPError as e:
            logger.error(f"Gotenberg LibreOffice conversion HTTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"Gotenberg LibreOffice conversion error: {e}")
            raise

    async def convert_html_to_pdf(
        self, 
        html_content: str, 
        css_content: Optional[str] = None,
        tenant_id: str = None,
        **options
    ) -> bytes:
        """Convert HTML to PDF using Gotenberg Chromium route"""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to GotenbergMicroserviceClient.")
        
        try:
            # Create temporary HTML file
            files = {
                'files': ('index.html', html_content.encode('utf-8'), 'text/html')
            }
            
            # Add CSS file if provided
            if css_content:
                files['files'] = [
                    ('index.html', html_content.encode('utf-8'), 'text/html'),
                    ('style.css', css_content.encode('utf-8'), 'text/css')
                ]
            
            data = {
                'landscape': str(options.get('landscape', False)).lower(),
                'marginTop': str(options.get('margin_top', '1')),
                'marginBottom': str(options.get('margin_bottom', '1')),
                'marginLeft': str(options.get('margin_left', '1')),
                'marginRight': str(options.get('margin_right', '1')),
                'scale': str(options.get('scale', '1')),
            }
            
            # Use official Gotenberg Chromium HTML endpoint
            response = await self.http_client.post(
                f"{self.base_url}/forms/chromium/convert/html",
                files=files,
                data=data
            )
            
            response.raise_for_status()
            return response.content
            
        except Exception as e:
            logger.error(f"HTML to PDF conversion error: {e}")
            raise

    async def convert_markdown_to_pdf(
        self, 
        markdown_content: str, 
        css_content: Optional[str] = None,
        tenant_id: str = None,
        **options
    ) -> bytes:
        """Convert Markdown to PDF using Gotenberg Chromium markdown route"""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to GotenbergMicroserviceClient.")
        
        try:
            files = {
                'files': ('index.md', markdown_content.encode('utf-8'), 'text/markdown')
            }
            
            # Add CSS file if provided
            if css_content:
                files['files'] = [
                    ('index.md', markdown_content.encode('utf-8'), 'text/markdown'),
                    ('style.css', css_content.encode('utf-8'), 'text/css')
                ]
            
            data = {
                'landscape': str(options.get('landscape', False)).lower(),
                'marginTop': str(options.get('margin_top', '1')),
                'marginBottom': str(options.get('margin_bottom', '1')),
                'marginLeft': str(options.get('margin_left', '1')),
                'marginRight': str(options.get('margin_right', '1')),
            }
            
            # Use official Gotenberg Chromium markdown endpoint
            response = await self.http_client.post(
                f"{self.base_url}/forms/chromium/convert/markdown",
                files=files,
                data=data
            )
            
            response.raise_for_status()
            return response.content
            
        except Exception as e:
            logger.error(f"Markdown to PDF conversion error: {e}")
            raise

    async def convert_text_to_pdf(
        self,
        text_content: str,
        title: Optional[str] = None,
        tenant_id: str = None,
        **options
    ) -> bytes:
        """Convert plain text to PDF by wrapping in HTML"""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to GotenbergMicroserviceClient.")
        
        try:
            # Wrap text content in basic HTML
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title or 'Text Document'}</title>
    <style>
        body {{ 
            font-family: monospace; 
            white-space: pre-wrap; 
            margin: 20px; 
            line-height: 1.4; 
        }}
    </style>
</head>
<body>{text_content}</body>
</html>"""
            
            # Use HTML conversion
            return await self.convert_html_to_pdf(
                html_content=html_content,
                tenant_id=tenant_id,
                **options
            )
            
        except Exception as e:
            logger.error(f"Text to PDF conversion error: {e}")
            raise

    async def generate_thumbnails_from_pdf(
        self, 
        pdf_content: bytes, 
        filename: str = "document.pdf",
        max_pages: int = 5,
        tenant_id: str = None
    ) -> list:
        """Generate thumbnails from PDF - Note: Gotenberg doesn't support this directly"""
        logger.warning("PDF thumbnail generation not supported by Gotenberg directly. Use pdf2image library instead.")
        return []

    async def generate_image_thumbnail(
        self, 
        image_content: bytes, 
        filename: str,
        tenant_id: str = None
    ) -> Optional[str]:
        """Generate thumbnail from image - Note: Gotenberg doesn't support this directly"""
        logger.warning("Image thumbnail generation not supported by Gotenberg directly. Use PIL library instead.")
        return None

    async def get_supported_formats(self, tenant_id: str = None) -> Dict[str, list]:
        """Get supported formats for Gotenberg"""
        return {
            'office': ['.docx', '.doc', '.odt', '.xlsx', '.xls', '.ods', '.pptx', '.ppt', '.odp', '.rtf'],
            'text': ['.html', '.htm', '.md', '.txt'],
            'images': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'],
            'pdf': ['.pdf']
        }

    def _get_mime_type(self, filename: str) -> str:
        """Determine MIME type based on extension"""
        ext = Path(filename).suffix.lower()
        mime_types = {
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.odt': 'application/vnd.oasis.opendocument.text',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.xls': 'application/vnd.ms-excel',
            '.ods': 'application/vnd.oasis.opendocument.spreadsheet',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.odp': 'application/vnd.oasis.opendocument.presentation',
            '.rtf': 'application/rtf',
            '.txt': 'text/plain',
        }
        return mime_types.get(ext, 'application/octet-stream')

    def _get_image_mime_type(self, filename: str) -> str:
        """Determine image MIME type based on extension"""
        ext = Path(filename).suffix.lower()
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.tiff': 'image/tiff',
        }
        return mime_types.get(ext, 'application/octet-stream')