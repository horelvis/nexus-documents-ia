import pytest
import io
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.storage_service import StorageService

class MockBlob:
    def __init__(self, name, exists=True):
        self.name = name
        self._exists = exists
        self.size = 1024
        self.updated = datetime.utcnow()
        self.content_type = "text/plain"
        self.metadata = {"doc_id": "test-doc-1"}
    
    def exists(self):
        return self._exists
    
    def upload_from_file(self, file_obj, rewind=True):
        # Método mock para simular carga
        return True
    
    def download_as_bytes(self):
        # Método mock para simular descarga
        return b"Test file content"
    
    def delete(self):
        # Método mock para simular eliminación
        return True
    
    def generate_signed_url(self, version="v4", expiration=None, method=None, content_type=None):
        # Método mock para generar URL firmada
        method_str = method or "GET"
        content_type_str = f"&content-type={content_type}" if content_type else ""
        return f"https://storage.googleapis.com/{self.name}?method={method_str}{content_type_str}&expiry={expiration}"

class MockBucket:
    def __init__(self, name):
        self.name = name
    
    def blob(self, name):
        return MockBlob(name)
    
    def list_blobs(self, prefix=""):
        # Devolver lista de blobs mock
        return [
            MockBlob(f"{prefix}file1.txt"),
            MockBlob(f"{prefix}file2.txt"),
            MockBlob(f"{prefix}subfolder/file3.txt")
        ]

class MockGCSClient:
    def __init__(self):
        self.buckets = {
            "test-bucket-test-tenant": MockBucket("test-bucket-test-tenant")
        }
    
    def get_bucket(self, name):
        if name in self.buckets:
            return self.buckets[name]
        raise Exception(f"Bucket {name} not found")
    
    def create_bucket(self, name, location=None):
        bucket = MockBucket(name)
        self.buckets[name] = bucket
        return bucket

def test_init_storage_service(monkeypatch):
    """Prueba para inicializar el servicio de almacenamiento"""
    # Mock para el cliente GCS
    monkeypatch.setattr("google.cloud.storage.Client", lambda **kwargs: MockGCSClient())
    
    # Ejecutar prueba
    storage_service = StorageService(tenant_id="test-tenant")
    
    assert storage_service.tenant_id == "test-tenant"
    assert storage_service.bucket_name == "test-bucket-test-tenant"

def test_generate_upload_signed_url(monkeypatch):
    """Prueba para generar URL firmada para carga"""
    # Mock para el cliente GCS
    monkeypatch.setattr("google.cloud.storage.Client", lambda **kwargs: MockGCSClient())
    
    # Ejecutar prueba
    storage_service = StorageService(tenant_id="test-tenant")
    url, expires_at = storage_service.generate_upload_signed_url(
        object_name="test/file.txt",
        content_type="text/plain"
    )
    
    assert isinstance(url, str)
    assert "https://storage.googleapis.com/test/file.txt" in url
    assert "method=PUT" in url
    assert "content-type=text/plain" in url
    assert isinstance(expires_at, datetime)
    assert expires_at > datetime.utcnow()

def test_generate_download_signed_url(monkeypatch):
    """Prueba para generar URL firmada para descarga"""
    # Mock para el cliente GCS
    monkeypatch.setattr("google.cloud.storage.Client", lambda **kwargs: MockGCSClient())
    
    # Ejecutar prueba
    storage_service = StorageService(tenant_id="test-tenant")
    url, expires_at = storage_service.generate_download_signed_url(
        object_name="test/file.txt"
    )
    
    assert isinstance(url, str)
    assert "https://storage.googleapis.com/test/file.txt" in url
    assert "method=GET" in url
    assert isinstance(expires_at, datetime)
    assert expires_at > datetime.utcnow()

def test_upload_file(monkeypatch):
    """Prueba para subir archivo"""
    # Mock para el cliente GCS
    monkeypatch.setattr("google.cloud.storage.Client", lambda **kwargs: MockGCSClient())
    
    # Ejecutar prueba
    storage_service = StorageService(tenant_id="test-tenant")
    
    # Archivo de prueba
    file_content = b"Test file content"
    file = io.BytesIO(file_content)
    
    result = storage_service.upload_file(
        file=file,
        object_name="test/file.txt",
        metadata={"doc_id": "test-doc-1"}
    )
    
    assert result is True

def test_download_file(monkeypatch):
    """Prueba para descargar archivo"""
    # Mock para el cliente GCS
    monkeypatch.setattr("google.cloud.storage.Client", lambda **kwargs: MockGCSClient())
    
    # Ejecutar prueba
    storage_service = StorageService(tenant_id="test-tenant")
    content = storage_service.download_file(object_name="test/file.txt")
    
    assert content == b"Test file content"

def test_download_nonexistent_file(monkeypatch):
    """Prueba para descargar archivo inexistente"""
    # Mock para el cliente GCS con blob inexistente
    mock_gcs_client = MockGCSClient()
    mock_bucket = mock_gcs_client.buckets["test-bucket-test-tenant"]
    
    # Sobrescribir método blob para devolver un blob que no existe
    def mock_blob(name):
        return MockBlob(name, exists=False)
    
    mock_bucket.blob = mock_blob
    
    monkeypatch.setattr("google.cloud.storage.Client", lambda **kwargs: mock_gcs_client)
    
    # Ejecutar prueba
    storage_service = StorageService(tenant_id="test-tenant")
    content = storage_service.download_file(object_name="nonexistent/file.txt")
    
    assert content is None

def test_delete_file(monkeypatch):
    """Prueba para eliminar archivo"""
    # Mock para el cliente GCS
    monkeypatch.setattr("google.cloud.storage.Client", lambda **kwargs: MockGCSClient())
    
    # Ejecutar prueba
    storage_service = StorageService(tenant_id="test-tenant")
    result = storage_service.delete_file(object_name="test/file.txt")
    
    assert result is True

def test_list_files(monkeypatch):
    """Prueba para listar archivos"""
    # Mock para el cliente GCS
    monkeypatch.setattr("google.cloud.storage.Client", lambda **kwargs: MockGCSClient())
    
    # Ejecutar prueba
    storage_service = StorageService(tenant_id="test-tenant")
    files = storage_service.list_files(prefix="test/")
    
    assert isinstance(files, list)
    assert len(files) == 3
    assert "name" in files[0]
    assert "size" in files[0]
    assert "updated" in files[0]
    assert "test/file1.txt" in files[0]["name"] or "test/file2.txt" in files[0]["name"] or "test/subfolder/file3.txt" in files[0]["name"]