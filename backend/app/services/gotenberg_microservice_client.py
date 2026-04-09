"""
Gotenberg Microservice Client

Provides PDF conversion capabilities via Gotenberg service:
- Office documents (DOCX, XLSX, PPTX) to PDF
- HTML/Markdown to PDF
- Text to PDF
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.clients.base import BaseHTTPClient
from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ConversionResult:
    """Result from a document conversion."""
    content: bytes
    source_format: str
    pages: Optional[int] = None


class GotenbergClient(BaseHTTPClient):
    """
    HTTP client for Gotenberg PDF conversion service.

    Gotenberg provides document conversion via LibreOffice (office docs)
    and Chromium (HTML/Markdown) engines.

    Example:
        client = GotenbergClient(user_id="u1")
        pdf_bytes = await client.convert_office_to_pdf(
            file_content=docx_bytes,
            filename="document.docx"
        )
    """

    # MIME type mappings for office documents
    OFFICE_MIME_TYPES: Dict[str, str] = {
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

    IMAGE_MIME_TYPES: Dict[str, str] = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.tiff': 'image/tiff',
    }

    SUPPORTED_FORMATS: Dict[str, List[str]] = {
        'office': ['.docx', '.doc', '.odt', '.xlsx', '.xls', '.ods', '.pptx', '.ppt', '.odp', '.rtf'],
        'text': ['.html', '.htm', '.md', '.txt'],
        'images': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'],
        'pdf': ['.pdf']
    }

    def __init__(
        self,
        user_id: Optional[str] = None
    ) -> None:
        """
        Initialize Gotenberg client.

        Args:
            user_id: User ID for context propagation
        """
        self.gotenberg_url = (settings.GOTENBERG_BASE_URL or "").rstrip("/")
        if not self.gotenberg_url:
            raise ValueError("GOTENBERG_BASE_URL is not configured")

        self.user_id = user_id

        super().__init__(
            service_name="gotenberg",
            base_url=self.gotenberg_url,
            timeout_type="document",  # 60s read timeout for document conversion
        )

    def _get_mime_type(self, filename: str) -> str:
        """Determine MIME type based on file extension."""
        ext = Path(filename).suffix.lower()
        return (
            self.OFFICE_MIME_TYPES.get(ext) or
            self.IMAGE_MIME_TYPES.get(ext) or
            'application/octet-stream'
        )

    async def health_check(self) -> Dict[str, Any]:
        """
        Check Gotenberg service health.

        Returns:
            Dict with status information
        """
        try:
            response = await self.get("/health")
            return {"status": "healthy", "service": self.service_name}
        except Exception as e:
            logger.warning(f"Gotenberg health check failed: {e}")
            return {"status": "unhealthy", "service": self.service_name, "error": str(e)}

    async def convert_office_to_pdf(
        self,
        file_content: Optional[bytes] = None,
        file_path: Optional[str] = None,
        filename: Optional[str] = None,
        landscape: bool = False,
        margin_top: str = "0.5",
        margin_bottom: str = "0.5",
        margin_left: str = "0.5",
        margin_right: str = "0.5",
    ) -> bytes:
        """
        Convert Office documents to PDF using Gotenberg LibreOffice route.

        Args:
            file_content: File content as bytes
            file_path: Path to file (alternative to file_content)
            filename: Filename for MIME type detection
            landscape: Use landscape orientation
            margin_top/bottom/left/right: Page margins

        Returns:
            PDF content as bytes

        Raises:
            ValueError: If neither file_content nor file_path provided
        """
        # Handle both file_path and file_content inputs
        if file_path and not file_content:
            with open(file_path, 'rb') as f:
                file_content = f.read()
            if not filename:
                filename = Path(file_path).name
        elif not file_content:
            raise ValueError("Either file_content or file_path must be provided")

        if not filename:
            filename = "document.docx"

        files = {
            'files': (filename, file_content, self._get_mime_type(filename))
        }

        # Gotenberg form parameters
        data = {
            'landscape': str(landscape).lower(),
            'marginTop': margin_top,
            'marginBottom': margin_bottom,
            'marginLeft': margin_left,
            'marginRight': margin_right,
        }

        response = await self.request(
            "POST",
            "/forms/libreoffice/convert",
            user_id=self.user_id,
            files=files,
            data=data,
        )

        logger.debug(f"Converted {filename} to PDF ({len(response.content)} bytes)")
        return response.content

    async def convert_html_to_pdf(
        self,
        html_content: str,
        css_content: Optional[str] = None,
        landscape: bool = False,
        margin_top: str = "1",
        margin_bottom: str = "1",
        margin_left: str = "1",
        margin_right: str = "1",
        scale: str = "1",
    ) -> bytes:
        """
        Convert HTML to PDF using Gotenberg Chromium route.

        Args:
            html_content: HTML content as string
            css_content: Optional CSS content
            landscape: Use landscape orientation
            margin_top/bottom/left/right: Page margins (in inches)
            scale: Page scale factor

        Returns:
            PDF content as bytes
        """
        # Prepare files
        if css_content:
            # Multiple files for HTML + CSS
            files = [
                ('files', ('index.html', html_content.encode('utf-8'), 'text/html')),
                ('files', ('style.css', css_content.encode('utf-8'), 'text/css')),
            ]
        else:
            files = {
                'files': ('index.html', html_content.encode('utf-8'), 'text/html')
            }

        data = {
            'landscape': str(landscape).lower(),
            'marginTop': margin_top,
            'marginBottom': margin_bottom,
            'marginLeft': margin_left,
            'marginRight': margin_right,
            'scale': scale,
        }

        response = await self.request(
            "POST",
            "/forms/chromium/convert/html",
            user_id=self.user_id,
            files=files,
            data=data,
        )

        logger.debug(f"Converted HTML to PDF ({len(response.content)} bytes)")
        return response.content

    async def convert_markdown_to_pdf(
        self,
        markdown_content: str,
        css_content: Optional[str] = None,
        landscape: bool = False,
        margin_top: str = "1",
        margin_bottom: str = "1",
        margin_left: str = "1",
        margin_right: str = "1",
    ) -> bytes:
        """
        Convert Markdown to PDF using Gotenberg Chromium markdown route.

        Args:
            markdown_content: Markdown content as string
            css_content: Optional CSS content for styling
            landscape: Use landscape orientation
            margin_top/bottom/left/right: Page margins (in inches)

        Returns:
            PDF content as bytes
        """
        # Prepare files
        if css_content:
            files = [
                ('files', ('index.md', markdown_content.encode('utf-8'), 'text/markdown')),
                ('files', ('style.css', css_content.encode('utf-8'), 'text/css')),
            ]
        else:
            files = {
                'files': ('index.md', markdown_content.encode('utf-8'), 'text/markdown')
            }

        data = {
            'landscape': str(landscape).lower(),
            'marginTop': margin_top,
            'marginBottom': margin_bottom,
            'marginLeft': margin_left,
            'marginRight': margin_right,
        }

        response = await self.request(
            "POST",
            "/forms/chromium/convert/markdown",
            user_id=self.user_id,
            files=files,
            data=data,
        )

        logger.debug(f"Converted Markdown to PDF ({len(response.content)} bytes)")
        return response.content

    async def convert_text_to_pdf(
        self,
        text_content: str,
        title: Optional[str] = None,
        landscape: bool = False,
        margin_top: str = "1",
        margin_bottom: str = "1",
        margin_left: str = "1",
        margin_right: str = "1",
    ) -> bytes:
        """
        Convert plain text to PDF by wrapping in HTML.

        Args:
            text_content: Plain text content
            title: Optional document title
            landscape: Use landscape orientation
            margin_top/bottom/left/right: Page margins

        Returns:
            PDF content as bytes
        """
        # Wrap text content in basic HTML for proper rendering
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

        return await self.convert_html_to_pdf(
            html_content=html_content,
            landscape=landscape,
            margin_top=margin_top,
            margin_bottom=margin_bottom,
            margin_left=margin_left,
            margin_right=margin_right,
        )

    def get_supported_formats(self) -> Dict[str, List[str]]:
        """
        Get supported file formats for conversion.

        Returns:
            Dict mapping category to list of extensions
        """
        return self.SUPPORTED_FORMATS.copy()


# Backward compatibility alias
GotenbergMicroserviceClient = GotenbergClient
