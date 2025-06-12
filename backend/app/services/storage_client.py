import httpx
import logging
import io
import mimetypes
from typing import Optional, Tuple, BinaryIO, Union, Dict, Any, List
from datetime import datetime
from fastapi import UploadFile, HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

class StorageClient:
    """Cliente para comunicarse con el storage microservice"""
    
    def __init__(self, tenant_id: str, user_id: Optional[str] = None, bucket_name: Optional[str] = None):
        """
        Inicializa el cliente de storage.
        
        Args:
            tenant_id: ID del tenant
            user_id: ID del usuario (opcional)
            bucket_name: Nombre del bucket (opcional, se obtiene del tenant si no se proporciona)
        """
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.base_url = getattr(settings, 'STORAGE_SERVICE_URL', 'http://storage-service:8001')
        self.api_key = getattr(settings, 'STORAGE_API_KEY', 'your-secret-api-key-here')
        
        # Headers comunes para todas las requests
        self.headers = {
            "X-API-Key": self.api_key,
            "X-Tenant-ID": self.tenant_id,
        }
        
        if self.user_id:
            self.headers["X-User-ID"] = self.user_id
            
        # Añadir bucket name si se proporciona
        if bucket_name:
            self.headers["X-Bucket-Name"] = bucket_name
    
    def _get_mimetype(self, filename: str, fallback: str = "application/octet-stream") -> str:
        """
        Detecta el mimetype basado en la extensión del archivo.
        
        Args:
            filename: Nombre del archivo
            fallback: Mimetype por defecto si no se puede detectar
            
        Returns:
            Mimetype detectado o fallback
        """
        # Mapeo manual para tipos comunes de documentos
        common_mimetypes = {
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.txt': 'text/plain',
            '.csv': 'text/csv',
            '.json': 'application/json',
            '.xml': 'application/xml',
            '.html': 'text/html',
            '.md': 'text/markdown',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.mp4': 'video/mp4',
            '.avi': 'video/x-msvideo',
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.zip': 'application/zip',
            '.rar': 'application/vnd.rar',
            '.7z': 'application/x-7z-compressed',
        }
        
        # Obtener extensión en minúsculas
        ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
        
        # Buscar en mapeo manual primero
        if ext in common_mimetypes:
            return common_mimetypes[ext]
        
        # Fallback a mimetypes estándar
        mimetype, _ = mimetypes.guess_type(filename)
        return mimetype or fallback
    
    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        **kwargs
    ) -> httpx.Response:
        """
        Realiza una request HTTP al storage service.
        
        Args:
            method: Método HTTP
            endpoint: Endpoint (sin base URL)
            **kwargs: Argumentos adicionales para httpx
            
        Returns:
            Response de httpx
        """
        url = f"{self.base_url}/api/v1/storage{endpoint}"
        
        # Merge headers
        request_headers = {**self.headers}
        if "headers" in kwargs:
            request_headers.update(kwargs["headers"])
            kwargs["headers"] = request_headers
        else:
            kwargs["headers"] = request_headers
        
        try:
            with httpx.Client(timeout=30.0) as client:  # Timeout suficiente para archivos grandes
                response = client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Storage service HTTP error: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Storage service error: {e.response.text}"
            )
        except (httpx.RequestError, httpx.TimeoutException, httpx.ConnectError) as e:
            logger.error(f"Storage service connection error: {e}")
            raise HTTPException(
                status_code=503,
                detail="Storage service unavailable"
            )
    
    def upload_file(
        self, 
        file: Union[UploadFile, BinaryIO, bytes], 
        filename: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Sube un archivo al storage.
        
        Args:
            file: Archivo a subir
            filename: Nombre del archivo
            metadata: Metadatos opcionales
            
        Returns:
            Información del archivo subido
        """
        try:
            # Detectar mimetype
            detected_mimetype = self._get_mimetype(filename)
            
            # Preparar archivo para upload
            if isinstance(file, bytes):
                files = {"file": (filename, io.BytesIO(file), detected_mimetype)}
            elif isinstance(file, UploadFile):
                content = file.file.read()
                file.file.seek(0)  # Reset para uso posterior
                # Usar mimetype del UploadFile si está disponible, sino el detectado
                mimetype = file.content_type or detected_mimetype
                files = {"file": (filename, io.BytesIO(content), mimetype)}
            else:
                file.seek(0)
                content = file.read()
                file.seek(0)  # Reset
                files = {"file": (filename, io.BytesIO(content), detected_mimetype)}
            
            # Preparar form data
            data = {}
            if metadata:
                import json
                data["metadata"] = json.dumps(metadata)
            
            response = self._make_request(
                "POST", 
                "/upload", 
                files=files,
                data=data
            )
            
            result = response.json()
            logger.info(f"File uploaded successfully: {filename}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to upload file {filename}: {e}")
            raise
    
    def download_file(self, file_path: str) -> Optional[bytes]:
        """
        Descarga un archivo del storage.
        
        Args:
            file_path: Path del archivo
            
        Returns:
            Contenido del archivo como bytes o None si no existe
        """
        try:
            response = self._make_request("GET", f"/download/{file_path}")
            
            logger.info(f"File downloaded successfully: {file_path}")
            return response.content
            
        except HTTPException as e:
            if e.status_code == 404:
                logger.warning(f"File not found: {file_path}")
                return None
            raise
        except Exception as e:
            logger.error(f"Failed to download file {file_path}: {e}")
            raise
    
    def delete_file(self, file_path: str) -> bool:
        """
        Elimina un archivo del storage.
        
        Args:
            file_path: Path del archivo
            
        Returns:
            True si se eliminó correctamente
        """
        try:
            response = self._make_request("DELETE", f"/delete/{file_path}")
            
            logger.info(f"File deleted successfully: {file_path}")
            return True
            
        except HTTPException as e:
            if e.status_code == 404:
                logger.warning(f"File not found for deletion: {file_path}")
                return False
            raise
        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            raise
    
    def get_file_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene información de un archivo.
        
        Args:
            file_path: Path del archivo
            
        Returns:
            Información del archivo o None si no existe
        """
        try:
            response = self._make_request("GET", f"/info/{file_path}")
            
            result = response.json()
            logger.info(f"File info retrieved: {file_path}")
            return result
            
        except HTTPException as e:
            if e.status_code == 404:
                return None
            raise
        except Exception as e:
            logger.error(f"Failed to get file info {file_path}: {e}")
            raise
    
    def list_files(self, prefix: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        """
        Lista archivos del tenant.
        
        Args:
            prefix: Prefijo para filtrar archivos
            limit: Límite de archivos
            
        Returns:
            Lista de información de archivos
        """
        try:
            params = {"prefix": prefix, "limit": limit}
            response = self._make_request("GET", "/list", params=params)
            
            result = response.json()
            files = result.get("files", [])
            
            logger.info(f"Listed {len(files)} files with prefix '{prefix}'")
            return files
            
        except Exception as e:
            logger.error(f"Failed to list files with prefix {prefix}: {e}")
            raise
    
    def generate_upload_signed_url(
        self, 
        filename: str, 
        content_type: str,
        expiration: Optional[int] = None
    ) -> Tuple[str, datetime]:
        """
        Genera una URL firmada para subir un archivo.
        
        Args:
            filename: Nombre del archivo
            content_type: Tipo de contenido MIME
            expiration: Tiempo de expiración en segundos
            
        Returns:
            Tuple con URL firmada y fecha de expiración
        """
        try:
            payload = {
                "filename": filename,
                "content_type": content_type
            }
            
            if expiration:
                payload["expiration"] = expiration
            
            response = self._make_request("POST", "/signed-url/upload", json=payload)
            
            result = response.json()
            url = result["url"]
            expires_at = datetime.fromisoformat(result["expires_at"])
            
            logger.info(f"Generated upload signed URL for: {filename}")
            return url, expires_at
            
        except Exception as e:
            logger.error(f"Failed to generate upload signed URL for {filename}: {e}")
            raise
    
    def generate_download_signed_url(
        self, 
        file_path: str,
        expiration: Optional[int] = None
    ) -> Tuple[str, datetime]:
        """
        Genera una URL firmada para descargar un archivo.
        
        Args:
            file_path: Path del archivo
            expiration: Tiempo de expiración en segundos
            
        Returns:
            Tuple con URL firmada y fecha de expiración
        """
        try:
            params = {}
            if expiration:
                params["expiration"] = expiration
            
            response = self._make_request(
                "POST", 
                f"/signed-url/download/{file_path}",
                params=params
            )
            
            result = response.json()
            url = result["url"]
            expires_at = datetime.fromisoformat(result["expires_at"])
            
            logger.info(f"Generated download signed URL for: {file_path}")
            return url, expires_at
            
        except Exception as e:
            logger.error(f"Failed to generate download signed URL for {file_path}: {e}")
            raise
    
    def cleanup_test_bucket(self) -> Dict[str, Any]:
        """
        Limpia el bucket de test. Solo para testing.
        
        Returns:
            Información sobre la limpieza
        """
        try:
            response = self._make_request("POST", "/cleanup")
            
            result = response.json()
            logger.info(f"Test bucket cleaned: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to cleanup test bucket: {e}")
            raise
    
    def health_check(self) -> Dict[str, Any]:
        """
        Verifica el estado del storage service.
        
        Returns:
            Estado del servicio
        """
        try:
            response = self._make_request("GET", "/health")
            return response.json()
        except Exception as e:
            logger.error(f"Storage service health check failed: {e}")
            raise