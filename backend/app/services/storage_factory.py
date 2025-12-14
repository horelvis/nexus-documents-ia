"""
DEPRECATED: Synchronous Storage Factory

Use AsyncStorageServiceFactory instead for async contexts.
This module is kept for backward compatibility with legacy sync code
and for MockStorageService which is used in testing.

Migration:
    # Before (sync - deprecated)
    service = StorageServiceFactory.create_storage_service(tenant_id, user_id)

    # After (async - recommended)
    service = await AsyncStorageServiceFactory.create_storage_service(tenant_id, user_id, db)
"""
import logging
import os
import warnings
from typing import Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageServiceFactory:
    """Factory que decide qué implementación de storage usar basado en la disponibilidad"""
    
    @staticmethod
    def create_storage_service(tenant_id: str, user_id: Optional[str] = None, db: Optional[Union[Session, AsyncSession]] = None):
        """
        Crea la instancia apropiada de storage service.
        
        Prioridad:
        1. StorageService (microservicio) - principal
        2. MockStorageService - solo para testing
        
        Args:
            tenant_id: ID del tenant
            user_id: ID del usuario (opcional)
            db: Sesión de base de datos (opcional)
            
        Returns:
            Instancia del storage service
        """
        
        # En modo testing, verificar si queremos usar mock
        if os.getenv("TESTING") == "true" and os.getenv("USE_MOCK_STORAGE") == "true":
            logger.info("Using MockStorageService for testing")
            return MockStorageService(tenant_id, user_id)
        
        # Si está en testing pero las credenciales no están disponibles, usar mock como fallback
        testing_mode = os.getenv("TESTING") == "true"
        credentials_available = (
            os.getenv("GCS_CREDENTIALS") and 
            os.path.exists(os.getenv("GCS_CREDENTIALS", ""))
        ) or os.getenv("GCS_PROJECT_ID")
        
        # Obtener bucket_name del tenant si hay sesión de BD
        bucket_name = None
        if db:
            from app.db.models import Tenant
            # Check if this is an async session
            if isinstance(db, AsyncSession):
                # For async sessions, we can't query here directly
                # The bucket_name should be passed or retrieved elsewhere
                logger.warning("Async session detected in storage factory, bucket_name lookup skipped")
            else:
                # Sync session - use regular query
                tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
                if tenant and tenant.bucket_name:
                    bucket_name = tenant.bucket_name

        # Usar storage service (microservicio)
        try:
            from app.services.storage_service import StorageService
            
            # Test rápido de conectividad
            if not testing_mode or credentials_available:
                storage = StorageService(tenant_id, user_id, bucket_name)
                health = storage.health_check()
                
                if health.get("status") == "healthy":
                    logger.info("Using StorageService (microservice)")
                    return storage
                else:
                    logger.warning("Storage microservice unhealthy")
            else:
                logger.info("Testing mode without credentials, skipping microservice")
                
        except Exception as e:
            logger.warning(f"Storage microservice unavailable: {e}")
        
        # Si estamos en testing, usar mock como último recurso
        if testing_mode:
            logger.warning("Using MockStorageService as last resort for testing")
            return MockStorageService(tenant_id, user_id)
        
        # En producción, fallar si no hay credenciales
        raise Exception("No storage service available and not in testing mode")

class MockStorageService:
    """Mock storage service para testing cuando GCS no está disponible"""
    
    def __init__(self, tenant_id: str, user_id: Optional[str] = None):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.bucket_name = f"mock-bucket-{tenant_id}"
        self._files = {}  # Almacenamiento en memoria
        logger.info(f"Initialized MockStorageService for tenant {tenant_id}")
    
    def upload_file(self, file, object_name: str, metadata: Optional[dict] = None) -> bool:
        """Mock upload que simula éxito"""
        try:
            # Leer contenido del archivo
            if hasattr(file, 'read'):
                content = file.read()
                if hasattr(file, 'seek'):
                    file.seek(0)  # Reset para uso posterior
            else:
                content = file
            
            # Almacenar en memoria
            self._files[object_name] = {
                'content': content,
                'metadata': metadata or {},
                'size': len(content) if content else 0
            }
            
            logger.debug(f"Mock uploaded: {object_name}")
            return True
            
        except Exception as e:
            logger.error(f"Mock upload failed for {object_name}: {e}")
            return False
    
    def download_file(self, object_name: str) -> Optional[bytes]:
        """Mock download desde memoria"""
        file_info = self._files.get(object_name)
        if file_info:
            logger.debug(f"Mock downloaded: {object_name}")
            return file_info['content']
        
        logger.warning(f"Mock file not found: {object_name}")
        return None
    
    def delete_file(self, object_name: str) -> bool:
        """Mock delete desde memoria"""
        if object_name in self._files:
            del self._files[object_name]
            logger.debug(f"Mock deleted: {object_name}")
            return True
        
        logger.warning(f"Mock file not found for deletion: {object_name}")
        return False
    
    def list_files(self, prefix: str = "") -> list:
        """Mock list files"""
        files = []
        for name, info in self._files.items():
            if name.startswith(prefix):
                files.append({
                    'name': name,
                    'size': info['size'],
                    'updated': None,
                    'content_type': 'application/octet-stream',
                    'metadata': info['metadata']
                })
        
        logger.debug(f"Mock listed {len(files)} files with prefix '{prefix}'")
        return files
    
    def generate_upload_signed_url(self, object_name: str, content_type: str, expiration: Optional[int] = None):
        """Mock signed URL para upload"""
        from datetime import datetime, timedelta
        expires_at = datetime.utcnow() + timedelta(seconds=expiration or 3600)
        url = f"https://mock-storage.googleapis.com/upload/{object_name}"
        logger.debug(f"Mock generated upload URL: {object_name}")
        return url, expires_at
    
    def generate_download_signed_url(self, object_name: str, expiration: Optional[int] = None):
        """Mock signed URL para download"""
        from datetime import datetime, timedelta
        expires_at = datetime.utcnow() + timedelta(seconds=expiration or 3600)
        url = f"https://mock-storage.googleapis.com/download/{object_name}"
        logger.debug(f"Mock generated download URL: {object_name}")
        return url, expires_at
    
    def cleanup_test_bucket(self) -> bool:
        """Mock cleanup"""
        count = len(self._files)
        self._files.clear()
        logger.info(f"Mock cleaned {count} files")
        return True
    
    def delete_test_bucket(self) -> bool:
        """Mock delete bucket"""
        return self.cleanup_test_bucket()
    
    def health_check(self) -> dict:
        """Mock health check"""
        return {
            "status": "healthy",
            "service": "MockStorageService",
            "files_count": len(self._files)
        }