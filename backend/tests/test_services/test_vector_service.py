import pytest
import numpy as np
from unittest.mock import MagicMock, patch

from app.services.vector_service import VectorService


class MockQdrantClient:
    def __init__(self):
        self.collections = {}
        self.points = {}
    
    def get_collections(self):
        class Collections:
            def __init__(self, names):
                self.collections = [type('obj', (object,), {'name': n}) for n in names]
        
        return Collections(list(self.collections.keys()))
    
    def create_collection(self, collection_name, vectors_config):
        self.collections[collection_name] = vectors_config
        self.points[collection_name] = []
    
    def upsert(self, collection_name, points):
        if collection_name not in self.points:
            self.points[collection_name] = []
        
        for point in points:
            self.points[collection_name].append({
                "id": point.id,
                "vector": point.vector,
                "payload": point.payload
            })
        
        return True
    
    def search(self, collection_name, query_vector, limit, query_filter=None):
        class SearchResult:
            def __init__(self, score, payload):
                self.score = score
                self.payload = payload
        
        # Simular resultados de búsqueda
        results = []
        for i in range(min(limit, len(self.points.get(collection_name, [])))):
            results.append(SearchResult(
                score=0.9 - (i * 0.1),
                payload={"doc_id": f"doc-{i+1}", "chunk_id": i, "chunk_text": f"Chunk {i+1}"}
            ))
        
        return results
    
    def delete(self, collection_name, points_selector):
        # Simulación simple de eliminación
        return True
    
    def scroll(self, collection_name, scroll_filter, limit):
        class Point:
            def __init__(self, id, vector, payload):
                self.id = id
                self.vector = vector
                self.payload = payload
        
        points = []
        for i in range(min(limit, 5)):
            points.append(Point(
                id=f"point-{i+1}",
                vector=np.zeros(1536).tolist(),
                payload={"doc_id": "test-doc", "chunk_id": i}
            ))
        
        return [points]

def test_init_vector_service(monkeypatch):
    """Prueba para inicializar el servicio vectorial"""
    # Mock para el cliente Qdrant
    monkeypatch.setattr("qdrant_client.QdrantClient", lambda **kwargs: MockQdrantClient())
    
    # Ejecutar prueba
    vector_service = VectorService(tenant_id="test-tenant")
    
    assert vector_service.tenant_id == "test-tenant"
    assert vector_service.collection_name == "documents_test-tenant"

def test_init_collection_new(monkeypatch):
    """Prueba para inicializar una nueva colección"""
    # Mock para el cliente Qdrant
    mock_qdrant = MockQdrantClient()
    monkeypatch.setattr("qdrant_client.QdrantClient", lambda **kwargs: mock_qdrant)
    
    # Ejecutar prueba
    vector_service = VectorService(tenant_id="test-tenant")
    
    # Verificar que la colección se creó
    assert "documents_test-tenant" in mock_qdrant.collections

def test_init_collection_existing(monkeypatch):
    """Prueba para usar una colección existente"""
    # Mock para el cliente Qdrant con colección existente
    mock_qdrant = MockQdrantClient()
    mock_qdrant.collections["documents_test-tenant"] = {}
    monkeypatch.setattr("qdrant_client.QdrantClient", lambda **kwargs: mock_qdrant)
    
    # Ejecutar prueba
    vector_service = VectorService(tenant_id="test-tenant")
    
    # Verificar que la colección existe
    assert "documents_test-tenant" in mock_qdrant.collections

def test_add_document_vectors(monkeypatch):
    """Prueba para añadir vectores de un documento"""
    # Mock para el cliente Qdrant
    mock_qdrant = MockQdrantClient()
    monkeypatch.setattr("qdrant_client.QdrantClient", lambda **kwargs: mock_qdrant)
    
    # Ejecutar prueba
    vector_service = VectorService(tenant_id="test-tenant")
    
    # Crear vectores y metadatos de prueba
    vectors = [np.random.rand(1536) for _ in range(3)]
    metadatas = [
        {"chunk_id": 0, "chunk_text": "Chunk 1"},
        {"chunk_id": 1, "chunk_text": "Chunk 2"},
        {"chunk_id": 2, "chunk_text": "Chunk 3"}
    ]
    
    point_ids = vector_service.add_document_vectors(
        doc_id="test-doc-1",
        vectors=vectors,
        metadatas=metadatas
    )
    
    # Verificar que devuelve IDs de puntos
    assert isinstance(point_ids, list)
    assert len(point_ids) == 3
    
    # Verificar que se añadieron los puntos
    assert len(mock_qdrant.points["documents_test-tenant"]) == 3
    
    # Verificar que doc_id se añadió a los metadatos
    for point in mock_qdrant.points["documents_test-tenant"]:
        assert point["payload"]["doc_id"] == "test-doc-1"

