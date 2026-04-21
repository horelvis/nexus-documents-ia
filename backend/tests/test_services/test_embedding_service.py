import pytest
import numpy as np
from unittest.mock import MagicMock

from app.services.embedding_service import EmbeddingService


def test_get_embedding(monkeypatch):
    """Prueba para obtener embedding"""
    # Mock para requests.post
    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json_data = json_data
        
        def json(self):
            return self._json_data
    
    # Crear vector de embedding aleatorio
    random_embedding = np.random.rand(1536).tolist()
    
    def mock_post(*args, **kwargs):
        return MockResponse(200, {"embedding": random_embedding})
    
    # Aplicar mock
    import requests
    monkeypatch.setattr(requests, "post", mock_post)
    
    # Ejecutar prueba
    embedding_service = EmbeddingService()
    result = embedding_service.get_embedding("Test text")
    
    assert isinstance(result, np.ndarray)
    assert result.shape == (1536,)
    assert np.array_equal(result, np.array(random_embedding))

def test_chunk_text():
    """Prueba para dividir texto en chunks"""
    embedding_service = EmbeddingService()
    
    # Texto simple para prueba
    text = "This is the first paragraph.\n\nThis is the second paragraph.\n\nThis is the third paragraph."
    
    result = embedding_service.chunk_text(text)
    
    assert isinstance(result, list)
    assert len(result) > 0
    
    # Verificar que cada chunk tiene el formato correcto
    for chunk in result:
        assert "text" in chunk
        assert "metadata" in chunk
        assert isinstance(chunk["text"], str)
        assert isinstance(chunk["metadata"], dict)
        assert "is_paragraph_boundary" in chunk["metadata"]

def test_add_document(monkeypatch):
    """Prueba para añadir documento al vector store"""
    embedding_service = EmbeddingService()
    
    # Mock para chunk_text
    def mock_chunk_text(text):
        return [
            {"text": "Chunk 1", "metadata": {"is_paragraph_boundary": True}},
            {"text": "Chunk 2", "metadata": {"is_paragraph_boundary": False}}
        ]
    
    monkeypatch.setattr(embedding_service, "chunk_text", mock_chunk_text)
    
    # Mock para get_embedding
    def mock_get_embedding(text):
        return np.random.rand(1536)
    
    monkeypatch.setattr(embedding_service, "get_embedding", mock_get_embedding)
    
    # Mock del vector_service
    embedding_service.vector_service = MagicMock()
    embedding_service.vector_service.add_document_vectors.return_value = ["point1", "point2"]
    
    # Ejecutar prueba
    result = embedding_service.add_document(
        doc_id="test-doc-1",
        text="Test document text",
        metadata={"title": "Test Document"}
    )
    
    assert result is True
    # Verificar que se llamó al método add_document_vectors
    embedding_service.vector_service.add_document_vectors.assert_called_once()
    # Verificar que se pasaron 2 vectores (uno por cada chunk)
    args, kwargs = embedding_service.vector_service.add_document_vectors.call_args
    assert len(args[1]) == 2  # vectores
    assert len(args[2]) == 2  # metadatos

def test_search(monkeypatch):
    """Prueba para buscar en el vector store"""
    embedding_service = EmbeddingService()
    
    # Mock para get_embedding
    def mock_get_embedding(text):
        return np.random.rand(1536)
    
    monkeypatch.setattr(embedding_service, "get_embedding", mock_get_embedding)
    
    # Mock del vector_service
    embedding_service.vector_service = MagicMock()
    embedding_service.vector_service.search_similar.return_value = [
        {
            "score": 0.9,
            "metadata": {
                "doc_id": "test-doc-1",
                "chunk_id": 1,
                "chunk_text": "This is a matching chunk"
            }
        }
    ]
    
    # Ejecutar prueba
    result = embedding_service.search(
        query="test query",
        limit=5,
        filters={"user_id": "test-user"}
    )
    
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["score"] == 0.9
    assert result[0]["metadata"]["doc_id"] == "test-doc-1"
    
    # Verificar que se llamó al método search_similar con los parámetros correctos
    embedding_service.vector_service.search_similar.assert_called_once()
    args, kwargs = embedding_service.vector_service.search_similar.call_args
    assert kwargs["limit"] == 5
    assert kwargs["filter_by"] == {"user_id": "test-user"}

def test_delete_document(monkeypatch):
    """Prueba para eliminar documento del vector store"""
    embedding_service = EmbeddingService()
    
    # Mock del vector_service
    embedding_service.vector_service = MagicMock()
    embedding_service.vector_service.delete_document_vectors.return_value = True
    
    # Ejecutar prueba
    result = embedding_service.delete_document(doc_id="test-doc-1")
    
    assert result is True
    # Verificar que se llamó al método delete_document_vectors
    embedding_service.vector_service.delete_document_vectors.assert_called_once_with(doc_id="test-doc-1")

def test_handle_errors_gracefully():
    """Prueba para manejar errores de manera elegante"""
    embedding_service = EmbeddingService()
    
    # Prueba con texto vacío
    result = embedding_service.chunk_text("")
    assert result == []
    
    # Prueba con error en search (vector_service no inicializado)
    embedding_service.vector_service = None
    result = embedding_service.search("test query")
    assert result == []