import pytest
import io
from uuid import uuid4
from fastapi import UploadFile
from datetime import datetime

from app.services.document_service import DocumentService
from app.db.models import Document, DocumentChunk, Tag


def test_get_documents(db, test_documents, test_tenant):
    """Prueba para obtener lista de documentos"""
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    
    result = document_service.get_documents(page=1, per_page=10)
    
    assert "documents" in result
    assert "pagination" in result
    assert len(result["documents"]) == 3
    assert result["pagination"]["total"] == 3
    
    # Probar paginación
    result = document_service.get_documents(page=1, per_page=2)
    assert len(result["documents"]) == 2
    assert result["pagination"]["total"] == 3
    assert result["pagination"]["pages"] == 2

def test_get_documents_with_filters(db, test_documents, test_tags, test_tenant):
    """Prueba para obtener documentos con filtros"""
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    
    # Filtrar por tag
    result = document_service.get_documents(tags=[test_tags[0].name])
    assert len(result["documents"]) > 0
    for doc in result["documents"]:
        assert test_tags[0].name in doc["tags"]
    
    # Filtrar por fecha
    from_date = datetime.utcnow().isoformat()
    result = document_service.get_documents(date_from=from_date)
    assert len(result["documents"]) == 0  # No debería haber documentos después de la fecha actual

def test_get_document(db, test_documents, test_tenant):
    """Prueba para obtener un documento específico"""
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    
    result = document_service.get_document(doc_id=str(test_documents[0].id))
    
    assert result["id"] == str(test_documents[0].id)
    assert result["title"] == test_documents[0].title
    assert "preview_chunks" in result
    assert len(result["preview_chunks"]) == 2  # Dos chunks creados en fixture

def test_add_and_remove_tag(db, test_documents, test_tenant):
    """Prueba para añadir y eliminar etiquetas"""
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    
    # Añadir tag
    tag_name = "new-test-tag"
    result = document_service.add_tag(doc_id=str(test_documents[0].id), tag_name=tag_name)
    assert "message" in result
    assert tag_name in result["message"]
    
    # Verificar que se añadió
    doc = document_service.get_document(doc_id=str(test_documents[0].id))
    assert tag_name in doc["tags"]
    
    # Eliminar tag
    result = document_service.remove_tag(doc_id=str(test_documents[0].id), tag_name=tag_name)
    assert "message" in result
    assert "removed" in result["message"]
    
    # Verificar que se eliminó
    doc = document_service.get_document(doc_id=str(test_documents[0].id))
    assert tag_name not in doc["tags"]

def test_generate_summary(db, test_documents, test_tenant, mock_llm_service):
    """Prueba para generar resumen de documento"""
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    document_service.llm_service = mock_llm_service
    
    result = document_service.generate_summary(doc_id=str(test_documents[0].id))
    
    assert "summary" in result
    assert "mock summary" in result["summary"].lower()

def test_get_signed_download_url(db, test_documents, test_tenant, mock_storage_service):
    """Prueba para obtener URL firmada de descarga"""
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    document_service.storage_service = mock_storage_service
    
    result = document_service.get_signed_download_url(doc_id=str(test_documents[0].id))
    
    assert "url" in result
    assert "expires_at" in result
    assert "filename" in result
    assert test_documents[0].filename == result["filename"]
    assert "mock-storage.example.com" in result["url"]

def test_get_signed_upload_url(db, test_tenant, mock_storage_service):
    """Prueba para obtener URL firmada de carga"""
    document_service = DocumentService(tenant_id=str(test_tenant.id))
    document_service.storage_service = mock_storage_service
    
    result = document_service.get_signed_upload_url(
        filename="test-upload.txt",
        content_type="text/plain"
    )
    
    assert "upload_url" in result
    assert "expires_at" in result
    assert "file_path" in result
    assert "doc_id" in result
    assert "mock-storage.example.com" in result["upload_url"]
    assert "documents/" in result["file_path"]
    assert "test-upload.txt" in result["file_path"]

def test_extract_text_methods(db, test_tenant):
    """Prueba para métodos de extracción de texto"""
    document_service = DocumentService(tenant_id=str(test_tenant.id))
    
    # Prueba con TXT
    txt_content = b"Este es un archivo de texto simple para pruebas."
    txt_file = io.BytesIO(txt_content)
    txt_text = document_service._extract_text(txt_file, "txt")
    assert txt_text.strip() == txt_content.decode().strip()
    
    # Nota: Las pruebas para PDF, DOCX, CSV y Excel requieren archivos reales
    # o mocks más complejos de sus respectivas bibliotecas