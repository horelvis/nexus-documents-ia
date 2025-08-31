#!/usr/bin/env python3
"""
Script para probar reindex de documentos en estado de error
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.append('/app')

from app.services.reindex_service import ReindexService
from app.db.database import SessionLocal
from app.db.models import Document
from app.schemas.enums import IndexingStatus
from sqlalchemy import and_

async def test_reindex_errors():
    """Test reindex functionality for error documents"""
    
    # Usar el tenant ID que aparece en los logs
    tenant_id = "09345153-5821-468d-84bf-f2473039e589"
    
    print(f"🚀 Iniciando reindex forzado de documentos con error para tenant: {tenant_id}")
    
    # Crear servicio de reindex
    reindex_service = ReindexService(tenant_id=tenant_id)
    
    # Obtener documentos en error
    print("🔍 Buscando documentos en estado de error...")
    with SessionLocal() as db:
        error_docs = db.query(Document).filter(
            and_(
                Document.tenant_id == tenant_id,
                Document.indexed == IndexingStatus.INDEXING_ERROR
            )
        ).all()
        
        print(f"Encontrados {len(error_docs)} documentos en error:")
        
        for doc in error_docs[:5]:  # Solo mostrar los primeros 5
            print(f"  - {doc.filename} (ID: {doc.id}) - Error: {getattr(doc, 'indexing_error', 'Unknown')}")
    
    if error_docs:
        print("🔄 Intentando reindexar documento de prueba...")
        
        # Tomar el primer documento y intentar reindexarlo
        test_doc = error_docs[0]
        print(f"Reindexando: {test_doc.filename}")
        
        with SessionLocal() as db:
            # Refresh el documento en la nueva sesión
            test_doc_refreshed = db.query(Document).filter(Document.id == test_doc.id).first()
            if test_doc_refreshed:
                success = await reindex_service.reindex_document(db, test_doc_refreshed)
                print(f"Resultado del reindex: {'✅ Éxito' if success else '❌ Falló'}")
                
                # Verificar estado final
                db.refresh(test_doc_refreshed)
                print(f"Estado final del documento: {test_doc_refreshed.indexed}")
    else:
        print("✅ No hay documentos en error para reindexar")

if __name__ == "__main__":
    asyncio.run(test_reindex_errors())