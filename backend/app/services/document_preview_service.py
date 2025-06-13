"""
Advanced Document Preview Service using Gotenberg
Provides universal document preview generation with fallback support
"""
import asyncio
import tempfile
import os
from pathlib import Path
from typing import Dict, Optional, List, Tuple
import logging
import hashlib
import time

from app.services.gotenberg_microservice_client import GotenbergMicroserviceClient
from app.services.storage_service import StorageService
from app.core.config import settings

logger = logging.getLogger(__name__)

class DocumentPreviewService:
    """Servicio de preview usando Gotenberg como motor principal"""
    
    def __init__(self, tenant_id: str, user_id: Optional[str] = None, http_client = None):
        self.tenant_id = tenant_id
        self.user_id = user_id
        
        # Track if we own the HTTP client for cleanup
        self._owns_http_client = http_client is None
        
        # Always create Gotenberg client with a default HTTP client if none provided
        if http_client is None:
            import httpx
            http_client = httpx.AsyncClient(timeout=30.0)
        
        self._http_client = http_client
        self.gotenberg = GotenbergMicroserviceClient(http_client, tenant_id, user_id)
        self.storage_service = StorageService(tenant_id, user_id)
        self.temp_dir = Path(tempfile.gettempdir()) / "previews" / tenant_id
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache directory for previews in storage
        self.preview_storage_prefix = f"previews/{tenant_id}"
        
        # Formatos soportados por categoría
        self.supported_formats = {
            'office': {'.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.odt', '.ods', '.odp'},
            'text': {'.txt', '.md', '.html', '.htm'},
            'images': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
        }
        
        logger.info(f"DocumentPreviewService initialized for tenant: {tenant_id}")
    
    async def generate_preview(
        self, 
        document_id: str, 
        file_path: str, 
        filename: str,
        force_regenerate: bool = False
    ) -> Dict:
        """
        Genera preview de documento usando Gotenberg
        
        Args:
            document_id: ID único del documento
            file_path: Ruta al archivo local
            filename: Nombre original del archivo
            force_regenerate: Forzar regeneración aunque exista cache
            
        Returns:
            Dict con información del preview generado
        """
        file_ext = Path(filename).suffix.lower()
        
        try:
            # Verificar cache existente
            if not force_regenerate:
                cached_preview = await self._get_cached_preview(document_id, filename)
                if cached_preview:
                    logger.info(f"Using cached preview for document {document_id}")
                    return cached_preview
            
            # Procesar según el tipo de archivo
            if file_ext == '.pdf':
                return await self._preview_existing_pdf(document_id, file_path, filename)
            
            # Verificar si Gotenberg está disponible para otros formatos
            if not await self.gotenberg.health_check():
                logger.warning("Gotenberg not available, using fallback")
                return await self._fallback_preview(file_path, filename)
            elif file_ext in self.supported_formats['office']:
                return await self._preview_office_with_gotenberg(
                    document_id, file_path, filename
                )
            elif file_ext in self.supported_formats['text']:
                return await self._preview_text_with_gotenberg(
                    document_id, file_path, filename
                )
            elif file_ext in self.supported_formats['images']:
                return await self._preview_image(document_id, file_path, filename)
            else:
                return await self._fallback_preview(file_path, filename)
                
        except Exception as e:
            logger.error(f"Preview generation failed for {filename}: {e}")
            return await self._fallback_preview(file_path, filename)
    
    async def _preview_office_with_gotenberg(
        self, 
        document_id: str, 
        file_path: str, 
        filename: str
    ) -> Dict:
        """Convierte documentos Office a PDF usando Gotenberg"""
        try:
            logger.info(f"Converting office document {filename} using Gotenberg")
            
            # Convertir a PDF
            pdf_content = await self.gotenberg.convert_office_to_pdf(
                file_path=file_path,
                filename=filename,
                margin_top='0.5',
                margin_bottom='0.5',
                margin_left='0.5',
                margin_right='0.5'
            )
            
            # Guardar PDF temporal
            pdf_name = f"{document_id}_preview.pdf"
            pdf_path = self.temp_dir / pdf_name
            
            with open(pdf_path, 'wb') as f:
                f.write(pdf_content)
            
            # Subir a storage para cache
            preview_storage_path = f"{self.preview_storage_prefix}/{document_id}/{pdf_name}"
            upload_success = self._upload_to_storage(str(pdf_path), preview_storage_path)
            
            # Generar thumbnails del PDF
            thumbnails = await self._generate_pdf_thumbnails(document_id, str(pdf_path))
            
            result = {
                "type": "office_preview",
                "conversion_method": "gotenberg",
                "pdf_available": True,
                "pdf_storage_path": preview_storage_path if upload_success else None,
                "pdf_local_path": str(pdf_path),
                "thumbnails": thumbnails,
                "original_format": Path(filename).suffix,
                "cached": upload_success,
                "generated_at": int(time.time()),
                "file_size": len(pdf_content)
            }
            
            # Cache metadata
            await self._cache_preview_metadata(document_id, filename, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Gotenberg office conversion failed: {e}")
            raise
    
    async def _preview_text_with_gotenberg(
        self, 
        document_id: str, 
        file_path: str, 
        filename: str
    ) -> Dict:
        """Convierte Markdown/HTML/TXT a PDF usando Gotenberg"""
        try:
            file_ext = Path(filename).suffix.lower()
            logger.info(f"Converting text document {filename} ({file_ext}) using Gotenberg")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if file_ext == '.md':
                # CSS para Markdown
                css_content = self._get_markdown_css()
                pdf_content = await self.gotenberg.convert_markdown_to_pdf(
                    markdown_content=content,
                    css_content=css_content,
                    margin_top='1',
                    margin_bottom='1'
                )
            elif file_ext in ['.html', '.htm']:
                pdf_content = await self.gotenberg.convert_html_to_pdf(
                    html_content=content,
                    margin_top='1',
                    margin_bottom='1'
                )
            else:  # .txt
                pdf_content = await self.gotenberg.convert_text_to_pdf(
                    text_content=content,
                    title=Path(filename).stem,
                    margin_top='1',
                    margin_bottom='1'
                )
            
            # Procesar PDF generado
            pdf_name = f"{document_id}_preview.pdf"
            pdf_path = self.temp_dir / pdf_name
            
            with open(pdf_path, 'wb') as f:
                f.write(pdf_content)
            
            # Subir a storage
            preview_storage_path = f"{self.preview_storage_prefix}/{document_id}/{pdf_name}"
            upload_success = self._upload_to_storage(str(pdf_path), preview_storage_path)
            
            # Generar thumbnails
            thumbnails = await self._generate_pdf_thumbnails(document_id, str(pdf_path))
            
            result = {
                "type": "text_preview",
                "conversion_method": "gotenberg",
                "pdf_available": True,
                "pdf_storage_path": preview_storage_path if upload_success else None,
                "pdf_local_path": str(pdf_path),
                "thumbnails": thumbnails,
                "original_format": file_ext,
                "cached": upload_success,
                "generated_at": int(time.time()),
                "file_size": len(pdf_content),
                "text_preview": content[:500] + "..." if len(content) > 500 else content
            }
            
            await self._cache_preview_metadata(document_id, filename, result)
            return result
            
        except Exception as e:
            logger.error(f"Gotenberg text conversion failed: {e}")
            raise
    
    async def _preview_existing_pdf(
        self,
        document_id: str,
        file_path: str,
        filename: str
    ) -> Dict:
        """Procesa PDF existente para generar thumbnails"""
        logger.info(f"Processing existing PDF {filename}")
        
        # Intentar generar thumbnails, pero no fallar si no se puede
        thumbnails = []
        try:
            thumbnails = await self._generate_pdf_thumbnails(document_id, file_path)
            logger.info(f"Generated {len(thumbnails)} thumbnails for PDF {filename}")
        except Exception as e:
            logger.warning(f"Could not generate thumbnails for PDF {filename}: {e}")
            # Continuar sin thumbnails
        
        # Obtener tamaño del archivo con fallback
        file_size = 0
        try:
            file_size = os.path.getsize(file_path)
        except Exception as e:
            logger.warning(f"Could not get file size for {file_path}: {e}")
        
        result = {
            "type": "pdf_preview",
            "conversion_method": "none",
            "pdf_available": True,
            "pdf_storage_path": None,  # El PDF original ya está en storage
            "pdf_local_path": file_path,
            "thumbnails": thumbnails,
            "original_format": ".pdf",
            "cached": False,
            "generated_at": int(time.time()),
            "file_size": file_size
        }
        
        # Intentar cache, pero no fallar si no se puede
        try:
            await self._cache_preview_metadata(document_id, filename, result)
        except Exception as e:
            logger.warning(f"Could not cache preview metadata for {filename}: {e}")
        
        return result
    
    async def _preview_image(
        self,
        document_id: str,
        file_path: str,
        filename: str
    ) -> Dict:
        """Preview para archivos de imagen"""
        try:
            logger.info(f"Processing image {filename}")
            
            # Usar PIL para redimensionar imagen
            try:
                from PIL import Image
                
                with Image.open(file_path) as img:
                    # Información original
                    original_size = img.size
                    original_format = img.format
                    
                    # Crear thumbnail
                    thumb_size = (300, 300)
                    img.thumbnail(thumb_size, Image.Resampling.LANCZOS)
                    
                    # Guardar thumbnail
                    thumb_name = f"{document_id}_thumb.jpg"
                    thumb_path = self.temp_dir / thumb_name
                    img.save(thumb_path, 'JPEG', quality=85)
                    
                    # Subir thumbnail a storage
                    thumb_storage_path = f"{self.preview_storage_prefix}/{document_id}/{thumb_name}"
                    upload_success = self._upload_to_storage(str(thumb_path), thumb_storage_path)
                    
                    result = {
                        "type": "image_preview",
                        "conversion_method": "pil",
                        "pdf_available": False,
                        "thumbnail_path": thumb_storage_path if upload_success else str(thumb_path),
                        "thumbnails": [str(thumb_path)],
                        "original_format": Path(filename).suffix,
                        "original_dimensions": original_size,
                        "original_image_format": original_format,
                        "cached": upload_success,
                        "generated_at": int(time.time()),
                        "file_size": os.path.getsize(file_path)
                    }
                    
                    await self._cache_preview_metadata(document_id, filename, result)
                    return result
                    
            except ImportError:
                logger.warning("PIL not available for image processing")
                return await self._fallback_preview(file_path, filename)
                
        except Exception as e:
            logger.error(f"Image preview failed: {e}")
            return await self._fallback_preview(file_path, filename)
    
    async def _generate_pdf_thumbnails(self, document_id: str, pdf_path: str) -> List[str]:
        """Genera thumbnails de PDF usando pdf2image"""
        try:
            from pdf2image import convert_from_path
            
            # Convertir solo las primeras 3 páginas
            pages = convert_from_path(
                pdf_path, 
                first_page=1, 
                last_page=3,
                dpi=150
            )
            
            thumbnails = []
            for i, page in enumerate(pages):
                thumb_name = f"{document_id}_thumb_{i}.jpg"
                thumb_path = self.temp_dir / thumb_name
                page.save(thumb_path, 'JPEG', quality=85)
                
                # Subir a storage
                thumb_storage_path = f"{self.preview_storage_prefix}/{document_id}/{thumb_name}"
                upload_success = self._upload_to_storage(str(thumb_path), thumb_storage_path)
                
                if upload_success:
                    thumbnails.append(thumb_storage_path)
                else:
                    thumbnails.append(str(thumb_path))
            
            return thumbnails
            
        except ImportError:
            logger.warning("pdf2image not available for thumbnail generation")
            return []
        except Exception as e:
            logger.error(f"Thumbnail generation failed: {e}")
            return []
    
    def _upload_to_storage(self, local_path: str, storage_path: str) -> bool:
        """Sube archivo al storage y retorna éxito/fallo"""
        try:
            # Leer archivo y subir como bytes
            with open(local_path, 'rb') as f:
                file_content = f.read()
            
            success = self.storage_service.upload_file(
                file=file_content,
                object_name=storage_path
            )
            if success:
                logger.debug(f"Uploaded {local_path} to {storage_path}")
            return success
        except Exception as e:
            logger.error(f"Storage upload failed: {e}")
            return False
    
    async def _cache_preview_metadata(self, document_id: str, filename: str, metadata: Dict):
        """Cache metadata del preview para reutilización"""
        try:
            # Guardar metadata como JSON en storage
            import json
            metadata_name = f"{document_id}_metadata.json"
            metadata_path = self.temp_dir / metadata_name
            
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            metadata_storage_path = f"{self.preview_storage_prefix}/{document_id}/{metadata_name}"
            self._upload_to_storage(str(metadata_path), metadata_storage_path)
            
        except Exception as e:
            logger.error(f"Preview metadata caching failed: {e}")
    
    async def _get_cached_preview(self, document_id: str, filename: str) -> Optional[Dict]:
        """Busca preview en cache"""
        try:
            # Buscar metadata en storage
            metadata_storage_path = f"{self.preview_storage_prefix}/{document_id}/{document_id}_metadata.json"
            
            # Intentar descargar metadata
            metadata_content = self.storage_service.download_file(metadata_storage_path)
            
            if metadata_content:
                import json
                metadata = json.loads(metadata_content.decode('utf-8'))
                
                # Verificar que el cache sigue válido (ej. menos de 24 horas)
                cache_age = time.time() - metadata.get('generated_at', 0)
                if cache_age < 86400:  # 24 horas
                    return metadata
            
            return None
            
        except Exception as e:
            logger.error(f"Cache retrieval failed: {e}")
            return None
    
    async def _fallback_preview(self, file_path: str, filename: str) -> Dict:
        """Fallback cuando Gotenberg no está disponible o el formato no es soportado"""
        file_ext = Path(filename).suffix.lower()
        file_size = os.path.getsize(file_path)
        
        # Para archivos de texto, intentar mostrar contenido
        if file_ext == '.txt':
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read(1000)  # Primeros 1000 caracteres
                
                return {
                    "type": "text_fallback",
                    "conversion_method": "fallback",
                    "pdf_available": False,
                    "text_preview": content,
                    "original_format": file_ext,
                    "file_size": file_size,
                    "message": "Text preview available"
                }
            except Exception:
                pass
        
        return {
            "type": "unsupported_fallback",
            "conversion_method": "fallback",
            "pdf_available": False,
            "message": f"Preview not available for {file_ext} files",
            "filename": filename,
            "original_format": file_ext,
            "file_size": file_size,
            "supported_formats": self.supported_formats
        }
    
    def _get_markdown_css(self) -> str:
        """CSS básico para renderizar Markdown"""
        return """
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px; 
            margin: 0 auto; 
            padding: 20px;
            line-height: 1.6;
            color: #333;
        }
        h1, h2, h3, h4, h5, h6 { 
            color: #2c3e50;
            margin-top: 1.5em;
            margin-bottom: 0.5em;
        }
        h1 { border-bottom: 2px solid #3498db; padding-bottom: 10px; }
        h2 { border-bottom: 1px solid #bdc3c7; padding-bottom: 5px; }
        code { 
            background-color: #f8f9fa; 
            padding: 2px 6px; 
            border-radius: 4px; 
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 0.9em;
        }
        pre { 
            background-color: #f8f9fa; 
            padding: 15px; 
            border-radius: 8px; 
            overflow-x: auto;
            border: 1px solid #e9ecef;
        }
        pre code {
            background: none;
            padding: 0;
        }
        blockquote {
            border-left: 4px solid #3498db;
            margin: 1em 0;
            padding-left: 1em;
            color: #666;
        }
        table {
            border-collapse: collapse;
            width: 100%;
            margin: 1em 0;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px 12px;
            text-align: left;
        }
        th {
            background-color: #f8f9fa;
            font-weight: 600;
        }
        a {
            color: #3498db;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
        """
    
    async def cleanup_temp_files(self, document_id: str):
        """Limpia archivos temporales de un documento específico"""
        try:
            pattern = f"{document_id}_*"
            for file_path in self.temp_dir.glob(pattern):
                file_path.unlink()
                logger.debug(f"Cleaned up temp file: {file_path}")
        except Exception as e:
            logger.error(f"Temp file cleanup failed: {e}")
    
    async def cleanup(self):
        """Cleanup resources including HTTP client if we own it"""
        try:
            if self._owns_http_client and hasattr(self, '_http_client'):
                await self._http_client.aclose()
                logger.debug("Closed HTTP client")
        except Exception as e:
            logger.error(f"HTTP client cleanup failed: {e}")
    
    async def get_preview_info(self, document_id: str) -> Optional[Dict]:
        """Obtiene información de preview existente sin regenerar"""
        return await self._get_cached_preview(document_id, "")