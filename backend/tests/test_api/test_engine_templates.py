import pytest
from unittest.mock import MagicMock, patch
import uuid
from app.db.models import Document

@pytest.fixture
def odt_document(db_session, test_tenant, test_user):
    """Create a test ODT document"""
    doc = Document(
        id=uuid.uuid4(),
        title="Test ODT Template",
        description="A test ODT document for template creation",
        filename="template.odt",
        file_path="templates/test.odt",
        file_type="odt",  # Important: must be odt (case insensitive check in service)
        mime_type="application/vnd.oasis.opendocument.text",
        file_size=1000,
        tenant_id=test_tenant.id,
        created_by=test_user.id,
        indexed=1
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc

def test_create_template_from_document_fix(
    client, 
    odt_document, 
    superuser_token_headers, 
    mock_storage_service
):
    """
    Test creating a workflow template from a document.
    Verifies the fix for UUID serialization in WorkflowTemplateResponse.
    """
    # Arrange
    payload = {
        "document_id": str(odt_document.id),
        "name": "Generated Template",
        "description": "Generated from ODT",
        "category": "legal"
    }
    
    # Mock StorageServiceFactory to return our mock_storage_service
    # IMPORTANT: TemplateStorageService uses synchronous calls, so we must ensure
    # the mock methods are NOT AsyncMock (which conftest.py might provide).
    mock_storage_service.download_file = MagicMock(return_value=b"fake odt content")
    mock_storage_service.upload_file = MagicMock(return_value=True)
    
    with patch("app.services.storage_factory.StorageServiceFactory.create_storage_service", return_value=mock_storage_service):
        # Act
        response = client.post(
            "/api/v1/engine-templates/from-document",
            headers=superuser_token_headers,
            json=payload
        )
    
    # Assert
    assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
    
    data = response.json()
    assert data["name"] == "Generated Template"
    assert data["tenant_id"] == str(odt_document.tenant_id)
    # Check that ID fields are strings (validation passed)
    assert isinstance(data["tenant_id"], str)
    assert isinstance(data["created_by"], str)
    # Check template source doc ID
    assert data["template_source_document_id"] == str(odt_document.id)

def test_create_workflow_template_direct_fix(
    client,
    superuser_token_headers
):
    """
    Test creating a workflow template directly.
    Verifies the fix applies to the standard creation endpoint too.
    """
    payload = {
        "name": "Direct Template",
        "category": "hr",
        "workflow_steps": [
            {
                "step_id": "step1",
                "step_name": "Step 1",
                "step_type": "manual"
            }
        ],
        "input_fields": []
    }
    
    response = client.post(
        "/api/v1/engine-templates/",
        headers=superuser_token_headers,
        json=payload
    )
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
    data = response.json()
    assert isinstance(data["tenant_id"], str)
    assert isinstance(data["created_by"], str)