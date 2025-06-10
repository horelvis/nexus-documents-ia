import logging
from typing import Optional, Tuple, BinaryIO, Union, Dict, Any, List
from datetime import datetime
from fastapi import UploadFile

from app.services.storage_client import StorageClient

logger = logging.getLogger(__name__)

class StorageService:
    """
    StorageService que usa el microservicio de storage.
    Proporciona interfaz para gestión de documentos via microservicio.
    """
    
    def __init__(self, tenant_id: str, user_id: Optional[str] = None, bucket_name: Optional[str] = None):
        """
        Inicializa el servicio de almacenamiento usando el microservicio.
        
        Args:
            tenant_id: ID del tenant
            user_id: ID del usuario (opcional)
            bucket_name: Nombre del bucket (opcional)
        """
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.bucket_name = bucket_name or f"storage-service-{tenant_id}"
        self.client = StorageClient(tenant_id, user_id, self.bucket_name)
    
    def upload_file(
        self, 
        file: Union[UploadFile, BinaryIO, bytes], 
        object_name: str, 
        metadata: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Sube un archivo al almacenamiento.
        
        Args:
            file: Objeto de archivo a subir
            object_name: Nombre del objeto en el almacenamiento
            metadata: Metadatos asociados al archivo
            
        Returns:
            True si se subió correctamente, False en caso contrario
        """
        try:
            # Extraer filename del object_name
            filename = object_name.split("/")[-1]
            
            result = self.client.upload_file(
                file=file,
                filename=filename,
                metadata=metadata
            )
            
            logger.info(f"File uploaded successfully: {object_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upload file {object_name}: {e}")
            return False
    
    def download_file(self, object_name: str) -> Optional[bytes]:
        """
        Descarga un archivo del almacenamiento.
        
        Args:
            object_name: Nombre del objeto a descargar
            
        Returns:
            Contenido del archivo como bytes o None si no existe
        """
        try:
            # Extraer path del object_name
            file_path = object_name.split("/")[-1]
            
            content = self.client.download_file(file_path)
            
            if content:
                logger.info(f"File downloaded successfully: {object_name}")
            else:
                logger.warning(f"File not found: {object_name}")
            
            return content
            
        except Exception as e:
            logger.error(f"Failed to download file {object_name}: {e}")
            return None
    
    def delete_file(self, object_name: str) -> bool:
        """
        Elimina un archivo del almacenamiento.
        
        Args:
            object_name: Nombre del objeto a eliminar
            
        Returns:
            True si se eliminó correctamente, False en caso contrario
        """
        try:
            # Extraer path del object_name
            file_path = object_name.split("/")[-1]
            
            success = self.client.delete_file(file_path)
            
            if success:
                logger.info(f"File deleted successfully: {object_name}")
            else:
                logger.warning(f"File not found for deletion: {object_name}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to delete file {object_name}: {e}")
            return False
    
    def list_files(self, prefix: str = "") -> List[Dict[str, Any]]:
        """
        Lista los archivos en el almacenamiento.
        
        Args:
            prefix: Prefijo para filtrar archivos
            
        Returns:
            Lista de información de archivos
        """
        try:
            files = self.client.list_files(prefix=prefix)
            
            # Convertir formato para compatibilidad con código existente
            result = []
            for file_info in files:
                result.append({
                    "name": file_info.get("name", ""),
                    "size": file_info.get("size", 0),
                    "updated": file_info.get("updated"),
                    "content_type": file_info.get("content_type"),
                    "metadata": file_info.get("metadata", {})
                })
            
            logger.info(f"Listed {len(result)} files with prefix '{prefix}'")
            return result
            
        except Exception as e:
            logger.error(f"Failed to list files with prefix {prefix}: {e}")
            return []
    
    def generate_upload_signed_url(
        self, 
        object_name: str, 
        content_type: str,
        expiration: Optional[int] = None
    ) -> Tuple[str, datetime]:
        """
        Genera una URL firmada para subir un objeto.
        
        Args:
            object_name: Nombre del objeto a subir
            content_type: Tipo MIME del contenido
            expiration: Tiempo de expiración en segundos
            
        Returns:
            Tuple con la URL firmada y la fecha de expiración
        """
        try:
            # Extraer filename del object_name
            filename = object_name.split("/")[-1]
            
            url, expires_at = self.client.generate_upload_signed_url(
                filename=filename,
                content_type=content_type,
                expiration=expiration
            )
            
            logger.info(f"Generated upload signed URL for: {object_name}")
            return url, expires_at
            
        except Exception as e:
            logger.error(f"Failed to generate upload signed URL for {object_name}: {e}")
            raise
    
    def generate_download_signed_url(
        self, 
        object_name: str,
        expiration: Optional[int] = None
    ) -> Tuple[str, datetime]:
        """
        Genera una URL firmada para descargar un objeto.
        
        Args:
            object_name: Nombre del objeto a descargar
            expiration: Tiempo de expiración en segundos
            
        Returns:
            Tuple con la URL firmada y la fecha de expiración
        """
        try:
            # Extraer path del object_name
            file_path = object_name.split("/")[-1]
            
            url, expires_at = self.client.generate_download_signed_url(
                file_path=file_path,
                expiration=expiration
            )
            
            logger.info(f"Generated download signed URL for: {object_name}")
            return url, expires_at
            
        except Exception as e:
            logger.error(f"Failed to generate download signed URL for {object_name}: {e}")
            raise
    
    def cleanup_test_bucket(self) -> bool:
        """
        Limpia completamente el bucket de test eliminando todos los archivos.
        Solo funciona en modo testing.
        
        Returns:
            True si se limpió correctamente, False en caso contrario
        """
        try:
            result = self.client.cleanup_test_bucket()
            
            logger.info(f"Test bucket cleaned: {result}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cleanup test bucket: {e}")
            return False
    
    def delete_test_bucket(self) -> bool:
        """
        Elimina completamente el bucket de test.
        Alias para cleanup_test_bucket para compatibilidad.
        
        Returns:
            True si se eliminó correctamente, False en caso contrario
        """
        return self.cleanup_test_bucket()
    
    def health_check(self) -> Dict[str, Any]:
        """
        Verifica el estado del storage service.
        
        Returns:
            Estado del servicio
        """
        try:
            return self.client.health_check()
        except Exception as e:
            logger.error(f"Storage service health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }