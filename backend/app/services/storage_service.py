import io
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Tuple, BinaryIO, Union, Dict, Any

from fastapi import UploadFile
from google.cloud import storage
from google.oauth2 import service_account

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Servicio para gestión de almacenamiento en Google Cloud Storage"""
    
    def __init__(self, tenant_id: str = None):
        """
        Inicializa el servicio de almacenamiento.
        
        Args:
            tenant_id: ID del tenant para separar buckets
        """
        self.tenant_id = tenant_id or settings.DEFAULT_TENANT
        
        # Inicializar cliente GCS
        import os
        if os.getenv("TESTING") == "true":
            # En entorno de testing, usar credenciales por defecto sin archivo
            try:
                self.client = storage.Client(project=settings.GCS_PROJECT_ID)
            except Exception as e:
                logger.warning(f"No se pudo inicializar GCS en testing, usando cliente mock: {e}")
                # Si falla, crear un cliente básico para testing
                self.client = None
        elif settings.GCS_CREDENTIALS and os.path.exists(settings.GCS_CREDENTIALS):
            # Usar credenciales explícitas si están configuradas y el archivo existe
            credentials = service_account.Credentials.from_service_account_file(
                settings.GCS_CREDENTIALS
            )
            self.client = storage.Client(
                credentials=credentials,
                project=settings.GCS_PROJECT_ID
            )
        else:
            # Usar credenciales por defecto del entorno
            self.client = storage.Client()
        
        # Obtener o crear bucket
        self.bucket_name = f"{settings.GCS_BUCKET_NAME}-{self.tenant_id}"
        self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self):
        """Asegura que el bucket exista, creándolo si es necesario"""
        import os
        if os.getenv("TESTING") == "true" and self.client is None:
            # En testing sin cliente GCS real, crear un bucket mock
            logger.info(f"Testing mode: using mock bucket {self.bucket_name}")
            self.bucket = None
            return
            
        try:
            self.bucket = self.client.get_bucket(self.bucket_name)
        except Exception as e:
            logger.info(f"Bucket {self.bucket_name} no encontrado, creando...")
            # Crear bucket con ubicación europe-west1
            self.bucket = self.client.create_bucket(
                self.bucket_name, 
                location="europe-west1"
            )
            logger.info(f"Bucket {self.bucket_name} creado exitosamente")
    
    def generate_upload_signed_url(
        self, 
        object_name: str, 
        content_type: str,
        expiration: int = None
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
        import os
        expiration = expiration or settings.SIGNED_URL_EXPIRATION
        expires_at = datetime.utcnow() + timedelta(seconds=expiration)
        
        # En modo testing, devolver URL mock
        if os.getenv("TESTING") == "true" and self.bucket is None:
            return f"https://mock-storage.googleapis.com/upload/{object_name}", expires_at
        
        blob = self.bucket.blob(object_name)
        
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=expiration),
            method="PUT",
            content_type=content_type,
        )
        
        return url, expires_at
    
    def generate_download_signed_url(
        self, 
        object_name: str,
        expiration: int = None
    ) -> Tuple[str, datetime]:
        """
        Genera una URL firmada para descargar un objeto.
        
        Args:
            object_name: Nombre del objeto a descargar
            expiration: Tiempo de expiración en segundos
            
        Returns:
            Tuple con la URL firmada y la fecha de expiración
        """
        import os
        expiration = expiration or settings.SIGNED_URL_EXPIRATION
        expires_at = datetime.utcnow() + timedelta(seconds=expiration)
        
        # En modo testing, devolver URL mock
        if os.getenv("TESTING") == "true" and self.bucket is None:
            return f"https://mock-storage.googleapis.com/download/{object_name}", expires_at
        
        blob = self.bucket.blob(object_name)
        
        # Verificar si el objeto existe
        if not blob.exists():
            raise FileNotFoundError(f"El objeto {object_name} no existe en el bucket {self.bucket_name}")
        
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=expiration),
            method="GET",
        )
        
        return url, expires_at
    
    def upload_file(
        self, 
        file: Union[UploadFile, BinaryIO], 
        object_name: str, 
        metadata: Dict[str, str] = None
    ) -> bool:
        """
        Sube un archivo directamente al almacenamiento.
        
        Args:
            file: Objeto de archivo a subir
            object_name: Nombre del objeto en el almacenamiento
            metadata: Metadatos asociados al archivo
            
        Returns:
            True si se subió correctamente, False en caso contrario
        """
        try:
            blob = self.bucket.blob(object_name)
            
            # Añadir metadatos si existen
            if metadata:
                blob.metadata = metadata
            
            # Convertir UploadFile a BytesIO si es necesario
            if isinstance(file, UploadFile):
                content = file.file.read()
                file_obj = io.BytesIO(content)
            else:
                file_obj = file
            
            # Subir el archivo
            blob.upload_from_file(file_obj, rewind=True)
            
            logger.info(f"Archivo {object_name} subido exitosamente a {self.bucket_name}")
            return True
            
        except Exception as e:
            logger.exception(f"Error al subir archivo {object_name}: {str(e)}")
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
            blob = self.bucket.blob(object_name)
            
            # Verificar si el objeto existe
            if not blob.exists():
                logger.warning(f"El objeto {object_name} no existe en el bucket {self.bucket_name}")
                return None
            
            # Descargar el contenido
            content = blob.download_as_bytes()
            
            logger.info(f"Archivo {object_name} descargado exitosamente de {self.bucket_name}")
            return content
            
        except Exception as e:
            logger.exception(f"Error al descargar archivo {object_name}: {str(e)}")
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
            blob = self.bucket.blob(object_name)
            
            # Verificar si el objeto existe
            if not blob.exists():
                logger.warning(f"El objeto {object_name} no existe en el bucket {self.bucket_name}")
                return False
            
            # Eliminar el archivo
            blob.delete()
            
            logger.info(f"Archivo {object_name} eliminado exitosamente de {self.bucket_name}")
            return True
            
        except Exception as e:
            logger.exception(f"Error al eliminar archivo {object_name}: {str(e)}")
            return False
    
    def list_files(self, prefix: str = "") -> list:
        """
        Lista los archivos en el almacenamiento.
        
        Args:
            prefix: Prefijo para filtrar archivos
            
        Returns:
            Lista de información de archivos
        """
        try:
            blobs = self.bucket.list_blobs(prefix=prefix)
            
            result = []
            for blob in blobs:
                result.append({
                    "name": blob.name,
                    "size": blob.size,
                    "updated": blob.updated,
                    "content_type": blob.content_type,
                    "metadata": blob.metadata
                })
            
            return result
            
        except Exception as e:
            logger.exception(f"Error al listar archivos con prefijo {prefix}: {str(e)}")
            return []