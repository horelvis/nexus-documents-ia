#!/usr/bin/env python3
"""
Script para probar el reindex con metadatos mejorados
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.append('/app')

from app.services.reindex_service import ReindexService
from app.db.database import SessionLocal

async def test_reindex():
    """Test reindex functionality"""
    
    # Usar el tenant ID que aparece en los logs (puedes cambiarlo según tu tenant)
    tenant_id = "09345153-5821-468d-84bf-f2473039e589"
    
    print(f"🚀 Iniciando prueba de reindex para tenant: {tenant_id}")
    
    # Crear servicio de reindex
    reindex_service = ReindexService(tenant_id=tenant_id)
    
    # Verificar estado actual
    print("📊 Verificando estado actual del reindex...")
    status = await reindex_service.check_reindex_status()
    print(f"Estado actual: {status}")
    
    # Obtener documentos que necesitan reindex
    print("🔍 Buscando documentos que necesitan reindex...")
    with SessionLocal() as db:
        docs_needing_reindex = await reindex_service.get_documents_needing_reindex(db)
        print(f"Documentos que necesitan reindex: {len(docs_needing_reindex)}")
        
        for doc in docs_needing_reindex[:3]:  # Solo mostrar los primeros 3
            print(f"  - {doc.filename} (ID: {doc.id})")
    
    # Si hay documentos para reindexar, hacer reindex de uno como prueba
    if docs_needing_reindex:
        print("🔄 Iniciando reindex de documentos...")
        result = await reindex_service.reindex_all_missing(max_concurrent=2)
        print(f"Resultado del reindex: {result}")
    else:
        print("✅ No hay documentos que necesiten reindex")

if __name__ == "__main__":
    asyncio.run(test_reindex())