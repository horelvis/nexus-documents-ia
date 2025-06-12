"""
Document Conversion Service using Gotenberg
"""
import httpx
import asyncio
import logging
import tempfile
import os
from typing import Optional, Dict, Any, BinaryIO
from pathlib import Path
from PIL import Image
import io
import base64

from app.core.config import settings

logger = logging.getLogger(__name__)

class ConversionService:
    """Service for document conversion using Gotenberg"""
    
    def __init__(self):
        self.gotenberg_url = settings.GOTENBERG_BASE_URL
        self.timeout = settings.PDF_CONVERSION_TIMEOUT
        
    async def health_check(self) -> bool:
        """Check if Gotenberg is available"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.gotenberg_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Gotenberg health check failed: {e}")
            return False
    
    async def convert_office_to_pdf(
        self, 
        file_content: bytes, 
        filename: str,
        **options
    ) -> bytes:
        """Convert Office documents to PDF"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                files = {
                    'files': (filename, file_content, self._get_mime_type(filename))
                }
                
                # Conversion options
                data = {
                    'landscape': str(options.get('landscape', False)).lower(),
                    'marginTop': str(options.get('margin_top', '0.5')),
                    'marginBottom': str(options.get('margin_bottom', '0.5')),
                    'marginLeft': str(options.get('margin_left', '0.5')),
                    'marginRight': str(options.get('margin_right', '0.5')),
                }
                
                response = await client.post(
                    f"{self.gotenberg_url}/forms/libreoffice/convert",
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
        """Convert HTML to PDF"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                files = {}
                
                # Main HTML file
                files['files'] = ('index.html', html_content.encode(), 'text/html')
                
                # Add CSS if provided
                if css_content:
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
                    f"{self.gotenberg_url}/forms/chromium/convert/html",
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
        **options
    ) -> bytes:
        """Convert Markdown to PDF"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                files = {}
                
                # Main Markdown file
                files['files'] = ('index.md', markdown_content.encode(), 'text/markdown')
                
                # Add CSS if provided
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
                    f"{self.gotenberg_url}/forms/chromium/convert/markdown",
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
        """Convert plain text to PDF using HTML"""
        try:
            # Create basic HTML for text
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
    
    def generate_thumbnail_from_pdf(
        self, 
        pdf_content: bytes, 
        page_number: int = 0
    ) -> Optional[str]:
        """Generate thumbnail from PDF page"""
        try:
            import pdf2image
            
            # Convert PDF to images
            images = pdf2image.convert_from_bytes(
                pdf_content,
                first_page=page_number + 1,
                last_page=page_number + 1,
                dpi=150
            )
            
            if not images:
                return None
            
            # Resize image to thumbnail size
            image = images[0]
            image.thumbnail((settings.THUMBNAIL_WIDTH, settings.THUMBNAIL_HEIGHT), Image.Resampling.LANCZOS)
            
            # Convert to base64
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=settings.THUMBNAIL_QUALITY)
            image_data = base64.b64encode(buffer.getvalue()).decode()
            
            return f"data:image/jpeg;base64,{image_data}"
            
        except Exception as e:
            logger.error(f"Thumbnail generation error: {e}")
            return None
    
    def generate_thumbnails_from_pdf(
        self, 
        pdf_content: bytes, 
        max_pages: int = 5
    ) -> list:
        """Generate thumbnails from multiple PDF pages"""
        try:
            import pdf2image
            
            # Convert PDF to images
            images = pdf2image.convert_from_bytes(
                pdf_content,
                last_page=max_pages,
                dpi=150
            )
            
            thumbnails = []
            for i, image in enumerate(images):
                # Resize image to thumbnail size
                image.thumbnail((settings.THUMBNAIL_WIDTH, settings.THUMBNAIL_HEIGHT), Image.Resampling.LANCZOS)
                
                # Convert to base64
                buffer = io.BytesIO()
                image.save(buffer, format='JPEG', quality=settings.THUMBNAIL_QUALITY)
                image_data = base64.b64encode(buffer.getvalue()).decode()
                
                thumbnails.append(f"data:image/jpeg;base64,{image_data}")
            
            return thumbnails
            
        except Exception as e:
            logger.error(f"Multiple thumbnails generation error: {e}")
            return []
    
    def generate_image_thumbnail(
        self, 
        image_content: bytes, 
        mime_type: str
    ) -> Optional[str]:
        """Generate thumbnail from image"""
        try:
            # Open image
            image = Image.open(io.BytesIO(image_content))
            
            # Convert to RGB if necessary
            if image.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            
            # Resize to thumbnail size
            image.thumbnail((settings.THUMBNAIL_WIDTH, settings.THUMBNAIL_HEIGHT), Image.Resampling.LANCZOS)
            
            # Convert to base64
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=settings.THUMBNAIL_QUALITY)
            image_data = base64.b64encode(buffer.getvalue()).decode()
            
            return f"data:image/jpeg;base64,{image_data}"
            
        except Exception as e:
            logger.error(f"Image thumbnail generation error: {e}")
            return None
    
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
    
    def get_supported_formats(self) -> Dict[str, list]:
        """Return supported formats by category"""
        return {
            "office": ['.docx', '.doc', '.odt', '.rtf', '.xlsx', '.xls', '.ods', '.pptx', '.ppt', '.odp'],
            "text": ['.txt', '.md', '.html', '.htm'],
            "already_pdf": ['.pdf'],
            "images": ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']
        }
    
    def is_supported_format(self, filename: str) -> bool:
        """Check if format is supported for conversion"""
        ext = Path(filename).suffix.lower()
        all_formats = []
        for format_list in self.get_supported_formats().values():
            all_formats.extend(format_list)
        return ext in all_formats