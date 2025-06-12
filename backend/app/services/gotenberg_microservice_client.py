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
        self.base_url = settings.GOTENBERG_MICROSERVICE_URL
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
        """Check Gotenberg microservice health"""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to GotenbergMicroserviceClient.")
        
        try:
            response = await self.http_client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Gotenberg microservice health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    async def convert_office_to_pdf(
        self, 
        file_content: bytes, 
        filename: str,
        tenant_id: str = None,
        **options
    ) -> bytes:
        """Convert Office documents to PDF via microservice"""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to GotenbergMicroserviceClient.")
        
        try:
            headers = self._get_auth_headers(tenant_id)
            
            files = {
                'file': (filename, file_content, self._get_mime_type(filename))
            }
            
            data = {
                'landscape': str(options.get('landscape', False)).lower(),
                'margin_top': str(options.get('margin_top', '0.5')),
                'margin_bottom': str(options.get('margin_bottom', '0.5')),
                'margin_left': str(options.get('margin_left', '0.5')),
                'margin_right': str(options.get('margin_right', '0.5')),
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/convert/office-to-pdf",
                files=files,
                data=data,
                headers=headers
            )
            
            response.raise_for_status()
            return response.content
            
        except httpx.HTTPError as e:
            logger.error(f"Gotenberg microservice HTTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"Gotenberg microservice conversion error: {e}")
            raise

    async def convert_html_to_pdf(
        self, 
        html_content: str, 
        css_content: Optional[str] = None,
        tenant_id: str = None,
        **options
    ) -> bytes:
        """Convert HTML to PDF via microservice"""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to GotenbergMicroserviceClient.")
        
        try:
            headers = self._get_auth_headers(tenant_id)
            
            data = {
                'html_content': html_content,
                'landscape': str(options.get('landscape', False)).lower(),
                'margin_top': str(options.get('margin_top', '1')),
                'margin_bottom': str(options.get('margin_bottom', '1')),
                'margin_left': str(options.get('margin_left', '1')),
                'margin_right': str(options.get('margin_right', '1')),
                'scale': str(options.get('scale', '1')),
            }
            
            if css_content:
                data['css_content'] = css_content
            
            response = await self.http_client.post(
                f"{self.base_url}/convert/html-to-pdf",
                data=data,
                headers=headers
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
        """Convert Markdown to PDF via microservice"""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to GotenbergMicroserviceClient.")
        
        try:
            headers = self._get_auth_headers(tenant_id)
            
            data = {
                'markdown_content': markdown_content,
                'landscape': str(options.get('landscape', False)).lower(),
                'margin_top': str(options.get('margin_top', '1')),
                'margin_bottom': str(options.get('margin_bottom', '1')),
                'margin_left': str(options.get('margin_left', '1')),
                'margin_right': str(options.get('margin_right', '1')),
            }
            
            if css_content:
                data['css_content'] = css_content
            
            response = await self.http_client.post(
                f"{self.base_url}/convert/markdown-to-pdf",
                data=data,
                headers=headers
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
        """Convert plain text to PDF via microservice"""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to GotenbergMicroserviceClient.")
        
        try:
            headers = self._get_auth_headers(tenant_id)
            
            data = {
                'text_content': text_content,
                'landscape': str(options.get('landscape', False)).lower(),
                'margin_top': str(options.get('margin_top', '1')),
                'margin_bottom': str(options.get('margin_bottom', '1')),
                'margin_left': str(options.get('margin_left', '1')),
                'margin_right': str(options.get('margin_right', '1')),
            }
            
            if title:
                data['title'] = title
            
            response = await self.http_client.post(
                f"{self.base_url}/convert/text-to-pdf",
                data=data,
                headers=headers
            )
            
            response.raise_for_status()
            return response.content
            
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
        """Generate thumbnails from PDF via microservice"""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to GotenbergMicroserviceClient.")
        
        try:
            headers = self._get_auth_headers(tenant_id)
            
            files = {
                'file': (filename, pdf_content, 'application/pdf')
            }
            
            data = {
                'max_pages': str(max_pages)
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/thumbnails/generate-from-pdf",
                files=files,
                data=data,
                headers=headers
            )
            
            response.raise_for_status()
            result = response.json()
            return result.get('thumbnails', [])
            
        except Exception as e:
            logger.error(f"PDF thumbnails generation error: {e}")
            return []

    async def generate_image_thumbnail(
        self, 
        image_content: bytes, 
        filename: str,
        tenant_id: str = None
    ) -> Optional[str]:
        """Generate thumbnail from image via microservice"""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to GotenbergMicroserviceClient.")
        
        try:
            headers = self._get_auth_headers(tenant_id)
            
            files = {
                'file': (filename, image_content, self._get_image_mime_type(filename))
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/thumbnails/generate-from-image",
                files=files,
                headers=headers
            )
            
            response.raise_for_status()
            result = response.json()
            return result.get('thumbnail')
            
        except Exception as e:
            logger.error(f"Image thumbnail generation error: {e}")
            return None

    async def get_supported_formats(self, tenant_id: str = None) -> Dict[str, list]:
        """Get supported formats via microservice"""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to GotenbergMicroserviceClient.")
        
        try:
            headers = self._get_auth_headers(tenant_id)
            
            response = await self.http_client.get(
                f"{self.base_url}/formats/supported",
                headers=headers
            )
            
            response.raise_for_status()
            result = response.json()
            return result.get('formats', {})
            
        except Exception as e:
            logger.error(f"Get supported formats error: {e}")
            return {}

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