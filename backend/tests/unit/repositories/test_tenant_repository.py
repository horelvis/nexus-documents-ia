import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from app.db.repositories import tenants as tenant_repo
from prisma.models import Tenant as PrismaTenant
from prisma.errors import RecordNotFoundError

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_tenant_data():
    tenant_id = str(uuid4())
    return {
        "id": tenant_id,
        "name": "Test Tenant",
        "description": "A tenant for testing",
        "isActive": True,
        "createdAt": "2023-01-01T00:00:00Z", # simplified ISO string
        "updatedAt": "2023-01-01T00:00:00Z",
        # Add other fields from your PrismaTenant model if necessary
    }

async def test_get_tenant_success(mock_prisma_client, mock_tenant_data):
    mock_prisma_client.tenant.find_unique.return_value = PrismaTenant(**mock_tenant_data)
    
    tenant = await tenant_repo.get_tenant(db=mock_prisma_client, tenant_id=mock_tenant_data["id"])
    
    assert tenant is not None
    assert tenant.id == mock_tenant_data["id"]
    assert tenant.name == mock_tenant_data["name"]
    mock_prisma_client.tenant.find_unique.assert_called_once_with(where={"id": mock_tenant_data["id"]})

async def test_get_tenant_not_found(mock_prisma_client):
    mock_prisma_client.tenant.find_unique.return_value = None
    tenant_id_not_found = str(uuid4())
    
    tenant = await tenant_repo.get_tenant(db=mock_prisma_client, tenant_id=tenant_id_not_found)
    
    assert tenant is None
    mock_prisma_client.tenant.find_unique.assert_called_once_with(where={"id": tenant_id_not_found})

async def test_get_tenant_by_name_success(mock_prisma_client, mock_tenant_data):
    mock_prisma_client.tenant.find_unique.return_value = PrismaTenant(**mock_tenant_data)
    
    tenant = await tenant_repo.get_tenant_by_name(db=mock_prisma_client, name=mock_tenant_data["name"])
    
    assert tenant is not None
    assert tenant.name == mock_tenant_data["name"]
    mock_prisma_client.tenant.find_unique.assert_called_once_with(where={"name": mock_tenant_data["name"]})

async def test_list_tenants_success(mock_prisma_client, mock_tenant_data):
    # Create a list of mock tenant data for the find_many return value
    mock_tenants_list = [PrismaTenant(**mock_tenant_data)] 
    mock_prisma_client.tenant.find_many.return_value = mock_tenants_list
    
    tenants = await tenant_repo.list_tenants(db=mock_prisma_client, skip=0, limit=10)
    
    assert tenants is not None
    assert len(tenants) == 1
    assert tenants[0].id == mock_tenant_data["id"]
    mock_prisma_client.tenant.find_many.assert_called_once_with(skip=0, take=10)

async def test_create_tenant_success(mock_prisma_client, mock_tenant_data):
    create_data = {"name": mock_tenant_data["name"], "description": mock_tenant_data["description"]}
    # Ensure the mock return includes an ID and other defaults if Prisma client does
    mock_prisma_client.tenant.create.return_value = PrismaTenant(**mock_tenant_data)
        
    created_tenant = await tenant_repo.create_tenant(db=mock_prisma_client, tenant_data=create_data)
    
    assert created_tenant is not None
    assert created_tenant.name == create_data["name"]
    assert created_tenant.id == mock_tenant_data["id"]
    mock_prisma_client.tenant.create.assert_called_once_with(data=create_data)

async def test_create_tenant_missing_name(mock_prisma_client):
    with pytest.raises(ValueError, match="Name is required to create a tenant."):
        await tenant_repo.create_tenant(db=mock_prisma_client, tenant_data={"description": "Missing name"})

async def test_update_tenant_success(mock_prisma_client, mock_tenant_data):
    update_payload = {"description": "Updated Description"}
    updated_tenant_raw_data = {**mock_tenant_data, "description": "Updated Description"}
    mock_prisma_client.tenant.update.return_value = PrismaTenant(**updated_tenant_raw_data)
    
    updated_tenant = await tenant_repo.update_tenant(
        db=mock_prisma_client, 
        tenant_id=mock_tenant_data["id"], 
        tenant_data=update_payload
    )
    
    assert updated_tenant is not None
    assert updated_tenant.description == "Updated Description"
    mock_prisma_client.tenant.update.assert_called_once_with(
        where={"id": mock_tenant_data["id"]}, 
        data=update_payload
    )

async def test_update_tenant_not_found(mock_prisma_client):
    mock_prisma_client.tenant.update.side_effect = RecordNotFoundError()
    tenant_id_not_found = str(uuid4())
    
    updated_tenant = await tenant_repo.update_tenant(
        db=mock_prisma_client, 
        tenant_id=tenant_id_not_found, 
        tenant_data={"name": "New Name"}
    )
    
    assert updated_tenant is None
    mock_prisma_client.tenant.update.assert_called_once()

async def test_delete_tenant_success(mock_prisma_client, mock_tenant_data):
    mock_prisma_client.tenant.delete.return_value = PrismaTenant(**mock_tenant_data)
    
    deleted_tenant = await tenant_repo.delete_tenant(db=mock_prisma_client, tenant_id=mock_tenant_data["id"])
    
    assert deleted_tenant is not None
    assert deleted_tenant.id == mock_tenant_data["id"]
    mock_prisma_client.tenant.delete.assert_called_once_with(where={"id": mock_tenant_data["id"]})

async def test_delete_tenant_not_found(mock_prisma_client):
    mock_prisma_client.tenant.delete.side_effect = RecordNotFoundError()
    tenant_id_not_found = str(uuid4())
    
    deleted_tenant = await tenant_repo.delete_tenant(db=mock_prisma_client, tenant_id=tenant_id_not_found)
    
    assert deleted_tenant is None
    mock_prisma_client.tenant.delete.assert_called_once()
