import io
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, BinaryIO, Union, Dict, Any, List

from google.cloud import storage
from google.oauth2 import service_account
from fastapi import UploadFile, HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

class GCSService:
    """Servicio para gestión de Google Cloud Storage"""
    
    def __init__(self, bucket_name: str):
        """
        Inicializa el servicio GCS para un bucket específico.
        
        Args:
            bucket_name: Nombre del bucket a usar
        """
        self.bucket_name = bucket_name
        self._init_client()
        self._ensure_bucket_exists()
    
    def _init_client(self):
        """Inicializa el cliente de GCS"""
        try:
            # Siempre usar GCS real - verificar si hay credenciales configuradas
            if settings.GCS_CREDENTIALS and settings.GCS_CREDENTIALS.strip():
                # Usar credenciales explícitas para producción
                if settings.GCS_CREDENTIALS.startswith("/"):
                    # Es un path a archivo
                    credentials = service_account.Credentials.from_service_account_file(
                        settings.GCS_CREDENTIALS
                    )
                else:
                    # Es JSON directo
                    import json
                    creds_info = json.loads(settings.GCS_CREDENTIALS)
                    credentials = service_account.Credentials.from_service_account_info(creds_info)
                
                self.client = storage.Client(
                    credentials=credentials,
                    project=settings.GCS_PROJECT_ID
                )
            else:
                # Usar credenciales por defecto del entorno (ADC)
                logger.info("Using Application Default Credentials")
                self.client = storage.Client(project=settings.GCS_PROJECT_ID)
            
            logger.info("GCS client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize GCS client: {e}")
            raise HTTPException(
                status_code=500,
                detail="Storage service unavailable"
            )
    
    def _ensure_bucket_exists(self):
        """Asegura que el bucket exista, creándolo si es necesario"""
        try:
            self.bucket = self.client.get_bucket(self.bucket_name)
            logger.info(f"Bucket {self.bucket_name} found")
        except Exception:
            try:
                logger.info(f"Creating bucket {self.bucket_name}")
                self.bucket = self.client.create_bucket(
                    self.bucket_name,
                    location="europe-west1"
                )
                logger.info(f"Bucket {self.bucket_name} created successfully")
            except Exception as e:
                logger.error(f"Failed to create bucket {self.bucket_name}: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to setup storage bucket"
                )
    
    def upload_file(
        self,
        file: Union[UploadFile, BinaryIO, bytes],
        object_name: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Sube un archivo al bucket.
        
        Args:
            file: Archivo a subir
            object_name: Nombre del objeto en el bucket
            metadata: Metadatos opcionales
            
        Returns:
            Información del archivo subido
        """
        try:
            blob = self.bucket.blob(object_name)
            
            # Añadir metadatos si existen
            if metadata:
                blob.metadata = metadata
            
            # Procesar diferentes tipos de entrada
            if isinstance(file, bytes):
                file_obj = io.BytesIO(file)
                file_size = len(file)
            elif isinstance(file, UploadFile):
                content = file.file.read()
                file_obj = io.BytesIO(content)
                file_size = len(content)
                file.file.seek(0)  # Reset para uso posterior si es necesario
            else:
                file_obj = file
                file_obj.seek(0, 2)  # Ir al final para obtener tamaño
                file_size = file_obj.tell()
                file_obj.seek(0)  # Volver al inicio
            
            # Subir el archivo
            blob.upload_from_file(file_obj, rewind=True)
            
            logger.info(f"File uploaded successfully: {object_name} ({file_size} bytes)")
            
            return {
                "object_name": object_name,
                "size": file_size,
                "bucket": self.bucket_name,
                "uploaded_at": datetime.utcnow().isoformat(),
                "metadata": metadata or {}
            }
            
        except Exception as e:
            logger.error(f"Failed to upload file {object_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload file: {str(e)}"
            )
    
    def download_file(self, object_name: str) -> Optional[bytes]:
        """
        Descarga un archivo del bucket.
        
        Args:
            object_name: Nombre del objeto a descargar
            
        Returns:
            Contenido del archivo como bytes o None si no existe
        """
        try:
            blob = self.bucket.blob(object_name)
            
            if not blob.exists():
                logger.warning(f"File not found: {object_name}")
                return None
            
            content = blob.download_as_bytes()
            logger.info(f"File downloaded successfully: {object_name}")
            return content
            
        except Exception as e:
            logger.error(f"Failed to download file {object_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to download file: {str(e)}"
            )
    
    def delete_file(self, object_name: str) -> bool:
        """
        Elimina un archivo del bucket.
        
        Args:
            object_name: Nombre del objeto a eliminar
            
        Returns:
            True si se eliminó correctamente
        """
        try:
            blob = self.bucket.blob(object_name)
            
            if not blob.exists():
                logger.warning(f"File not found for deletion: {object_name}")
                raise HTTPException(
                    status_code=404,
                    detail="File not found"
                )
            
            blob.delete()
            logger.info(f"File deleted successfully: {object_name}")
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete file {object_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete file: {str(e)}"
            )
    
    def file_exists(self, object_name: str) -> bool:
        """
        Verifica si un archivo existe en el bucket.
        
        Args:
            object_name: Nombre del objeto a verificar
            
        Returns:
            True si existe, False si no
        """
        try:
            blob = self.bucket.blob(object_name)
            return blob.exists()
        except Exception as e:
            logger.error(f"Failed to check file existence {object_name}: {e}")
            return False
    
    def get_file_info(self, object_name: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene información de un archivo.
        
        Args:
            object_name: Nombre del objeto
            
        Returns:
            Información del archivo o None si no existe
        """
        try:
            blob = self.bucket.blob(object_name)
            
            if not blob.exists():
                return None
            
            # Refrescar para obtener metadatos actuales
            blob.reload()
            
            return {
                "name": blob.name,
                "size": blob.size,
                "content_type": blob.content_type,
                "created": blob.time_created.isoformat() if blob.time_created else None,
                "updated": blob.updated.isoformat() if blob.updated else None,
                "metadata": blob.metadata or {}
            }
            
        except Exception as e:
            logger.error(f"Failed to get file info {object_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get file info: {str(e)}"
            )
    
    def list_files(self, prefix: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        """
        Lista archivos en el bucket.
        
        Args:
            prefix: Prefijo para filtrar archivos
            limit: Límite de archivos a retornar
            
        Returns:
            Lista de información de archivos
        """
        try:
            blobs = self.bucket.list_blobs(prefix=prefix, max_results=limit)
            
            files = []
            for blob in blobs:
                files.append({
                    "name": blob.name,
                    "size": blob.size,
                    "content_type": blob.content_type,
                    "created": blob.time_created.isoformat() if blob.time_created else None,
                    "updated": blob.updated.isoformat() if blob.updated else None,
                    "metadata": blob.metadata or {}
                })
            
            logger.info(f"Listed {len(files)} files with prefix '{prefix}'")
            return files
            
        except Exception as e:
            logger.error(f"Failed to list files with prefix {prefix}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list files: {str(e)}"
            )
    
    def generate_signed_url(
        self,
        object_name: str,
        method: str = "GET",
        expiration: Optional[int] = None,
        content_type: Optional[str] = None
    ) -> Tuple[str, datetime]:
        """
        Genera una URL firmada para el objeto.
        
        Args:
            object_name: Nombre del objeto
            method: Método HTTP (GET, PUT, etc.)
            expiration: Tiempo de expiración en segundos
            content_type: Tipo de contenido (para PUT)
            
        Returns:
            Tuple con URL firmada y fecha de expiración
        """
        try:
            expiration_seconds = expiration or settings.SIGNED_URL_EXPIRATION
            expires_at = datetime.utcnow() + timedelta(seconds=expiration_seconds)
            
            blob = self.bucket.blob(object_name)
            
            url_params = {
                "version": "v4",
                "expiration": timedelta(seconds=expiration_seconds),
                "method": method,
            }
            
            if content_type and method.upper() == "PUT":
                url_params["content_type"] = content_type
            
            url = blob.generate_signed_url(**url_params)
            
            logger.info(f"Generated signed URL for {object_name} (method: {method})")
            return url, expires_at
            
        except Exception as e:
            logger.error(f"Failed to generate signed URL for {object_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate signed URL: {str(e)}"
            )
    
    def cleanup_bucket(self) -> Dict[str, Any]:
        """
        Limpia todos los archivos del bucket (solo para testing).
        
        Returns:
            Información sobre la limpieza
        """
        if not settings.TESTING or not self.bucket_name.endswith("-test"):
            raise HTTPException(
                status_code=403,
                detail="Bucket cleanup only allowed in testing mode with test buckets"
            )
        
        try:
            blobs = list(self.bucket.list_blobs())
            
            if not blobs:
                return {
                    "message": "Bucket already empty",
                    "files_deleted": 0
                }
            
            # Eliminar todos los archivos
            for blob in blobs:
                blob.delete()
                logger.debug(f"Deleted: {blob.name}")
            
            logger.info(f"Test bucket {self.bucket_name} cleaned ({len(blobs)} files deleted)")
            
            return {
                "message": f"Bucket cleaned successfully",
                "files_deleted": len(blobs),
                "bucket": self.bucket_name
            }
            
        except Exception as e:
            logger.error(f"Failed to cleanup bucket {self.bucket_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to cleanup bucket: {str(e)}"
            )