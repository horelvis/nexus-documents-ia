import pytest
from fastapi.testclient import TestClient

def test_chat_with_documents(client, test_documents, normal_user_token_headers, mock_embedding_service, mock_llm_service):
    """Prueba de chat con documentos"""
    doc_ids = [str(doc.id) for doc in test_documents[:2]]
    
    response = client.post(
        "/api/v1/chat/",
        headers=normal_user_token_headers,
        json={
            "question": "What is the main idea?",
            "doc_ids": doc_ids
        }
    )
    
    assert response.status_code == 200
    content = response.json()
    assert "answer" in content
    assert content["answer"] is not None
    assert "mock answer" in content["answer"].lower()

def test_suggest_tags(client, normal_user_token_headers, mock_llm_service):
    """Prueba de sugerencia de etiquetas"""
    response = client.post(
        "/api/v1/chat/suggest-tags",
        headers=normal_user_token_headers,
        json={
            "text": "This is a sample text to suggest tags for.",
            "num_tags": 5
        }
    )
    
    assert response.status_code == 200
    content = response.json()
    assert "suggested_tags" in content
    assert isinstance(content["suggested_tags"], list)
    assert len(content["suggested_tags"]) == 5

def test_extract_metadata(client, normal_user_token_headers, mock_llm_service):
    """Prueba de extracción de metadatos"""
    response = client.post(
        "/api/v1/chat/extract-metadata",
        headers=normal_user_token_headers,
        json={
            "text": "This is a sample text to extract metadata from. Author: John Doe. Date: 2023-01-01."
        }
    )
    
    assert response.status_code == 200
    content = response.json()
    assert "metadata" in content
    assert isinstance(content["metadata"], dict)
    assert "título" in content["metadata"]