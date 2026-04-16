import pytest
from fastapi.testclient import TestClient

def test_search_documents(client, test_documents, normal_user_token_headers, mock_embedding_service):
    """Prueba de búsqueda semántica de documentos"""
    response = client.get(
        "/api/v1/search/?query=test query",
        headers=normal_user_token_headers
    )
    
    assert response.status_code == 200
    content = response.json()
    assert isinstance(content, list)
    assert len(content) > 0
    assert "document" in content[0]
    assert "score" in content[0]
    assert "matches" in content[0]

def test_search_with_tag_filter(client, test_documents, test_tags, normal_user_token_headers, mock_embedding_service):
    """Prueba de búsqueda con filtro de etiquetas"""
    response = client.get(
        f"/api/v1/search/?query=test query&tags={test_tags[0].name}",
        headers=normal_user_token_headers
    )
    
    assert response.status_code == 200
    content = response.json()
    assert isinstance(content, list)
    # No podemos asumir cantidad específica debido al mock, pero debe devolver resultados

def test_search_with_date_filter(client, test_documents, normal_user_token_headers, mock_embedding_service):
    """Prueba de búsqueda con filtro de fechas"""
    response = client.get(
        "/api/v1/search/?query=test query&date_from=2023-01-01&date_to=2023-12-31",
        headers=normal_user_token_headers
    )
    
    assert response.status_code == 200
    content = response.json()
    assert isinstance(content, list)
    # No podemos asumir cantidad específica debido al mock, pero debe devolver resultados

def test_search_empty_query(client, normal_user_token_headers):
    """Prueba de búsqueda con consulta vacía"""
    response = client.get(
        "/api/v1/search/?query=",
        headers=normal_user_token_headers
    )
    
    assert response.status_code == 422  # Validation error

def test_ask_documents(client, test_documents, normal_user_token_headers, mock_embedding_service, mock_emma_service):
    """Prueba para hacer preguntas sobre documentos"""
    doc_ids = [str(doc.id) for doc in test_documents[:2]]

    response = client.post(
        "/api/v1/search/ask",
        headers=normal_user_token_headers,
        json={
            "question": "What is the main topic?",
            "doc_ids": doc_ids
        }
    )

    assert response.status_code == 200
    content = response.json()
    assert "answer" in content
    assert "mock answer" in content["answer"].lower()

def test_ask_without_documents(client, normal_user_token_headers, mock_embedding_service, mock_emma_service):
    """Prueba para hacer preguntas sin especificar documentos"""
    response = client.post(
        "/api/v1/search/ask",
        headers=normal_user_token_headers,
        json={
            "question": "What is the main topic?",
            "doc_ids": []
        }
    )

    assert response.status_code == 200
    content = response.json()
    assert "answer" in content
    # Debería buscar en todos los documentos accesibles