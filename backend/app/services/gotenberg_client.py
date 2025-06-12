"""
Gotenberg Client for Document Conversion
Open source document conversion service
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

class GotenbergClient:
    """Cliente para Gotenberg - Servicio de conversión de documentos"""
    
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or settings.GOTENBERG_SERVICE_URL
        self.timeout = 120.0  # 2 minutos timeout
        
    async def health_check(self) -> bool:
        """Verificar si Gotenberg está disponible"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Gotenberg health check failed: {e}")
            return False
    
    async def convert_office_to_pdf(
        self, 
        file_path: str, 
        filename: str,
        **options
    ) -> bytes:
        """
        Convierte documentos Office a PDF
        
        Args:
            file_path: Ruta al archivo
            filename: Nombre original del archivo
            options: Opciones adicionales (landscape, margins, etc.)
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                with open(file_path, 'rb') as file:
                    files = {
                        'files': (filename, file, self._get_mime_type(filename))
                    }
                    
                    # Opciones de conversión
                    data = {
                        'landscape': str(options.get('landscape', False)).lower(),
                        'marginTop': str(options.get('margin_top', '0.5')),
                        'marginBottom': str(options.get('margin_bottom', '0.5')),
                        'marginLeft': str(options.get('margin_left', '0.5')),
                        'marginRight': str(options.get('margin_right', '0.5')),
                    }
                    
                    response = await client.post(
                        f"{self.base_url}/forms/libreoffice/convert",
                        files=files,
                        data=data
                    )
                    
                    response.raise_for_status()
                    return response.content
                    
        except httpx.HTTPError as e:
            logger.error(f"Gotenberg HTTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"Gotenberg conversion error: {e}")
            raise
    
    async def convert_html_to_pdf(
        self, 
        html_content: str, 
        css_content: Optional[str] = None,
        **options
    ) -> bytes:
        """Convierte HTML a PDF"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                files = {}
                
                # Archivo HTML principal
                files['files'] = ('index.html', html_content.encode(), 'text/html')
                
                # Si hay CSS, agregarlo como archivo adicional
                if css_content:
                    # Para múltiples archivos, usar lista de tuplas
                    files = {
                        'files': [
                            ('index.html', html_content.encode(), 'text/html'),
                            ('style.css', css_content.encode(), 'text/css')
                        ]
                    }
                
                data = {
                    'landscape': str(options.get('landscape', False)).lower(),
                    'marginTop': str(options.get('margin_top', '1')),
                    'marginBottom': str(options.get('margin_bottom', '1')),
                    'marginLeft': str(options.get('margin_left', '1')),
                    'marginRight': str(options.get('margin_right', '1')),
                    'scale': str(options.get('scale', '1')),
                }
                
                response = await client.post(
                    f"{self.base_url}/forms/chromium/convert/html",
                    files=files,
                    data=data
                )
                
                response.raise_for_status()
                return response.content
                
        except Exception as e:
            logger.error(f"HTML to PDF conversion error: {e}")
            raise
    
    async def convert_url_to_pdf(self, url: str, **options) -> bytes:
        """Convierte una URL a PDF"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                data = {
                    'url': url,
                    'landscape': str(options.get('landscape', False)).lower(),
                    'marginTop': str(options.get('margin_top', '1')),
                    'marginBottom': str(options.get('margin_bottom', '1')),
                    'marginLeft': str(options.get('margin_left', '1')),
                    'marginRight': str(options.get('margin_right', '1')),
                    'scale': str(options.get('scale', '1')),
                    'waitDelay': options.get('wait_delay', '1s'),
                }
                
                response = await client.post(
                    f"{self.base_url}/forms/chromium/convert/url",
                    data=data
                )
                
                response.raise_for_status()
                return response.content
                
        except Exception as e:
            logger.error(f"URL to PDF conversion error: {e}")
            raise
    
    async def convert_markdown_to_pdf(
        self, 
        markdown_content: str, 
        css_content: Optional[str] = None,
        **options
    ) -> bytes:
        """Convierte Markdown a PDF"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                files = {}
                
                # Archivo Markdown principal
                files['files'] = ('index.md', markdown_content.encode(), 'text/markdown')
                
                # Si hay CSS, agregarlo
                if css_content:
                    files = {
                        'files': [
                            ('index.md', markdown_content.encode(), 'text/markdown'),
                            ('style.css', css_content.encode(), 'text/css')
                        ]
                    }
                
                data = {
                    'landscape': str(options.get('landscape', False)).lower(),
                    'marginTop': str(options.get('margin_top', '1')),
                    'marginBottom': str(options.get('margin_bottom', '1')),
                    'marginLeft': str(options.get('margin_left', '1')),
                    'marginRight': str(options.get('margin_right', '1')),
                }
                
                response = await client.post(
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
        **options
    ) -> bytes:
        """Convierte texto plano a PDF usando HTML"""
        try:
            # Crear HTML básico para el texto
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>{title or 'Document'}</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        max-width: 800px;
                        margin: 0 auto;
                        padding: 20px;
                        font-size: 12pt;
                    }}
                    h1 {{
                        color: #333;
                        border-bottom: 2px solid #333;
                        padding-bottom: 10px;
                    }}
                    pre {{
                        white-space: pre-wrap;
                        word-wrap: break-word;
                        background-color: #f9f9f9;
                        padding: 15px;
                        border-radius: 5px;
                        border: 1px solid #ddd;
                    }}
                </style>
            </head>
            <body>
                {f'<h1>{title}</h1>' if title else ''}
                <pre>{text_content}</pre>
            </body>
            </html>
            """
            
            return await self.convert_html_to_pdf(html_content, **options)
            
        except Exception as e:
            logger.error(f"Text to PDF conversion error: {e}")
            raise
    
    def _get_mime_type(self, filename: str) -> str:
        """Determina el MIME type basado en la extensión"""
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
    
    def get_supported_formats(self) -> Dict[str, list]:
        """Retorna los formatos soportados por categoría"""
        return {
            "office": ['.docx', '.doc', '.odt', '.rtf', '.xlsx', '.xls', '.ods', '.pptx', '.ppt', '.odp'],
            "text": ['.txt', '.md', '.html', '.htm'],
            "already_pdf": ['.pdf'],
            "images": ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']
        }
    
    def is_supported_format(self, filename: str) -> bool:
        """Verifica si el formato es soportado para conversión"""
        ext = Path(filename).suffix.lower()
        all_formats = []
        for format_list in self.get_supported_formats().values():
            all_formats.extend(format_list)
        return ext in all_formats