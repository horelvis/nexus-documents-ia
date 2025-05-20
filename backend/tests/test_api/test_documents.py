import pytest
import io
from fastapi.testclient import TestClient

def test_list_documents(client, test_documents, normal_user_token_headers):
    """Prueba para listar documentos"""
    response = client.get(
        "/api/v1/documents/",
        headers=normal_user_token_headers
    )
    assert response.status_code == 200
    content = response.json()
    assert "documents" in content
    assert "pagination" in content
    assert len(content["documents"]) == 3
    assert content["pagination"]["total"] == 3

def test_get_document(client, test_documents, normal_user_token_headers):
    """Prueba para obtener un documento específico"""
    doc_id = str(test_documents[0].id)
    response = client.get(
        f"/api/v1/documents/{doc_id}",
        headers=normal_user_token_headers
    )
    assert response.status_code == 200
    content = response.json()
    assert content["id"] == doc_id
    assert content["title"] == "Test Document 1"
    assert "preview_chunks" in content
    assert len(content["preview_chunks"]) == 2

def test_get_nonexistent_document(client, normal_user_token_headers):
    """Prueba para obtener un documento inexistente"""
    response = client.get(
        "/api/v1/documents/00000000-0000-0000-0000-000000000000",
        headers=normal_user_token_headers
    )
    assert response.status_code == 404

def test_upload_document(client, normal_user_token_headers, monkeypatch, mock_storage_service, mock_embedding_service):
    """Prueba para subir un documento"""
    # Crear archivo de prueba
    file_content = b"This is a test document content."
    file = io.BytesIO(file_content)
    
    response = client.post(
        "/api/v1/documents/",
        headers=normal_user_token_headers,
        files={"file": ("test.txt", file, "text/plain")},
        data={
            "title": "Upload Test Document",
            "description": "Test description",
            "tags": "tag1,tag2"
        }
    )
    
    assert response.status_code == 200
    content = response.json()
    assert content["title"] == "Upload Test Document"
    assert content["description"] == "Test description"
    assert content["file_type"] == "txt"
    assert "tag1" in content["tags"]
    assert "tag2" in content["tags"]

def test_upload_invalid_file_type(client, normal_user_token_headers):
    """Prueba para subir un archivo con tipo no permitido"""
    # Crear archivo de prueba
    file_content = b"This is an invalid file type."
    file = io.BytesIO(file_content)
    
    response = client.post(
        "/api/v1/documents/",
        headers=normal_user_token_headers,
        files={"file": ("test.invalid", file, "application/octet-stream")},
        data={"title": "Invalid File Type"}
    )
    
    assert response.status_code == 400
    content = response.json()
    assert "detail" in content
    assert "Tipo de archivo no permitido" in content["detail"]

def test_delete_document(client, test_documents, normal_user_token_headers, mock_storage_service, mock_embedding_service):
    """Prueba para eliminar un documento"""
    doc_id = str(test_documents[0].id)
    response = client.delete(
        f"/api/v1/documents/{doc_id}",
        headers=normal_user_token_headers
    )
    
    assert response.status_code == 200
    content = response.json()
    assert "message" in content
    assert "deleted successfully" in content["message"]
    
    # Verificar que el documento ya no existe
    response = client.get(
        f"/api/v1/documents/{doc_id}",
        headers=normal_user_token_headers
    )
    assert response.status_code == 404

def test_delete_nonexistent_document(client, normal_user_token_headers):
    """Prueba para eliminar un documento inexistente"""
    response = client.delete(
        "/api/v1/documents/00000000-0000-0000-0000-000000000000",
        headers=normal_user_token_headers
    )
    
    assert response.status_code == 404

def test_add_tag(client, test_documents, normal_user_token_headers):
    """Prueba para añadir una etiqueta a un documento"""
    doc_id = str(test_documents[0].id)
    response = client.post(
        f"/api/v1/documents/{doc_id}/tag",
        headers=normal_user_token_headers,
        json={"tag": "new-tag"}
    )
    
    assert response.status_code == 200
    content = response.json()
    assert "message" in content
    assert "new-tag" in content["message"]
    
    # Verificar que la etiqueta se añadió
    response = client.get(
        f"/api/v1/documents/{doc_id}",
        headers=normal_user_token_headers
    )
    
    assert response.status_code == 200
    content = response.json()
    assert "new-tag" in content["tags"]

def test_generate_summary(client, test_documents, normal_user_token_headers, mock_llm_service):
    """Prueba para generar un resumen de un documento"""
    doc_id = str(test_documents[0].id)
    response = client.get(
        f"/api/v1/documents/{doc_id}/summary",
        headers=normal_user_token_headers
    )
    
    assert response.status_code == 200
    content = response.json()
    assert "summary" in content
    assert "mock summary" in content["summary"].lower()

def test_get_signed_download_url(client, test_documents, normal_user_token_headers, mock_storage_service):
    """Prueba para obtener URL firmada de descarga"""
    doc_id = str(test_documents[0].id)
    response = client.get(
        f"/api/v1/documents/{doc_id}/download-url",
        headers=normal_user_token_headers
    )
    
    assert response.status_code == 200
    content = response.json()
    assert "url" in content
    assert "expires_at" in content
    assert doc_id in content["url"]

def test_get_signed_upload_url(client, normal_user_token_headers, mock_storage_service):
    """Prueba para obtener URL firmada de carga"""
    response = client.post(
        "/api/v1/documents/upload-url",
        headers=normal_user_token_headers,
        json={
            "filename": "test-upload.txt",
            "content_type": "text/plain",
            "size": 1000
        }
    )
    
    assert response.status_code == 200
    content = response.json()
    assert "upload_url" in content
    assert "expires_at" in content
    assert "file_path" in content
    assert "doc_id" in content