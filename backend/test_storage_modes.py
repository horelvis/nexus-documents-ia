#!/usr/bin/env python3
"""
Script para demostrar los diferentes modos de storage disponibles.
Útil para testing y debugging.
"""

import os
import sys
import logging

# Agregar el directorio del proyecto al path
sys.path.insert(0, '/Users/horelvis/git-personal/nexus-document-backend/backend')

from app.services.storage_factory import StorageServiceFactory

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(name)s - %(message)s')

def test_storage_mode(mode_name, env_vars):
    """Prueba un modo específico de storage"""
    print(f"\n🧪 Testing {mode_name}...")
    print(f"Environment: {env_vars}")
    
    # Configurar variables de entorno
    for key, value in env_vars.items():
        if value is None:
            if key in os.environ:
                del os.environ[key]
        else:
            os.environ[key] = value
    
    try:
        # Crear storage service
        storage = StorageServiceFactory.create_storage_service(
            tenant_id="test-tenant-123",
            user_id="test-user-456"
        )
        
        print(f"✅ Success: {type(storage).__name__}")
        
        # Test health check
        health = storage.health_check()
        print(f"Health: {health}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

def main():
    """Función principal"""
    print("🚀 Storage Service Mode Testing")
    print("=" * 50)
    
    # Modo 1: Mock explícito
    test_storage_mode("Mock Storage (Explicit)", {
        "TESTING": "true",
        "USE_MOCK_STORAGE": "true",
        "GCS_CREDENTIALS": None,
        "STORAGE_SERVICE_URL": None
    })
    
    # Modo 2: Testing sin credenciales (debería usar mock)
    test_storage_mode("Testing without credentials (should use mock)", {
        "TESTING": "true",
        "USE_MOCK_STORAGE": None,
        "GCS_CREDENTIALS": None,
        "GCS_PROJECT_ID": None,
        "STORAGE_SERVICE_URL": "http://localhost:8003"  # No disponible
    })
    
    # Modo 3: Testing con microservicio (si está disponible)
    test_storage_mode("Testing with microservice", {
        "TESTING": "true",
        "USE_MOCK_STORAGE": None,
        "GCS_CREDENTIALS": "/app/credentials/nexus-document-ia-04252dae0146.json",
        "GCS_PROJECT_ID": "tu-project-id",
        "STORAGE_SERVICE_URL": "http://localhost:8003",
        "STORAGE_API_KEY": "test-storage-api-key-12345"
    })
    
    # Modo 4: Producción (fallback a original)
    test_storage_mode("Production mode (fallback to original)", {
        "TESTING": None,
        "USE_MOCK_STORAGE": None,
        "GCS_CREDENTIALS": "/fake/path/to/credentials.json",  # No existe
        "GCS_PROJECT_ID": "tu-project-id",
        "STORAGE_SERVICE_URL": "http://localhost:8003"  # No disponible
    })
    
    print("\n📋 Summary:")
    print("- Mock storage: Always works in testing mode")
    print("- Microservice: Works if service is running and configured")  
    print("- Original GCS: Works if credentials are available")
    print("- Factory automatically selects best available option")

if __name__ == "__main__":
    main()