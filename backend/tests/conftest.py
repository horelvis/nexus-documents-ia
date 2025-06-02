import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app # Import your FastAPI app
from app.db.base_class import Base
from app.db.models import User, Tenant, Document, Tag
from app.core.security import get_password_hash
from app.api.dependencies import get_db, get_current_user, get_current_active_user, get_current_active_superuser
from app.services.auth_service import AuthService

# Fixture to provide a TestClient for integration tests
@pytest.fixture(scope="function")
def client(): 
    # Create a TestClient instance for the app
    with TestClient(app) as client:
        yield client # Provide the client to the test

    # Clean up any dependency overrides if they were used by a specific test
    # For now, no global overrides are set up here.
    # If future tests add overrides directly, they should clean them up.
    # Consider adding app.dependency_overrides.clear() if tests start adding overrides.


# This is needed if you have any 'async def' test functions directly
# and are not using something like pytest-asyncio's auto mode.
# However, with pytest-asyncio, this might not be strictly necessary
# if it's configured to handle async fixtures and tests automatically.
@pytest.fixture(scope="session")
def event_loop():
    # Set the policy to prevent "Event loop is closed" error on Windows
    # if sys.platform == "win32":
    #     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # For pytest-asyncio, the default event loop policy is usually sufficient.
    # If specific policy changes are needed, they can be done here.
    # The primary purpose is to ensure an event loop is available for the session.
    try:
        loop = asyncio.get_event_loop_policy().new_event_loop()
        asyncio.set_event_loop(loop)
        yield loop
    finally:
        loop.close()


