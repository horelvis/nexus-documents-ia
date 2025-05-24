import pytest
import io
from fastapi.testclient import TestClient

def test_list_documents(client, test_documents, normal_user_token_headers):
    """Prueba para listar documentos"""
    # Act
    response = client.get(
        "/api/v1/documents/",
        headers=normal_user_token_headers
    )
    
    # Assert
    assert response.status_code == 200, f"Expected status 200 but got {response.status_code}. Response: {response.text}"
    listed_content = response.json()
    assert "documents" in listed_content, "Response JSON should contain 'documents' key"
    assert "pagination" in listed_content, "Response JSON should contain 'pagination' key"
    assert len(listed_content["documents"]) == 3, f"Expected 3 documents, got {len(listed_content['documents'])}"
    assert listed_content["pagination"]["total"] == 3, f"Expected pagination total 3, got {listed_content['pagination']['total']}"
    
    # Check a known title to ensure data consistency
    expected_titles = {doc.title for doc in test_documents}
    assert listed_content["documents"][0]["title"] in expected_titles, f"Document title '{listed_content['documents'][0]['title']}' not in expected titles."

def test_get_document(client, test_documents, normal_user_token_headers):
    """Prueba para obtener un documento específico"""
    # Arrange
    document_to_get = test_documents[0]
    doc_id_str = str(document_to_get.id)
    
    # Act
    response = client.get(
        f"/api/v1/documents/{doc_id_str}",
        headers=normal_user_token_headers
    )
    
    # Assert
    assert response.status_code == 200, f"Expected status 200 but got {response.status_code}. Response: {response.text}"
    retrieved_document = response.json()
    assert retrieved_document["id"] == doc_id_str, f"Expected document ID {doc_id_str} but got {retrieved_document['id']}"
    assert retrieved_document["title"] == document_to_get.title, f"Expected title '{document_to_get.title}' but got {retrieved_document['title']}"
    assert "preview_chunks" in retrieved_document, "Response JSON should contain 'preview_chunks' key"
    assert len(retrieved_document["preview_chunks"]) == 2, f"Expected 2 preview chunks, got {len(retrieved_document['preview_chunks'])}"
    # Assuming test_documents[0] is "Test Document 1" and has specific chunk content
    assert "Content for document 1, chunk 1" in retrieved_document["preview_chunks"][0]["content"], "Preview chunk content mismatch"

def test_get_nonexistent_document(client, normal_user_token_headers):
    """Prueba para obtener un documento inexistente"""
    # Arrange
    non_existent_doc_id = "00000000-0000-0000-0000-000000000000"
    
    # Act
    response = client.get(
        f"/api/v1/documents/{non_existent_doc_id}",
        headers=normal_user_token_headers
    )
    
    # Assert
    assert response.status_code == 404, f"Expected status 404 but got {response.status_code}. Response: {response.text}"
    error_content = response.json()
    assert "detail" in error_content, "Response JSON should contain 'detail' key for errors"
    assert "Document not found" in error_content["detail"], f"Expected 'Document not found' in details, got {error_content['detail']}"

def test_upload_document(client, normal_user_token_headers, monkeypatch, mock_storage_service, mock_embedding_service):
    """Prueba para subir un documento"""
    # Arrange
    file_content = b"This is a test document content."
    test_file = io.BytesIO(file_content)
    document_payload = {
        "title": "Upload Test Document",
        "description": "Test description",
        "tags": "tag1,tag2"
    }
    
    # Act
    response = client.post(
        "/api/v1/documents/",
        headers=normal_user_token_headers,
        files={"file": ("test.txt", test_file, "text/plain")},
        data=document_payload
    )
    
    # Assert
    assert response.status_code == 200, f"Expected status 200 but got {response.status_code}. Response: {response.text}"
    uploaded_document_content = response.json()
    assert uploaded_document_content["title"] == document_payload["title"], f"Expected title '{document_payload['title']}', got '{uploaded_document_content['title']}'"
    assert uploaded_document_content["description"] == document_payload["description"], f"Expected description '{document_payload['description']}', got '{uploaded_document_content['description']}'"
    assert uploaded_document_content["filename"] == "test.txt", f"Expected filename 'test.txt', got '{uploaded_document_content['filename']}'"
    assert uploaded_document_content["file_type"] == "txt", f"Expected file_type 'txt', got '{uploaded_document_content['file_type']}'"
    assert "tag1" in uploaded_document_content["tags"], "Expected 'tag1' in tags"
    assert "tag2" in uploaded_document_content["tags"], "Expected 'tag2' in tags"

def test_upload_invalid_file_type(client, normal_user_token_headers):
    """Prueba para subir un archivo con tipo no permitido"""
    # Arrange
    file_content = b"This is an invalid file type."
    invalid_file = io.BytesIO(file_content)
    
    # Act
    response = client.post(
        "/api/v1/documents/",
        headers=normal_user_token_headers,
        files={"file": ("test.invalid", invalid_file, "application/octet-stream")},
        data={"title": "Invalid File Type"}
    )
    
    # Assert
    assert response.status_code == 400, f"Expected status 400 but got {response.status_code}. Response: {response.text}"
    error_content = response.json()
    assert "detail" in error_content, "Response JSON should contain 'detail' key for errors"
    assert "Tipo de archivo no permitido" in error_content["detail"], f"Expected 'Tipo de archivo no permitido' in details, got {error_content['detail']}"

