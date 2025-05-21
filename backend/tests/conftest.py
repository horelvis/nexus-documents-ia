import os
from app.db.base_class import Base
import pytest
from typing import Dict, Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import uuid
from datetime import datetime

from app.main import app
from app.db.database import get_db

from app.core.security import get_password_hash
from app.db.models import User, Tenant, Document, Tag, DocumentChunk
from app.services.auth_service import AuthService

# Crear base de datos en memoria para tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Fixture para crear la base de datos
@pytest.fixture(scope="function")
def db():
    # Crear tablas
    Base.metadata.create_all(bind=engine)
    
    # Crear sesión
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        
    # Limpiar tablas después de cada test
    Base.metadata.drop_all(bind=engine)

# Fixture para el cliente de pruebas
@pytest.fixture(scope="function")
def client(db):
    # Dependencia de base de datos override
    def override_get_db():
        try:
            yield db
        finally:
            pass
    
    # Reemplazar la dependencia en la aplicación
    app.dependency_overrides[get_db] = override_get_db
    
    # Crear cliente
    with TestClient(app) as c:
        yield c
    
    # Restaurar dependencias
    app.dependency_overrides = {}

# Fixture para crear un tenant de prueba
@pytest.fixture(scope="function")
def test_tenant(db):
    tenant_id = uuid.uuid4()
    tenant = Tenant(
        id=tenant_id,
        name="test-tenant",
        description="Tenant for testing",
        bucket_name="test-bucket",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant

# Fixture para crear un usuario normal
@pytest.fixture(scope="function")
def test_user(db, test_tenant):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="test@example.com",
        hashed_password=get_password_hash("password"),
        full_name="Test User",
        is_active=True,
        is_superuser=False,
        tenant_id=test_tenant.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

# Fixture para crear un usuario administrador
@pytest.fixture(scope="function")
def test_superuser(db, test_tenant):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="admin@example.com",
        hashed_password=get_password_hash("adminpassword"),
        full_name="Admin User",
        is_active=True,
        is_superuser=True,
        tenant_id=test_tenant.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

# Fixture para obtener token de usuario normal
@pytest.fixture(scope="function")
def normal_user_token_headers(test_user):
    token = AuthService.create_access_token(
        subject=str(test_user.id),
        tenant_id=str(test_user.tenant_id)
    )
    return {"Authorization": f"Bearer {token}"}

# Fixture para obtener token de administrador
@pytest.fixture(scope="function")
def superuser_token_headers(test_superuser):
    token = AuthService.create_access_token(
        subject=str(test_superuser.id),
        tenant_id=str(test_superuser.tenant_id)
    )
    return {"Authorization": f"Bearer {token}"}

# Fixture para crear tags de prueba
@pytest.fixture(scope="function")
def test_tags(db, test_tenant):
    tags = []
    for name in ["test-tag1", "test-tag2", "test-tag3"]:
        tag = Tag(name=name, tenant_id=test_tenant.id)
        db.add(tag)
        tags.append(tag)
    
    db.commit()
    for tag in tags:
        db.refresh(tag)
    
    return tags

# Fixture para crear documentos de prueba
@pytest.fixture(scope="function")
def test_documents(db, test_user, test_tenant, test_tags):
    documents = []
    
    for i in range(3):
        doc_id = uuid.uuid4()
        document = Document(
            id=doc_id,
            title=f"Test Document {i+1}",
            description=f"Description for test document {i+1}",
            filename=f"test_document_{i+1}.txt",
            file_path=f"documents/{doc_id}/test_document_{i+1}.txt",
            file_type="txt",
            file_size=1000,
            tenant_id=test_tenant.id,
            created_by=test_user.id,
            indexed=1,  # Indexado
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Añadir tags a los documentos
        for tag in test_tags[:2]:
            document.tags.append(tag)
        
        # Añadir chunks a los documentos
        for j in range(2):
            chunk = DocumentChunk(
                document_id=doc_id,
                chunk_index=j,
                content=f"Content for document {i+1}, chunk {j+1}"
            )
            db.add(chunk)
        
        documents.append(document)
        db.add(document)
    
    db.commit()
    for doc in documents:
        db.refresh(doc)
    
    return documents

# Mock para el servicio LLM
@pytest.fixture(scope="function")
def mock_llm_service(monkeypatch):
    class MockLLMService:
        def _call_ollama_api(self, prompt, system_prompt=None, temperature=0.5, max_tokens=1000, stream=False):
            return "This is a mock response from the LLM service."
        
        def summarize_text(self, text, max_length=500):
            return "This is a mock summary of the text."
        
        def suggest_tags(self, text, num_tags=5):
            return ["tag1", "tag2", "tag3", "tag4", "tag5"]
        
        def extract_metadata(self, text):
            return {
                "título": "Mock Title",
                "autor": "Mock Author",
                "fecha": "2023-01-01",
                "categoría": "Mock Category",
                "entidades": ["Entity1", "Entity2"]
            }
        
        def answer_question(self, question, context):
            return f"Mock answer to the question: {question}"
        
        def classify_document(self, text, categories):
            return categories[0] if categories else "Mock Category"
    
    # Aplicar el mock
    from app.services import llm_service
    monkeypatch.setattr(llm_service, "LLMService", MockLLMService)
    
    return MockLLMService()

# Mock para el servicio de almacenamiento
@pytest.fixture(scope="function")
def mock_storage_service(monkeypatch):
    class MockStorageService:
        def __init__(self, tenant_id=None):
            self.tenant_id = tenant_id or "test-tenant"
        
        def generate_upload_signed_url(self, object_name, content_type, expiration=None):
            from datetime import datetime, timedelta
            expires_at = datetime.now() + timedelta(minutes=5)
            return f"https://mock-storage.example.com/upload/{object_name}", expires_at
        
        def generate_download_signed_url(self, object_name, expiration=None):
            from datetime import datetime, timedelta
            expires_at = datetime.now() + timedelta(minutes=5)
            return f"https://mock-storage.example.com/download/{object_name}", expires_at
        
        def upload_file(self, file, object_name, metadata=None):
            return True
        
        def download_file(self, object_name):
            return b"Mock file content"
        
        def delete_file(self, object_name):
            return True
        
        def list_files(self, prefix=""):
            return [
                {"name": f"{prefix}file1.txt", "size": 100, "updated": datetime.utcnow()},
                {"name": f"{prefix}file2.txt", "size": 200, "updated": datetime.utcnow()}
            ]
    
    # Aplicar el mock
    from app.services import storage_service
    monkeypatch.setattr(storage_service, "StorageService", MockStorageService)
    
    return MockStorageService()

# Mock para el servicio de embeddings
@pytest.fixture(scope="function")
def mock_embedding_service(monkeypatch):
    import numpy as np
    
    class MockEmbeddingService:
        def __init__(self, tenant_id=None):
            self.tenant_id = tenant_id or "test-tenant"
        
        def get_embedding(self, text):
            # Generar un vector aleatorio de 1536 dimensiones
            return np.random.rand(1536).astype(np.float32)
        
        def chunk_text(self, text):
            # Dividir el texto en chunks simplificados
            chunks = []
            for i in range(1, 4):
                chunks.append({
                    "text": f"Chunk {i} of the text",
                    "metadata": {"is_paragraph_boundary": i % 2 == 0}
                })
            return chunks
        
        def add_document(self, doc_id, text, metadata):
            return True
        
        def search(self, query, limit=5, filters=None):
            # Devolver resultados ficticios
            results = []
            for i in range(1, limit + 1):
                results.append({
                    "score": 0.9 - (i * 0.1),
                    "metadata": {
                        "doc_id": f"doc-{i}",
                        "chunk_id": i,
                        "chunk_text": f"Chunk {i} matching the query",
                        "title": f"Document {i}"
                    }
                })
            return results
        
        def delete_document(self, doc_id):
            return True
    
    # Aplicar el mock
    from app.services import embedding_service
    monkeypatch.setattr(embedding_service, "EmbeddingService", MockEmbeddingService)
    
    return MockEmbeddingService()

# Mock para el servicio vectorial
@pytest.fixture(scope="function")
def mock_vector_service(monkeypatch):
    import numpy as np
    
    class MockVectorService:
        def __init__(self, tenant_id=None):
            self.tenant_id = tenant_id or "test-tenant"
        
        def add_document_vectors(self, doc_id, vectors, metadatas):
            return [f"point-{i+1}" for i in range(len(vectors))]
        
        def search_similar(self, query_vector, limit=10, filter_by=None):
            results = []
            for i in range(1, limit + 1):
                results.append({
                    "score": 0.9 - (i * 0.1),
                    "metadata": {
                        "doc_id": f"doc-{i}",
                        "chunk_id": i,
                        "chunk_text": f"Chunk {i} matching the query",
                        "title": f"Document {i}"
                    }
                })
            return results
        
        def delete_document_vectors(self, doc_id):
            return True
        
        def get_document_vectors(self, doc_id):
            return [{
                "id": f"point-{i+1}",
                "vector": np.random.rand(1536),
                "metadata": {
                    "doc_id": doc_id,
                    "chunk_id": i,
                    "chunk_text": f"Chunk {i} of document {doc_id}"
                }
            } for i in range(3)]
    
    # Aplicar el mock
    from app.services import vector_service
    monkeypatch.setattr(vector_service, "VectorService", MockVectorService)
    
    return MockVectorService()