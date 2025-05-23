import os
import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import uuid
from datetime import datetime

# CRITICAL: Import all models to register with Base.metadata
from app.db.base_class import Base
from app.db.models import User, Tenant, Document, Tag, DocumentChunk

from app.main import app
from app.db.database import get_db
from app.core.security import get_password_hash
from app.services.auth_service import AuthService

# Configuración de base de datos para tests
TESTING = os.getenv("TESTING", "false").lower() == "true"

if TESTING:
    POSTGRES_SERVER = os.getenv("POSTGRES_SERVER", "test-db")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "test_user")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "test_password")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "test_db")
    SQLALCHEMY_DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_SERVER}/{POSTGRES_DB}"
else:
    SQLALCHEMY_DATABASE_URL = "postgresql://test_user:test_password@localhost:5432/test_db"

print(f"🔧 Test DB URL: {SQLALCHEMY_DATABASE_URL}")

# Crear engine
engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True, echo=False)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

print(f"🔍 Modelos registrados: {list(Base.metadata.tables.keys())}")

# Fixture para crear la base de datos
@pytest.fixture(scope="function")
def db():
    """
    Crea una sesión de base de datos para cada test.
    SOLUCIÓN: Usar una sesión simple SIN transacciones que interfieran.
    """
    print("🔧 Setting up test database...")
    
    # PASO 1: Crear todas las tablas de forma limpia
    try:
        print("🧹 Cleaning and creating fresh tables...")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        
        # Verificar que las tablas se crearon
        with engine.connect() as verify_conn:
            result = verify_conn.execute(text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' ORDER BY table_name
            """))
            created_tables = [row[0] for row in result.fetchall()]
            print(f"✅ Tables confirmed: {created_tables}")
            
            if 'users' not in created_tables or 'tenants' not in created_tables:
                raise Exception(f"❌ Required tables missing! Found: {created_tables}")
                
    except Exception as e:
        print(f"❌ FATAL ERROR creating tables: {e}")
        raise
    
    # PASO 2: Crear sesión simple (SIN transacciones complejas)
    session = TestingSessionLocal()
    
    try:
        # Test simple para verificar que la sesión funciona
        test_count = session.execute(text("SELECT COUNT(*) FROM users")).scalar()
        print(f"✅ Database session working (users: {test_count})")
        
        yield session
        
    except Exception as e:
        print(f"❌ Error in database session: {e}")
        session.rollback()
        raise
    finally:
        print("🧹 Cleaning up session...")
        session.close()
        
        # Limpiar al final
        try:
            Base.metadata.drop_all(bind=engine)
            print("✅ Database cleaned")
        except Exception as e:
            print(f"⚠️ Warning during cleanup: {e}")

# Fixture para el cliente de pruebas
@pytest.fixture(scope="function")
def client(db):
    """Cliente de pruebas con base de datos mockeada"""
    def override_get_db():
        try:
            yield db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as c:
        print("🔧 Test client ready")
        yield c
    
    app.dependency_overrides = {}

# Fixture para crear un tenant de prueba
@pytest.fixture(scope="function")
def test_tenant(db):
    """Crea un tenant de prueba"""
    print("🔧 Creating test tenant...")
    
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
    print(f"✅ Tenant created: {tenant.name} ({tenant.id})")
    return tenant

# Fixture para crear un usuario normal
@pytest.fixture(scope="function")
def test_user(db, test_tenant):
    """Crea un usuario normal de prueba"""
    print("🔧 Creating test user...")
    
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
    print(f"✅ User created: {user.email} (superuser: {user.is_superuser})")
    return user

# Fixture para crear un usuario administrador
@pytest.fixture(scope="function")
def test_superuser(db, test_tenant):
    """Crea un usuario administrador de prueba"""
    print("🔧 Creating test superuser...")
    
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="admin@example.com",
        hashed_password=get_password_hash("adminpassword"),
        full_name="Admin User",
        is_active=True,
        is_superuser=True,  # ✅ CRITICAL
        tenant_id=test_tenant.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"✅ Superuser created: {user.email} (superuser: {user.is_superuser})")
    return user

# Fixture para obtener token de usuario normal
@pytest.fixture(scope="function")
def normal_user_token_headers(test_user):
    """Headers de autorización para usuario normal"""
    token = AuthService.create_access_token(
        subject=str(test_user.id),
        tenant_id=str(test_user.tenant_id)
    )
    return {"Authorization": f"Bearer {token}"}

# Fixture para obtener token de administrador
@pytest.fixture(scope="function")
def superuser_token_headers(test_superuser):
    """Headers de autorización para administrador"""
    token = AuthService.create_access_token(
        subject=str(test_superuser.id),
        tenant_id=str(test_superuser.tenant_id)
    )
    return {"Authorization": f"Bearer {token}"}

# Fixture para crear tags de prueba
@pytest.fixture(scope="function")
def test_tags(db, test_tenant):
    """Crea tags de prueba"""
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
    """Crea documentos de prueba"""
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
            indexed=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        for tag in test_tags[:2]:
            document.tags.append(tag)
        
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

# Mock fixtures simplificados
@pytest.fixture(scope="function")
def mock_llm_service(monkeypatch):
    """Mock del servicio LLM para tests"""
    class MockLLMService:
        def summarize_text(self, text, max_length=500):
            return "This is a mock summary of the text."
        def suggest_tags(self, text, num_tags=5):
            return ["tag1", "tag2", "tag3", "tag4", "tag5"]
        def answer_question(self, question, context):
            return f"Mock answer to the question: {question}"
    
    from app.services import llm_service
    monkeypatch.setattr(llm_service, "LLMService", MockLLMService)
    return MockLLMService()

@pytest.fixture(scope="function")
def mock_storage_service(monkeypatch):
    """Mock del servicio de almacenamiento para tests"""
    class MockStorageService:
        def __init__(self, tenant_id=None):
            self.tenant_id = tenant_id or "test-tenant"
        def upload_file(self, file, object_name, metadata=None):
            return True
        def delete_file(self, object_name):
            return True
        def generate_download_signed_url(self, object_name, expiration=None):
            from datetime import datetime, timedelta
            expires_at = datetime.now() + timedelta(minutes=5)
            return f"https://mock-storage.example.com/download/{object_name}", expires_at
    
    from app.services import storage_service
    monkeypatch.setattr(storage_service, "StorageService", MockStorageService)
    return MockStorageService()

@pytest.fixture(scope="function")
def mock_embedding_service(monkeypatch):
    """Mock del servicio de embeddings para tests"""
    class MockEmbeddingService:
        def __init__(self, tenant_id=None):
            self.tenant_id = tenant_id or "test-tenant"
        def chunk_text(self, text):
            return [{"text": f"Chunk {i}", "metadata": {"is_paragraph_boundary": True}} for i in range(1, 4)]
        def add_document(self, doc_id, text, metadata):
            return True
        def search(self, query, limit=5, filters=None):
            return [{"score": 0.9, "metadata": {"doc_id": "doc-1", "chunk_text": "Mock chunk"}}]
        def delete_document(self, doc_id):
            return True
    
    from app.services import embedding_service
    monkeypatch.setattr(embedding_service, "EmbeddingService", MockEmbeddingService)
    return MockEmbeddingService()