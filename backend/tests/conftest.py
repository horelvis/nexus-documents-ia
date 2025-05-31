import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from fastapi.testclient import TestClient
from app.main import app # Import your FastAPI app

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