# Database test fixtures
@pytest.fixture(scope="session")
def test_db():
    """Create a test database connection using PostgreSQL from docker-compose-test.yml"""
    # Use environment variables that match docker-compose-test.yml
    import os
    
    # Database configuration for tests
    POSTGRES_SERVER = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "test_user")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "test_password")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "test_db")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    
    DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}"
    
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    yield TestingSessionLocal
    
    # Clean up the database after tests
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(test_db):
    """Create a database session for tests"""
    session = test_db()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_tenant(db_session):
    """Create a test tenant"""
    # Generate unique name to avoid duplicates
    unique_id = str(uuid.uuid4())[:8]
    tenant_name = f"Test Tenant {unique_id}"
    bucket_name = f"test-bucket-{unique_id}"
    
    # Check if tenant already exists, if so return it
    existing_tenant = db_session.query(Tenant).filter(Tenant.name == tenant_name).first()
    if existing_tenant:
        return existing_tenant
    
    tenant = Tenant(
        id=uuid.uuid4(),
        name=tenant_name,
        description=f"A test tenant {unique_id}",
        bucket_name=bucket_name,
        is_active=True
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def test_user(db_session, test_tenant):
    """Create a test user"""
    # Generate unique email to avoid duplicates
    unique_id = str(uuid.uuid4())[:8]
    user_email = f"test-{unique_id}@example.com"
    clerk_user_id = f"test_clerk_{unique_id}"
    
    # Check if user already exists, if so delete it first to avoid conflicts
    existing_user = db_session.query(User).filter(User.email == user_email).first()
    if existing_user:
        db_session.delete(existing_user)
        db_session.commit()
    
    user = User(
        id=uuid.uuid4(),
        email=user_email,
        hashed_password=get_password_hash("password"),
        full_name=f"Test User {unique_id}",
        is_active=True,
        is_superuser=False,
        tenant_id=test_tenant.id,
        clerk_user_id=clerk_user_id
    )
    db_session.add(user)
    try:
        db_session.commit()
        db_session.refresh(user)
    except Exception:
        db_session.rollback()
        # Try to find existing user again
        existing_user = db_session.query(User).filter(User.clerk_user_id == clerk_user_id).first()
        if existing_user:
            return existing_user
        raise
    return user


@pytest.fixture
def test_superuser(db_session, test_tenant):
    """Create a test superuser"""
    # Generate unique email to avoid duplicates
    unique_id = str(uuid.uuid4())[:8]
    admin_email = f"admin-{unique_id}@example.com"
    clerk_user_id = f"admin_clerk_{unique_id}"
    
    # Check if superuser already exists, if so delete it first to avoid conflicts
    existing_superuser = db_session.query(User).filter(User.email == admin_email).first()
    if existing_superuser:
        db_session.delete(existing_superuser)
        db_session.commit()
    
    superuser = User(
        id=uuid.uuid4(),
        email=admin_email,
        hashed_password=get_password_hash("password"),
        full_name=f"Admin User {unique_id}",
        is_active=True,
        is_superuser=True,
        tenant_id=test_tenant.id,
        clerk_user_id=clerk_user_id
    )
    db_session.add(superuser)
    try:
        db_session.commit()
        db_session.refresh(superuser)
    except Exception:
        db_session.rollback()
        # Try to find existing superuser again
        existing_superuser = db_session.query(User).filter(User.clerk_user_id == clerk_user_id).first()
        if existing_superuser:
            return existing_superuser
        raise
    return superuser


@pytest.fixture
def test_documents(db_session, test_tenant, test_user):
    """Create test documents with real temporary files"""
    import tempfile
    import os
    
    documents = []
    temp_files = []
    
    try:
        for i in range(3):
            # Create a temporary file with some content
            temp_file = tempfile.NamedTemporaryFile(mode='w+', suffix='.pdf', delete=False)
            content = f"This is test document {i+1} content for testing purposes."
            temp_file.write(content)
            temp_file.close()
            temp_files.append(temp_file.name)
            
            doc = Document(
                id=uuid.uuid4(),
                title=f"Test Document {i+1}",
                description=f"Description for test document {i+1}",
                filename=f"test_doc_{i+1}.pdf",
                file_path=temp_file.name,
                file_type="application/pdf",
                file_size=len(content.encode('utf-8')),
                tenant_id=test_tenant.id,
                created_by=test_user.id,
                indexed=1
            )
            documents.append(doc)
            db_session.add(doc)
        
        db_session.commit()
        for doc in documents:
            db_session.refresh(doc)
        
        yield documents
        
    finally:
        # Clean up temporary files
        for temp_file_path in temp_files:
            try:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
            except Exception:
                pass


@pytest.fixture
def test_tags(db_session, test_tenant):
    """Create test tags"""
    tags = []
    tag_names = ["python", "fastapi", "testing", "documentation", "api"]
    
    for name in tag_names:
        tag = Tag(
            name=name,
            tenant_id=test_tenant.id
        )
        tags.append(tag)
        db_session.add(tag)
    
    db_session.commit()
    for tag in tags:
        db_session.refresh(tag)
    return tags


@pytest.fixture
def normal_user_token_headers(test_user):
    """Create token headers for normal user"""
    # Override authentication dependencies to return the test user
    def override_get_current_user():
        return test_user
    
    def override_get_current_active_user():
        return test_user
    
    # Override both the dependencies and the AuthService methods
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user
    app.dependency_overrides[AuthService.get_current_user] = override_get_current_user
    
    token = "mock_normal_user_token"
    yield {"Authorization": f"Bearer {token}"}
    
    # Clean up overrides
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(AuthService.get_current_user, None)


@pytest.fixture
def superuser_token_headers(test_superuser):
    """Create token headers for superuser"""
    # Override authentication dependencies to return the test superuser
    def override_get_current_user():
        return test_superuser
    
    def override_get_current_active_user():
        return test_superuser
    
    def override_get_current_active_superuser():
        return test_superuser
    
    # Override both the dependencies and the AuthService methods
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user
    app.dependency_overrides[get_current_active_superuser] = override_get_current_active_superuser
    app.dependency_overrides[AuthService.get_current_user] = override_get_current_user
    
    token = "mock_superuser_token"
    yield {"Authorization": f"Bearer {token}"}
    
    # Clean up overrides
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_current_active_superuser, None)
    app.dependency_overrides.pop(AuthService.get_current_user, None)


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service for tests"""
    mock = MagicMock()
    mock.get_embeddings = AsyncMock(return_value=[[0.1, 0.2, 0.3] * 100])  # Mock 300-dim embeddings
    return mock


@pytest.fixture
def mock_llm_service():
    """Mock LLM service for tests"""
    mock = MagicMock()
    mock.generate_response = AsyncMock(return_value={
        "answer": "Mock answer from LLM service",
        "sources": [],
        "confidence": 0.95
    })
    mock.suggest_tags = AsyncMock(return_value=["tag1", "tag2", "tag3", "tag4", "tag5"])
    mock.extract_metadata = AsyncMock(return_value={
        "título": "Mock Title",
        "autor": "Mock Author",
        "fecha": "2023-01-01",
        "categoría": "Mock Category"
    })
    return mock


@pytest.fixture
def mock_vector_service():
    """Mock vector service for tests"""
    mock = MagicMock()
    mock.search_similar = MagicMock(return_value=[
        {
            "document": {"id": "doc1", "title": "Test Doc 1", "content": "Mock content 1"},
            "score": 0.95,
            "matches": ["match1", "match2"]
        },
        {
            "document": {"id": "doc2", "title": "Test Doc 2", "content": "Mock content 2"},
            "score": 0.85,
            "matches": ["match3", "match4"]
        }
    ])
    mock.search_by_document_ids = MagicMock(return_value=[
        {
            "document": {"id": "doc1", "title": "Test Doc 1", "content": "Mock content 1"},
            "score": 0.95,
            "matches": ["match1", "match2"]
        }
    ])
    mock.get_collection_info = MagicMock(return_value={"total_documents": 10, "total_vectors": 100})
    return mock


@pytest.fixture
def mock_search_service():
    """Mock search service for tests"""
    mock = MagicMock()
    mock.ask_documents = AsyncMock(return_value={
        "answer": "Mock answer from search service",
        "sources": [],
        "confidence": 0.95
    })
    mock.chat_with_documents = AsyncMock(return_value={
        "answer": "Mock answer from search service",
        "sources": [],
        "confidence": 0.95
    })
    mock.semantic_search = MagicMock(return_value=[
        {
            "document": {"id": "doc1", "title": "Test Doc 1", "content": "Mock content 1"},
            "score": 0.95,
            "matches": ["match1", "match2"]
        }
    ])
    mock.search_documents = AsyncMock(return_value=[
        {
            "document": {"id": "doc1", "title": "Test Doc 1", "content": "Mock content 1"},
            "score": 0.95,
            "matches": ["match1", "match2"]
        }
    ])
    return mock


@pytest.fixture
def mock_storage_service():
    """Mock storage service for tests"""
    mock = MagicMock()
    mock.upload_file = AsyncMock(return_value={
        "file_path": "/mock/path/test_file.pdf",
        "file_size": 1024,
        "content_type": "application/pdf"
    })
    mock.download_file = AsyncMock(return_value=b"Mock file content")
    mock.delete_file = AsyncMock(return_value=True)
    mock.file_exists = MagicMock(return_value=True)
    mock.get_file_info = MagicMock(return_value={
        "size": 1024,
        "content_type": "application/pdf",
        "last_modified": datetime.now()
    })
    return mock


@pytest.fixture
def mock_document_service():
    """Mock document service for tests"""
    mock = MagicMock()
    mock.process_document = AsyncMock(return_value={
        "status": "processed",
        "chunks": 10,
        "embedding_id": "mock_embedding_123"
    })
    mock.extract_text = AsyncMock(return_value="Mock extracted text content")
    mock.get_document_content = AsyncMock(return_value="Mock document content")
    return mock


@pytest.fixture(autouse=True)
def patch_services(mock_llm_service, mock_vector_service, mock_embedding_service, mock_search_service, mock_storage_service, mock_document_service):
    """Auto-patch services for all tests"""
    with patch('app.services.search_service.LLMService') as mock_llm_class, \
         patch('app.services.search_service.VectorService') as mock_vector_class, \
         patch('app.services.llm_service.LLMService') as mock_llm_class2, \
         patch('app.api.v1.chat.LLMService') as mock_llm_class3, \
         patch('app.services.search_service.SearchService') as mock_search_class, \
         patch('app.api.v1.search.SearchService') as mock_search_class2, \
         patch('app.api.v1.chat.SearchService') as mock_search_class3, \
         patch('app.services.llm_service.LLMService') as mock_llm_class4, \
         patch('app.services.storage_service.StorageService') as mock_storage_class, \
         patch('app.services.document_service.DocumentService') as mock_document_class:
        
        # Configure the service classes to return our mocks
        mock_llm_class.return_value = mock_llm_service
        mock_vector_class.return_value = mock_vector_service
        mock_llm_class2.return_value = mock_llm_service
        mock_llm_class3.return_value = mock_llm_service
        mock_llm_class4.return_value = mock_llm_service
        mock_search_class.return_value = mock_search_service
        mock_search_class2.return_value = mock_search_service
        mock_search_class3.return_value = mock_search_service
        mock_storage_class.return_value = mock_storage_service
        mock_document_class.return_value = mock_document_service
        
        yield


@pytest.fixture
def real_storage_service(test_tenant):
    """
    Fixture para usar el StorageService real en tests de storage.
    Usa un bucket de test separado y se limpia después de cada test.
    """
    import os
    os.environ["TESTING"] = "true"  # Asegurar que está en modo testing
    
    from app.services.storage_service import StorageService
    storage = StorageService(tenant_id=str(test_tenant.id))
    
    yield storage
    
    # Cleanup: limpiar el bucket de test después de cada test
    try:
        storage.cleanup_test_bucket()
    except Exception as e:
        print(f"Warning: No se pudo limpiar bucket de test: {e}")


@pytest.fixture
def real_storage_service_with_cleanup(test_tenant):
    """
    Fixture para usar el StorageService real con cleanup completo.
    Elimina completamente el bucket de test después del test.
    """
    import os
    os.environ["TESTING"] = "true"  # Asegurar que está en modo testing
    
    from app.services.storage_service import StorageService
    storage = StorageService(tenant_id=str(test_tenant.id))
    
    yield storage
    
    # Cleanup completo: eliminar bucket de test
    try:
        storage.delete_test_bucket()
    except Exception as e:
        print(f"Warning: No se pudo eliminar bucket de test: {e}")
