import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app # Import your FastAPI app
from app.db.base_class import Base
from app.db.models import User, Tenant, Document
from app.core.security import get_password_hash
from app.api.dependencies import get_db, get_current_user, get_current_active_user, get_current_active_superuser

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
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Test Tenant",
        description="A test tenant",
        bucket_name="test-bucket",
        is_active=True
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def test_user(db_session, test_tenant):
    """Create a test user"""
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        hashed_password=get_password_hash("password"),
        full_name="Test User",
        is_active=True,
        is_superuser=False,
        tenant_id=test_tenant.id,
        clerk_user_id="test_clerk_123"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_superuser(db_session, test_tenant):
    """Create a test superuser"""
    superuser = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        hashed_password=get_password_hash("password"),
        full_name="Admin User",
        is_active=True,
        is_superuser=True,
        tenant_id=test_tenant.id,
        clerk_user_id="admin_clerk_123"
    )
    db_session.add(superuser)
    db_session.commit()
    db_session.refresh(superuser)
    return superuser


@pytest.fixture
def test_documents(db_session, test_tenant, test_user):
    """Create test documents"""
    documents = []
    for i in range(3):
        doc = Document(
            id=uuid.uuid4(),
            title=f"Test Document {i+1}",
            description=f"Description for test document {i+1}",
            filename=f"test_doc_{i+1}.pdf",
            file_path=f"/path/to/test_doc_{i+1}.pdf",
            file_type="application/pdf",
            file_size=1024 * (i+1),
            tenant_id=test_tenant.id,
            created_by=test_user.id,
            indexed=1
        )
        documents.append(doc)
        db_session.add(doc)
    
    db_session.commit()
    for doc in documents:
        db_session.refresh(doc)
    return documents


@pytest.fixture
def normal_user_token_headers(test_user):
    """Create token headers for normal user"""
    # Override authentication dependencies to return the test user
    def override_get_current_user():
        return test_user
    
    def override_get_current_active_user():
        return test_user
    
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user
    
    token = "mock_normal_user_token"
    yield {"Authorization": f"Bearer {token}"}
    
    # Clean up overrides
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)


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
    
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user
    app.dependency_overrides[get_current_active_superuser] = override_get_current_active_superuser
    
    token = "mock_superuser_token"
    yield {"Authorization": f"Bearer {token}"}
    
    # Clean up overrides
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_current_active_superuser, None)
