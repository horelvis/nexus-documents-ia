import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from fastapi.testclient import TestClient
from app.main import app, db_client as global_prisma_client  # Import your FastAPI app and the global prisma client
from app.api.dependencies import get_prisma_db # Import the dependency we want to override

# Fixture to provide a mocked Prisma client instance for unit tests or direct use
@pytest.fixture(scope="function")
def mock_prisma_client():
    mock_client = MagicMock(spec=global_prisma_client) # Use spec from the actual client for better mocking
    
    # Mock specific model methods if needed, e.g., for user repository tests
    # These can be further customized in individual tests
    mock_client.user = MagicMock()
    mock_client.user.find_unique = AsyncMock()
    mock_client.user.find_first = AsyncMock()
    mock_client.user.create = AsyncMock()
    mock_client.user.update = AsyncMock()
    mock_client.user.delete = AsyncMock()

    mock_client.tenant = MagicMock()
    mock_client.tenant.find_unique = AsyncMock()
    mock_client.tenant.create = AsyncMock()
    mock_client.tenant.find_many = AsyncMock()
    
    mock_client.subscription = MagicMock()
    mock_client.subscription.find_unique = AsyncMock()
    mock_client.subscription.create = AsyncMock()

    # Mock connect/disconnect if they are explicitly called in the code being tested
    # (though for lifespan events, this might not be directly tested this way)
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.is_connected = MagicMock(return_value=True) # Assume connected

    return mock_client

# Fixture to provide a TestClient for integration tests, with Prisma dependency overridden
@pytest.fixture(scope="function")
def test_app_client(mock_prisma_client: MagicMock): # Depends on the mock_prisma_client fixture
    
    # This function will override the original get_prisma_db dependency
    async def override_get_prisma_db():
        # Ensure the mock client itself is awaitable if the dependency is an async generator
        # However, our get_prisma_db is an async function returning the client directly.
        return mock_prisma_client

    # Apply the override to the FastAPI app
    app.dependency_overrides[get_prisma_db] = override_get_prisma_db
    
    # Create a TestClient instance for the app
    with TestClient(app) as client:
        yield client # Provide the client to the test

    # Clean up the override after the test
    app.dependency_overrides.clear()


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
