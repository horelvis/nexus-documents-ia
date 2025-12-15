import logging
import tempfile
import os
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
            logger.info(f"=== GCS CLIENT INITIALIZATION ===")
            logger.info(f"GCS_CREDENTIALS: {settings.GCS_CREDENTIALS}")
            logger.info(f"GCS_PROJECT_ID: {settings.GCS_PROJECT_ID}")
            
            # Verificar si el archivo de credenciales existe
            if settings.GCS_CREDENTIALS and settings.GCS_CREDENTIALS.startswith("/"):
                import os
                exists = os.path.exists(settings.GCS_CREDENTIALS)
                logger.info(f"Credentials file exists: {exists}")
                if exists:
                    import stat
                    file_stat = os.stat(settings.GCS_CREDENTIALS)
                    logger.info(f"Credentials file size: {file_stat.st_size} bytes")
                    logger.info(f"Credentials file permissions: {oct(file_stat.st_mode)}")
            
            # Siempre usar GCS real - verificar si hay credenciales configuradas
            if settings.GCS_CREDENTIALS and settings.GCS_CREDENTIALS.strip():
                # Usar credenciales explícitas
                if settings.GCS_CREDENTIALS.startswith("/"):
                    # Es un path a archivo - usar método recomendado
                    logger.info(f"Using service account file: {settings.GCS_CREDENTIALS}")
                    self.client = storage.Client.from_service_account_json(settings.GCS_CREDENTIALS)
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
            self.bucket = self.client.bucket(self.bucket_name)
            if not self.bucket.exists():
                raise Exception("Bucket does not exist")
            logger.info(f"Bucket {self.bucket_name} found")
        except Exception:
            try:
                logger.info(f"Creating bucket {self.bucket_name} in location europe-west1")
                logger.info(f"Using project: {settings.GCS_PROJECT_ID}")
                self.bucket = self.client.bucket(self.bucket_name)
                self.bucket.create(location="europe-west1")
                logger.info(f"Bucket {self.bucket_name} created successfully")
            except Exception as e:
                logger.error(f"Failed to create bucket {self.bucket_name}: {e}")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error details: {str(e)}")
                
                # Intentar crear sin especificar ubicación
                try:
                    logger.info(f"Retrying bucket creation without location...")
                    self.bucket = self.client.bucket(self.bucket_name)
                    self.bucket.create()
                    logger.info(f"Bucket {self.bucket_name} created successfully (default location)")
                except Exception as e2:
                    logger.error(f"Second attempt also failed: {e2}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to setup storage bucket: {str(e)}"
                    )
    
    async def upload_file(
        self,
        file: Union[UploadFile, BinaryIO, bytes],
        object_name: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Uploads bytes from a stream or other file-like object to a blob.
        
        Based on official documentation:
        https://cloud.google.com/storage/docs/uploading-objects#storage-upload-object-from-stream-python
        """
        try:
            # Construct a client-side representation of the blob
            blob = self.bucket.blob(object_name)
            
            # Set metadata if provided
            if metadata:
                blob.metadata = metadata
            
            logger.info(f"Uploading {object_name} to bucket {self.bucket_name}")
            
            # Initialize file_size
            file_size = 0
            
            # Use temporary files for all uploads (consistent and memory-efficient)
            if isinstance(file, UploadFile) or hasattr(file, 'read') and hasattr(file, 'file'):
                # For FastAPI UploadFile - save directly to temp file
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    try:
                        # Copy file content to temp file
                        content = await file.read()
                        file_size = len(content)
                        temp_file.write(content)
                        temp_file.flush()
                        
                        # Upload from temp file
                        blob.upload_from_filename(temp_file.name)
                    finally:
                        os.unlink(temp_file.name)
                        
            elif isinstance(file, bytes):
                # For bytes
                file_size = len(file)
                
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    try:
                        temp_file.write(file)
                        temp_file.flush()
                        blob.upload_from_filename(temp_file.name)
                    finally:
                        os.unlink(temp_file.name)
                        
            else:
                # For other file-like objects
                content = file.read()
                file_size = len(content)
                
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    try:
                        temp_file.write(content)
                        temp_file.flush()
                        blob.upload_from_filename(temp_file.name)
                    finally:
                        os.unlink(temp_file.name)
            
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
    
    def move_file(self, source_name: str, destination_name: str) -> Dict[str, Any]:
        """
        Move a file within the bucket (copy + delete).

        Uses GCS's native copy operation which is atomic and efficient
        for files within the same bucket.

        Args:
            source_name: Current object name/path
            destination_name: New object name/path

        Returns:
            Information about the move operation
        """
        try:
            source_blob = self.bucket.blob(source_name)

            if not source_blob.exists():
                logger.warning(f"Source file not found: {source_name}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Source file not found: {source_name}"
                )

            # Copy to new location
            destination_blob = self.bucket.copy_blob(
                source_blob,
                self.bucket,
                destination_name
            )

            # Delete original
            source_blob.delete()

            logger.info(f"File moved successfully: {source_name} -> {destination_name}")

            return {
                "source": source_name,
                "destination": destination_name,
                "bucket": self.bucket_name,
                "moved_at": datetime.utcnow().isoformat()
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to move file {source_name} -> {destination_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to move file: {str(e)}"
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