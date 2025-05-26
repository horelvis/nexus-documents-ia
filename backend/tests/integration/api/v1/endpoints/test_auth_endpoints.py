import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.schemas.user import UserRead
from app.schemas.auth import LoginRequest, TokenResponse
from app.core.security import get_password_hash # For creating hashed passwords for mocks
from prisma.models import User as PrismaUser, Tenant as PrismaTenant

# Mark all tests in this file as asyncio, though TestClient calls are synchronous
# pytestmark = pytest.mark.asyncio # Not strictly needed for TestClient tests if test functions are not async

def test_login_success(test_app_client: TestClient, mock_prisma_client: MagicMock, mocker):
    user_id = str(uuid4())
    tenant_id = str(uuid4())
    email = "test@example.com"
    password = "password123"
    hashed_password = get_password_hash(password)

    mock_user_db_instance = PrismaUser(
        id=user_id, 
        email=email, 
        hashedPassword=hashed_password, 
        isActive=True, 
        tenantId=tenant_id,
        fullName="Test User",
        isSuperuser=False,
        clerkUserId=None,
        createdAt="2023-01-01T00:00:00Z",
        updatedAt="2023-01-01T00:00:00Z",
        subscriptionId=None
    )
    
    # Mock the return value of user_repo.get_user_by_email (called by AuthService.authenticate_user)
    mock_prisma_client.user.find_unique.return_value = mock_user_db_instance
    
    # Mock create_access_token if we don't want to test its actual implementation here
    # For full integration, we might let it run if SECRET_KEY is available for tests
    mocker.patch("app.services.auth_service.AuthService.create_access_token", return_value="fake-access-token")

    login_data = {"username": email, "password": password} # FastAPI's OAuth2PasswordRequestForm uses "username"
    
    response = test_app_client.post("/api/v1/auth/login", data=login_data) # Send as form data
    
    assert response.status_code == 200
    token_response = response.json()
    assert token_response["access_token"] == "fake-access-token"
    assert token_response["token_type"] == "bearer"
    assert token_response["user"]["email"] == email
    assert token_response["user"]["id"] == user_id

    mock_prisma_client.user.find_unique.assert_called_once_with(where={"email": email})


def test_login_invalid_credentials(test_app_client: TestClient, mock_prisma_client: MagicMock):
    email = "wrong@example.com"
    password = "wrongpassword"
    
    # Simulate user not found or password incorrect
    mock_prisma_client.user.find_unique.return_value = None # Simulate user not found
    
    login_data = {"username": email, "password": password}
    response = test_app_client.post("/api/v1/auth/login", data=login_data)
    
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"
    mock_prisma_client.user.find_unique.assert_called_once_with(where={"email": email})


def test_register_success(test_app_client: TestClient, mock_prisma_client: MagicMock):
    new_user_email = "newuser@example.com"
    new_user_password = "newpassword123"
    tenant_id = str(uuid4())
    user_id = str(uuid4())

    # Mock for existing_user check (should be None)
    mock_prisma_client.user.find_unique.return_value = None 
    
    # Mock for get_tenant (should return a tenant)
    mock_tenant_instance = PrismaTenant(id=tenant_id, name="Test Tenant", isActive=True, description=None, createdAt="2023-01-01T00:00:00Z", updatedAt="2023-01-01T00:00:00Z")
    # If tenant_repo.get_tenant uses find_unique on tenant model:
    mock_prisma_client.tenant.find_unique.return_value = mock_tenant_instance
    
    # Mock for user_repo.create_user
    created_user_instance = PrismaUser(
        id=user_id, 
        email=new_user_email, 
        hashedPassword=get_password_hash(new_user_password), # Not directly checked in response
        isActive=True, 
        tenantId=tenant_id,
        fullName="New User",
        isSuperuser=False,
        clerkUserId="clerk_new_user",
        createdAt="2023-01-01T00:00:00Z",
        updatedAt="2023-01-01T00:00:00Z",
        subscriptionId=None
    )
    mock_prisma_client.user.create.return_value = created_user_instance
    
    register_payload = {
        "email": new_user_email,
        "password": new_user_password,
        "fullName": "New User",
        "tenantId": tenant_id,
        "clerkUserId": "clerk_new_user",
        "isSuperuser": False,
        "isActive": True
    }
    
    response = test_app_client.post("/api/v1/auth/register", json=register_payload)
    
    assert response.status_code == 201
    user_response = response.json()
    assert user_response["email"] == new_user_email
    assert user_response["id"] == user_id
    assert user_response["tenantId"] == tenant_id
    assert user_response["clerkUserId"] == "clerk_new_user"

    # Assert that find_unique was called for email check
    mock_prisma_client.user.find_unique.assert_called_once_with(where={"email": new_user_email})
    # Assert that find_unique was called for tenant check
    mock_prisma_client.tenant.find_unique.assert_called_once_with(where={"id": tenant_id})
    # Assert create was called
    # We need to be careful about the exact data passed to create, especially hashedPassword
    mock_prisma_client.user.create.assert_called_once() 
    # More specific check for create_user data (excluding hashed_password for simplicity here)
    # called_data = mock_prisma_client.user.create.call_args[1]['data']
    # assert called_data['email'] == new_user_email


def test_register_email_exists(test_app_client: TestClient, mock_prisma_client: MagicMock):
    existing_user_email = "existing@example.com"
    
    # Mock for existing_user check (returns a user)
    mock_prisma_client.user.find_unique.return_value = PrismaUser(
        id=str(uuid4()), email=existing_user_email, hashedPassword="dummy", isActive=True, tenantId=str(uuid4()),
        createdAt="2023-01-01T00:00:00Z", updatedAt="2023-01-01T00:00:00Z", fullName=None, isSuperuser=False, clerkUserId=None, subscriptionId=None
    )
        
    register_payload = {
        "email": existing_user_email,
        "password": "password123",
        "fullName": "Existing User",
        "tenantId": str(uuid4()),
    }
    
    response = test_app_client.post("/api/v1/auth/register", json=register_payload)
    
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"
    mock_prisma_client.user.find_unique.assert_called_once_with(where={"email": existing_user_email})


def test_register_tenant_not_found(test_app_client: TestClient, mock_prisma_client: MagicMock):
    new_user_email = "newtenantuser@example.com"
    tenant_id_not_found = str(uuid4())

    # Mock for existing_user check (should be None)
    mock_prisma_client.user.find_unique.return_value = None
    
    # Mock for get_tenant (should return None)
    mock_prisma_client.tenant.find_unique.return_value = None
            
    register_payload = {
        "email": new_user_email,
        "password": "password123",
        "tenantId": tenant_id_not_found,
    }
    
    response = test_app_client.post("/api/v1/auth/register", json=register_payload)
    
    assert response.status_code == 400
    assert response.json()["detail"] == f"Tenant with ID {tenant_id_not_found} not found."
    # find_unique for user email check
    mock_prisma_client.user.find_unique.assert_called_once_with(where={"email": new_user_email})
    # find_unique for tenant check
    mock_prisma_client.tenant.find_unique.assert_called_once_with(where={"id": tenant_id_not_found})
    # user.create should not have been called
    mock_prisma_client.user.create.assert_not_called()