def test_delete_document(client, test_documents, normal_user_token_headers, mock_storage_service, mock_embedding_service):
    """Prueba para eliminar un documento"""
    # Arrange
    document_to_delete_id = str(test_documents[0].id)
    
    # Act: Delete the document
    response_delete = client.delete(
        f"/api/v1/documents/{document_to_delete_id}",
        headers=normal_user_token_headers
    )
    
    # Assert: Deletion was successful
    assert response_delete.status_code == 200, f"Expected status 200 for delete but got {response_delete.status_code}. Response: {response_delete.text}"
    delete_content = response_delete.json()
    assert "message" in delete_content, "Delete response JSON should contain 'message' key"
    assert f"Document {document_to_delete_id} and its data deleted successfully" in delete_content["message"], f"Expected success message for {document_to_delete_id}, got '{delete_content['message']}'"
    
    # Act: Verify the document no longer exists
    response_get_after_delete = client.get(
        f"/api/v1/documents/{document_to_delete_id}",
        headers=normal_user_token_headers
    )
    # Assert: Get returns 404
    assert response_get_after_delete.status_code == 404, f"Expected status 404 after delete, but got {response_get_after_delete.status_code}. Response: {response_get_after_delete.text}"

def test_delete_nonexistent_document(client, normal_user_token_headers):
    """Prueba para eliminar un documento inexistente"""
    # Arrange
    non_existent_doc_id = "00000000-0000-0000-0000-000000000000"
    
    # Act
    response = client.delete(
        f"/api/v1/documents/{non_existent_doc_id}",
        headers=normal_user_token_headers
    )
    
    # Assert
    assert response.status_code == 404, f"Expected status 404 but got {response.status_code}. Response: {response.text}"
    error_content = response.json()
    assert "detail" in error_content, "Response JSON should contain 'detail' key for errors"
    assert "Document not found" in error_content["detail"], f"Expected 'Document not found' in details, got {error_content['detail']}"

def test_add_tag(client, test_documents, normal_user_token_headers):
    """Prueba para añadir una etiqueta a un documento"""
    # Arrange
    document_to_tag_id = str(test_documents[0].id)
    tag_to_add = "new-tag"
    
    # Act: Add the tag
    response_add_tag = client.post(
        f"/api/v1/documents/{document_to_tag_id}/tag",
        headers=normal_user_token_headers,
        json={"tag": tag_to_add}
    )
    
    # Assert: Tag addition was successful
    assert response_add_tag.status_code == 200, f"Expected status 200 for add tag but got {response_add_tag.status_code}. Response: {response_add_tag.text}"
    add_tag_content = response_add_tag.json()
    assert "message" in add_tag_content, "Add tag response JSON should contain 'message' key"
    assert f"Tag '{tag_to_add}' added to document {document_to_tag_id}" in add_tag_content["message"], f"Expected success message for adding tag, got '{add_tag_content['message']}'"
    
    # Act: Verify the tag was added
    response_get_after_tag = client.get(
        f"/api/v1/documents/{document_to_tag_id}",
        headers=normal_user_token_headers
    )
    
    # Assert: Get after tag successful and tag is present
    assert response_get_after_tag.status_code == 200, f"Expected status 200 for get after tag add, got {response_get_after_tag.status_code}. Response: {response_get_after_tag.text}"
    get_content_after_tag = response_get_after_tag.json()
    assert tag_to_add in get_content_after_tag["tags"], f"Expected '{tag_to_add}' in document tags, got {get_content_after_tag['tags']}"

def test_generate_summary(client, test_documents, normal_user_token_headers, mock_llm_service):
    """Prueba para generar un resumen de un documento"""
    # Arrange
    document_to_summarize_id = str(test_documents[0].id)
    
    # Act
    response = client.get(
        f"/api/v1/documents/{document_to_summarize_id}/summary",
        headers=normal_user_token_headers
    )
    
    # Assert
    assert response.status_code == 200, f"Expected status 200 but got {response.status_code}. Response: {response.text}"
    summary_content = response.json()
    assert "summary" in summary_content, "Response JSON should contain 'summary' key"
    assert "mock summary" in summary_content["summary"].lower(), f"Expected 'mock summary' in summary, got '{summary_content['summary']}'"

def test_get_signed_download_url(client, test_documents, normal_user_token_headers, mock_storage_service):
    """Prueba para obtener URL firmada de descarga"""
    # Arrange
    document_to_download = test_documents[0]
    doc_id_str = str(document_to_download.id)
    
    # Act
    response = client.get(
        f"/api/v1/documents/{doc_id_str}/download-url",
        headers=normal_user_token_headers
    )
    
    # Assert
    assert response.status_code == 200, f"Expected status 200 but got {response.status_code}. Response: {response.text}"
    url_content = response.json()
    assert "url" in url_content, "Response JSON should contain 'url' key"
    assert "expires_at" in url_content, "Response JSON should contain 'expires_at' key"
    assert document_to_download.filename in url_content["url"], f"Expected filename '{document_to_download.filename}' in URL, got '{url_content['url']}'"

def test_get_signed_upload_url(client, normal_user_token_headers, mock_storage_service):
    """Prueba para obtener URL firmada de carga"""
    # Arrange
    upload_payload = {
        "filename": "test-upload.txt",
        "content_type": "text/plain",
        "size": 1000
    }

    # Act
    response = client.post(
        "/api/v1/documents/upload-url",
        headers=normal_user_token_headers,
        json=upload_payload
    )
    
    # Assert
    assert response.status_code == 200, f"Expected status 200 but got {response.status_code}. Response: {response.text}"
    upload_url_content = response.json()
    assert "upload_url" in upload_url_content, "Response JSON should contain 'upload_url' key"
    assert "expires_at" in upload_url_content, "Response JSON should contain 'expires_at' key"
    assert "file_path" in upload_url_content, "Response JSON should contain 'file_path' key"
    assert upload_payload["filename"] in upload_url_content["upload_url"], f"Expected '{upload_payload['filename']}' in upload_url, got '{upload_url_content['upload_url']}'"
    assert "doc_id" in upload_url_content, "Response JSON should contain 'doc_id' key"