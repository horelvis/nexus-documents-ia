import pytest
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient
from app.core.config import settings # To get the API_KEY for testing
from prisma.models import User as PrismaUser

# Valid API Key for tests (should match what's in your test .env or config override for tests)
# For this test, we'll use the default from config if not overridden for test environment
VALID_API_KEY = settings.API_KEY 

@pytest.fixture
def mock_user_db_instance():
    user_id = str(uuid4())
    tenant_id = str(uuid4())
    return PrismaUser(
        id=user_id,
        email="me@example.com",
        hashedPassword="hashedpassword",
        isActive=True,
        tenantId=tenant_id,
        fullName="Me User",
        isSuperuser=False,
        clerkUserId=f"clerk_{user_id}",
        createdAt="2023-01-01T00:00:00Z",
        updatedAt="2023-01-01T00:00:00Z",
        subscriptionId=None
    )

def test_read_users_me_success(test_app_client: TestClient, mock_prisma_client: MagicMock, mock_user_db_instance: PrismaUser):
    mock_prisma_client.user.find_first.return_value = mock_user_db_instance
    
    response = test_app_client.get(
        "/api/v1/users/me",
        headers={"X-API-KEY": VALID_API_KEY}
    )
    
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["email"] == mock_user_db_instance.email
    assert user_data["id"] == mock_user_db_instance.id
    mock_prisma_client.user.find_first.assert_called_once()

def test_read_users_me_no_api_key(test_app_client: TestClient):
    response = test_app_client.get("/api/v1/users/me")
    assert response.status_code == 403 # Or 401 depending on auto_error in APIKeyHeader
    assert "Not authenticated" in response.json()["detail"]

def test_read_users_me_invalid_api_key(test_app_client: TestClient):
    response = test_app_client.get(
        "/api/v1/users/me",
        headers={"X-API-KEY": "invalid_key"}
    )
    assert response.status_code == 403 # Or 401
    assert "Invalid API Key" in response.json()["detail"]

def test_read_users_me_user_not_found(test_app_client: TestClient, mock_prisma_client: MagicMock):
    mock_prisma_client.user.find_first.return_value = None # Simulate no user found
    
    response = test_app_client.get(
        "/api/v1/users/me",
        headers={"X-API-KEY": VALID_API_KEY}
    )
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Default user for /me not found."


def test_read_user_by_id_success(test_app_client: TestClient, mock_prisma_client: MagicMock, mock_user_db_instance: PrismaUser):
    target_user_id = mock_user_db_instance.id
    mock_prisma_client.user.find_unique.return_value = mock_user_db_instance
    
    response = test_app_client.get(
        f"/api/v1/users/{target_user_id}",
        headers={"X-API-KEY": VALID_API_KEY}
    )
    
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["id"] == target_user_id
    assert user_data["email"] == mock_user_db_instance.email
    mock_prisma_client.user.find_unique.assert_called_once_with(where={"id": target_user_id})

def test_read_user_by_id_not_found(test_app_client: TestClient, mock_prisma_client: MagicMock):
    non_existent_user_id = str(uuid4())
    mock_prisma_client.user.find_unique.return_value = None
    
    response = test_app_client.get(
        f"/api/v1/users/{non_existent_user_id}",
        headers={"X-API-KEY": VALID_API_KEY}
    )
    
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"
    mock_prisma_client.user.find_unique.assert_called_once_with(where={"id": non_existent_user_id})

def test_read_user_by_id_no_api_key(test_app_client: TestClient):
    user_id = str(uuid4())
    response = test_app_client.get(f"/api/v1/users/{user_id}")
    assert response.status_code == 403 # Or 401
    assert "Not authenticated" in response.json()["detail"]

def test_read_user_by_id_invalid_api_key(test_app_client: TestClient):
    user_id = str(uuid4())
    response = test_app_client.get(
        f"/api/v1/users/{user_id}",
        headers={"X-API-KEY": "invalid_key"}
    )
    assert response.status_code == 403 # Or 401
    assert "Invalid API Key" in response.json()["detail"]
