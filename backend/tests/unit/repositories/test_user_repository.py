import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.db.repositories import users as user_repo
from prisma.models import User as PrismaUser # For type hinting if needed for mock return values
from prisma.errors import RecordNotFoundError

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_user_data():
    user_id = str(uuid4())
    tenant_id = str(uuid4())
    return {
        "id": user_id,
        "email": "test@example.com",
        "hashedPassword": "hashedpassword",
        "fullName": "Test User",
        "isActive": True,
        "isSuperuser": False,
        "tenantId": tenant_id,
        "clerkUserId": f"clerk_{user_id}",
        "createdAt": "2023-01-01T00:00:00Z", # simplified ISO string for datetime
        "updatedAt": "2023-01-01T00:00:00Z",
        # Add other fields as defined in your PrismaUser model for completeness
        "subscriptionId": None, # Assuming optional
    }

async def test_get_user_success(mock_prisma_client, mock_user_data):
    mock_prisma_client.user.find_unique.return_value = PrismaUser(**mock_user_data)
    
    user = await user_repo.get_user(db=mock_prisma_client, user_id=mock_user_data["id"])
    
    assert user is not None
    assert user.id == mock_user_data["id"]
    assert user.email == mock_user_data["email"]
    mock_prisma_client.user.find_unique.assert_called_once_with(where={"id": mock_user_data["id"]})

async def test_get_user_not_found(mock_prisma_client):
    mock_prisma_client.user.find_unique.return_value = None
    user_id_not_found = str(uuid4())
    
    user = await user_repo.get_user(db=mock_prisma_client, user_id=user_id_not_found)
    
    assert user is None
    mock_prisma_client.user.find_unique.assert_called_once_with(where={"id": user_id_not_found})

async def test_get_user_by_email_success(mock_prisma_client, mock_user_data):
    mock_prisma_client.user.find_unique.return_value = PrismaUser(**mock_user_data)
    
    user = await user_repo.get_user_by_email(db=mock_prisma_client, email=mock_user_data["email"])
    
    assert user is not None
    assert user.email == mock_user_data["email"]
    mock_prisma_client.user.find_unique.assert_called_once_with(where={"email": mock_user_data["email"]})

async def test_get_user_by_clerk_id_success(mock_prisma_client, mock_user_data):
    mock_prisma_client.user.find_unique.return_value = PrismaUser(**mock_user_data)
    
    user = await user_repo.get_user_by_clerk_id(db=mock_prisma_client, clerk_user_id=mock_user_data["clerkUserId"])
    
    assert user is not None
    assert user.clerkUserId == mock_user_data["clerkUserId"]
    mock_prisma_client.user.find_unique.assert_called_once_with(where={"clerkUserId": mock_user_data["clerkUserId"]})

async def test_get_user_by_clerk_id_not_found(mock_prisma_client):
    mock_prisma_client.user.find_unique.return_value = None
    clerk_id_not_found = "clerk_nonexistent"
    
    user = await user_repo.get_user_by_clerk_id(db=mock_prisma_client, clerk_user_id=clerk_id_not_found)
    
    assert user is None
    mock_prisma_client.user.find_unique.assert_called_once_with(where={"clerkUserId": clerk_id_not_found})


async def test_create_user_success(mock_prisma_client, mock_user_data):
    create_data = {
        "email": mock_user_data["email"],
        "hashedPassword": mock_user_data["hashedPassword"],
        "tenantId": mock_user_data["tenantId"],
        "fullName": mock_user_data["fullName"],
        "clerkUserId": mock_user_data["clerkUserId"]
    }
    # Mock the return value of create to include an ID and other defaults
    mock_prisma_client.user.create.return_value = PrismaUser(**mock_user_data)
        
    created_user = await user_repo.create_user(db=mock_prisma_client, user_data=create_data)
    
    assert created_user is not None
    assert created_user.email == create_data["email"]
    # In a real scenario, PrismaUser(**mock_user_data) should have an id
    assert created_user.id == mock_user_data["id"] 
    mock_prisma_client.user.create.assert_called_once_with(data=create_data)

async def test_create_user_missing_required_fields(mock_prisma_client):
    with pytest.raises(ValueError, match="Email and tenantId are required"):
        await user_repo.create_user(db=mock_prisma_client, user_data={"email": "test@example.com"}) # Missing tenantId

async def test_update_user_success(mock_prisma_client, mock_user_data):
    update_payload = {"fullName": "Updated Name"}
    updated_user_data = {**mock_user_data, "fullName": "Updated Name"}
    mock_prisma_client.user.update.return_value = PrismaUser(**updated_user_data)
    
    updated_user = await user_repo.update_user(
        db=mock_prisma_client, 
        user_id=mock_user_data["id"], 
        user_data=update_payload
    )
    
    assert updated_user is not None
    assert updated_user.fullName == "Updated Name"
    mock_prisma_client.user.update.assert_called_once_with(
        where={"id": mock_user_data["id"]}, 
        data=update_payload
    )

async def test_update_user_not_found(mock_prisma_client):
    mock_prisma_client.user.update.side_effect = RecordNotFoundError()
    user_id_not_found = str(uuid4())
    
    updated_user = await user_repo.update_user(
        db=mock_prisma_client, 
        user_id=user_id_not_found, 
        user_data={"fullName": "New Name"}
    )
    
    assert updated_user is None
    mock_prisma_client.user.update.assert_called_once()

async def test_delete_user_success(mock_prisma_client, mock_user_data):
    mock_prisma_client.user.delete.return_value = PrismaUser(**mock_user_data)
    
    deleted_user = await user_repo.delete_user(db=mock_prisma_client, user_id=mock_user_data["id"])
    
    assert deleted_user is not None
    assert deleted_user.id == mock_user_data["id"]
    mock_prisma_client.user.delete.assert_called_once_with(where={"id": mock_user_data["id"]})

async def test_delete_user_not_found(mock_prisma_client):
    mock_prisma_client.user.delete.side_effect = RecordNotFoundError()
    user_id_not_found = str(uuid4())
    
    deleted_user = await user_repo.delete_user(db=mock_prisma_client, user_id=user_id_not_found)
    
    assert deleted_user is None
    mock_prisma_client.user.delete.assert_called_once()