def test_search_similar(monkeypatch):
    """Prueba para buscar vectores similares"""
    # Mock para el cliente Qdrant
    mock_qdrant = MockQdrantClient()
    # Añadir algunos puntos
    mock_qdrant.collections["documents_test-tenant"] = {}
    mock_qdrant.points["documents_test-tenant"] = []
    monkeypatch.setattr("qdrant_client.QdrantClient", lambda **kwargs: mock_qdrant)
    
    # Ejecutar prueba
    vector_service = VectorService(tenant_id="test-tenant")
    
    # Crear vector de consulta
    query_vector = np.random.rand(1536)
    
    results = vector_service.search_similar(
        query_vector=query_vector,
        limit=5
    )
    
    # La implementación mock devuelve resultados ficticios
    assert isinstance(results, list)
    # Verificar formato de resultados
    if results:  # El mock podría devolver lista vacía
        assert "score" in results[0]
        assert "metadata" in results[0]

def test_search_with_filter(monkeypatch):
    """Prueba para buscar con filtros"""
    # Mock para el cliente Qdrant
    mock_qdrant = MockQdrantClient()
    # Añadir algunos puntos
    mock_qdrant.collections["documents_test-tenant"] = {}
    mock_qdrant.points["documents_test-tenant"] = []
    monkeypatch.setattr("qdrant_client.QdrantClient", lambda **kwargs: mock_qdrant)
    
    # Mock para search
    mock_search = MagicMock(return_value=[])
    monkeypatch.setattr(mock_qdrant, "search", mock_search)
    
    # Ejecutar prueba
    vector_service = VectorService(tenant_id="test-tenant")
    
    # Crear vector de consulta
    query_vector = np.random.rand(1536)
    
    # Buscar con filtro
    vector_service.search_similar(
        query_vector=query_vector,
        limit=5,
        filter_by={"doc_id": "test-doc-1"}
    )
    
    # Verificar que se llamó a search con el filtro
    mock_search.assert_called_once()
    args, kwargs = mock_search.call_args
    assert "query_filter" in kwargs

def test_delete_document_vectors(monkeypatch):
    """Prueba para eliminar vectores de un documento"""
    # Mock para el cliente Qdrant
    mock_qdrant = MockQdrantClient()
    # Añadir algunos puntos
    mock_qdrant.collections["documents_test-tenant"] = {}
    mock_qdrant.points["documents_test-tenant"] = []
    monkeypatch.setattr("qdrant_client.QdrantClient", lambda **kwargs: mock_qdrant)
    
    # Mock para delete
    mock_delete = MagicMock(return_value=True)
    monkeypatch.setattr(mock_qdrant, "delete", mock_delete)
    
    # Ejecutar prueba
    vector_service = VectorService(tenant_id="test-tenant")
    
    result = vector_service.delete_document_vectors(doc_id="test-doc-1")
    
    assert result is True
    # Verificar que se llamó a delete
    mock_delete.assert_called_once()

def test_get_document_vectors(monkeypatch):
    """Prueba para obtener vectores de un documento"""
    # Mock para el cliente Qdrant
    mock_qdrant = MockQdrantClient()
    # Añadir algunos puntos
    mock_qdrant.collections["documents_test-tenant"] = {}
    mock_qdrant.points["documents_test-tenant"] = []
    monkeypatch.setattr("qdrant_client.QdrantClient", lambda **kwargs: mock_qdrant)
    
    # Ejecutar prueba
    vector_service = VectorService(tenant_id="test-tenant")
    
    vectors = vector_service.get_document_vectors(doc_id="test-doc")
    
    assert isinstance(vectors, list)
    # El mock devuelve 5 vectores
    assert len(vectors) == 5
    # Verificar estructura
    if vectors:
        assert "id" in vectors[0]
        assert "vector" in vectors[0]
        assert "metadata" in vectors[0]