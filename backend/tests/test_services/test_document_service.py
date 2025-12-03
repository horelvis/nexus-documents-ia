import pytest
import io
from uuid import uuid4, UUID
from fastapi import UploadFile, HTTPException
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

from sqlalchemy.orm import Session

from app.services.document_service import DocumentService
from app.db.models import Document, Tag # Removed DocumentChunk as it's not directly used by these tests
from app.schemas.enums import IndexingStatus
from app.core.config import settings


# --- Fixtures for DocumentService tests ---
@pytest.fixture
def mock_db_session():
    """Provides a MagicMock for the SQLAlchemy Session."""
    session = MagicMock(spec=Session)
    # Mock the query chain
    session.query.return_value.filter.return_value.first.return_value = None
    return session

@pytest.fixture
def document_service_instance(mock_db_session, test_tenant): # Added test_tenant for tenant_id
    """Provides a DocumentService instance with mocked dependencies."""
    # Mock dependencies of DocumentService if they are called by the methods under test
    # For _validate_file and _create_document_record, storage_service, embedding_service
    # are not directly called.
    service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(uuid4()))
    # If these services were used, you would mock them:
    # service.storage_service = MagicMock()
    # service.embedding_service = MagicMock()
    # Additional services can be mocked here if needed
    return service

# --- Tests for _validate_file ---

@pytest.mark.asyncio
async def test_validate_file_success(document_service_instance):
    """Test successful file validation."""
    # Arrange
    mock_file_content = b"This is a test file."
    mock_upload_file = AsyncMock(spec=UploadFile)
    mock_upload_file.filename = "test.pdf"
    mock_upload_file.read = AsyncMock(return_value=mock_file_content)
    mock_upload_file.seek = AsyncMock() 

    # Modify settings for this test case
    original_allowed_extensions = settings.ALLOWED_EXTENSIONS
    settings.ALLOWED_EXTENSIONS = ["pdf", "txt"]
    
    # Act
    file_ext, contents, file_size = await document_service_instance._validate_file(mock_upload_file, "test.pdf")
    
    # Assert
    assert file_ext == "pdf", f"Expected file extension 'pdf', got '{file_ext}'"
    assert contents == mock_file_content, "File content does not match expected content"
    assert file_size == len(mock_file_content), f"Expected file size {len(mock_file_content)}, got {file_size}"
    mock_upload_file.read.assert_called_once()
    
    # Teardown: Reset settings
    settings.ALLOWED_EXTENSIONS = original_allowed_extensions

@pytest.mark.asyncio
async def test_validate_file_invalid_extension(document_service_instance):
    """Test file validation with an invalid file extension."""
    # Arrange
    mock_upload_file = AsyncMock(spec=UploadFile)
    mock_upload_file.filename = "test.exe" # Invalid extension
    mock_upload_file.read = AsyncMock(return_value=b"some content")
    mock_upload_file.seek = AsyncMock()

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await document_service_instance._validate_file(mock_upload_file, "test.exe")
    assert exc_info.value.status_code == 400, f"Expected status code 400, got {exc_info.value.status_code}"
    assert "Tipo de archivo no permitido" in exc_info.value.detail, f"Expected error detail 'Tipo de archivo no permitido', got '{exc_info.value.detail}'"

@pytest.mark.asyncio
async def test_validate_file_too_large(document_service_instance):
    """Test file validation when file size exceeds the maximum allowed."""
    # Arrange
    mock_file_content = b"a" * (settings.MAX_UPLOAD_SIZE + 1) # Exceeds max size
    mock_upload_file = AsyncMock(spec=UploadFile)
    mock_upload_file.filename = "large_file.txt"
    mock_upload_file.read = AsyncMock(return_value=mock_file_content)
    mock_upload_file.seek = AsyncMock()

    # Modify settings for this test case
    original_allowed_extensions = settings.ALLOWED_EXTENSIONS
    settings.ALLOWED_EXTENSIONS = ["txt"] 

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await document_service_instance._validate_file(mock_upload_file, "large_file.txt")
    assert exc_info.value.status_code == 400, f"Expected status code 400, got {exc_info.value.status_code}"
    assert "Tamaño de archivo excede el límite" in exc_info.value.detail, f"Expected error detail 'Tamaño de archivo excede el límite', got '{exc_info.value.detail}'"

    # Teardown: Reset settings
    settings.ALLOWED_EXTENSIONS = original_allowed_extensions

@pytest.mark.asyncio
async def test_validate_file_empty(document_service_instance):
    """Test file validation for an empty file."""
    # Arrange
    mock_upload_file = AsyncMock(spec=UploadFile)
    mock_upload_file.filename = "empty.txt"
    mock_upload_file.read = AsyncMock(return_value=b"") # Empty content
    mock_upload_file.seek = AsyncMock()
    
    # Modify settings for this test case
    original_allowed_extensions = settings.ALLOWED_EXTENSIONS
    settings.ALLOWED_EXTENSIONS = ["txt"]

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await document_service_instance._validate_file(mock_upload_file, "empty.txt")
    assert exc_info.value.status_code == 400, f"Expected status code 400, got {exc_info.value.status_code}"
    assert "El archivo está vacío" in exc_info.value.detail, f"Expected error detail 'El archivo está vacío', got '{exc_info.value.detail}'"

    # Teardown: Reset settings
    settings.ALLOWED_EXTENSIONS = original_allowed_extensions

# --- Tests for _create_document_record ---

def test_create_document_record_success(document_service_instance, mock_db_session):
    """Test successful creation of a document record in the database, including tag handling."""
    # Arrange
    title = "Test Document"
    description = "A document for testing"
    filename = "test_doc.pdf"
    file_ext = "pdf"
    file_size = 1024
    tags_input = ["tag1", "new_tag"]  # "tag1" exists, "new_tag" does not

    # Mocking behavior for Tag lookups
    # This mock simulates that 'tag1' exists and 'new_tag' does not.
    existing_tag_obj = Tag(id=uuid4(), name="tag1", tenant_id=UUID(document_service_instance.tenant_id))
    
    def query_side_effect(model_class):
        query_mock = MagicMock()
        if model_class == Tag:
            # This more robustly mocks the filter().first() chain for Tags
            def filter_first_side_effect(*args, **kwargs):
                # Simplified: check if the filter is for "tag1" or "new_tag"
                # A more precise mock would inspect the actual filter condition object.
                if any("name='tag1'" in str(arg) for arg in args):
                    return existing_tag_obj
                elif any("name='new_tag'" in str(arg) for arg in args):
                    return None
                return None # Default for other tag queries
            
            filter_mock = MagicMock()
            filter_mock.first.side_effect = filter_first_side_effect
            query_mock.filter.return_value = filter_mock
        else:
            # Default mock for other models if any
            query_mock.filter.return_value.first.return_value = None
        return query_mock

    mock_db_session.query.side_effect = query_side_effect

    # Act
    db_document = document_service_instance._create_document_record(
        db=mock_db_session,
        title=title,
        description=description,
        filename=filename,
        file_ext=file_ext,
        file_size=file_size,
        tags=tags_input
    )

    # Assert
    assert isinstance(db_document, Document), "Result should be an instance of Document"
    assert db_document.title == title, f"Expected title '{title}', got '{db_document.title}'"
    assert db_document.description == description, f"Expected description '{description}', got '{db_document.description}'"
    assert db_document.filename == filename, f"Expected filename '{filename}', got '{db_document.filename}'"
    assert db_document.file_type == file_ext, f"Expected file_type '{file_ext}', got '{db_document.file_type}'"
    assert db_document.file_size == file_size, f"Expected file_size {file_size}, got {db_document.file_size}"
    assert db_document.tenant_id == UUID(document_service_instance.tenant_id), "Tenant ID mismatch"
    assert db_document.created_by == UUID(document_service_instance.user_id), "User ID mismatch"
    assert db_document.indexed == IndexingStatus.PROCESSING, f"Expected indexing status PROCESSING, got {db_document.indexed}"
    assert filename in db_document.file_path, f"Filename '{filename}' not in file_path '{db_document.file_path}'"
    assert str(db_document.id) in db_document.file_path, f"Document ID '{db_document.id}' not in file_path '{db_document.file_path}'"
    
    # Check tags
    assert len(db_document.tags) == 2, f"Expected 2 tags, got {len(db_document.tags)}"
    tag_names_in_doc = sorted([tag.name for tag in db_document.tags])
    assert tag_names_in_doc == sorted(["tag1", "new_tag"]), f"Expected tags ['tag1', 'new_tag'], got {tag_names_in_doc}"

    # Check db calls (add, flush, refresh)
    # At least two 'add' calls: one for the Document, one for the new Tag 'new_tag'.
    # The existing 'tag1' is not added again.
    assert mock_db_session.add.call_count >= 2, "db.add() should be called for Document and new Tags"
    
    added_objects = [call.args[0] for call in mock_db_session.add.call_args_list]
    assert any(isinstance(obj, Document) and obj.title == title for obj in added_objects), "Document object was not added to session"
    assert any(isinstance(obj, Tag) and obj.name == "new_tag" for obj in added_objects), "New Tag object 'new_tag' was not added to session"

    mock_db_session.flush.assert_called_once_with(_expected_order=None), "db.flush() was not called exactly once or with unexpected arguments"
    mock_db_session.refresh.assert_called_once_with(db_document), "db.refresh() was not called with the document instance"


def test_create_document_record_no_tags(document_service_instance, mock_db_session):
    """Test creation of a document record with no tags."""
    # Arrange
    title = "No Tags Doc"
    description = "Document without tags"
    filename = "notags.txt"
    file_ext = "txt"
    file_size = 100
    tags_input = [] # No tags

    # Act
    db_document = document_service_instance._create_document_record(
        db=mock_db_session,
        title=title,
        description=description, # Use the variable
        filename=filename,       # Use the variable
        file_ext=file_ext,       # Use the variable
        file_size=file_size,     # Use the variable
        tags=tags_input          # Use the variable
    )

    # Assert
    assert isinstance(db_document, Document), "Result should be an instance of Document"
    assert db_document.title == title, f"Expected title '{title}', got '{db_document.title}'"
    assert len(db_document.tags) == 0, f"Expected 0 tags, got {len(db_document.tags)}"
    
    # Assert that db.add was called for the document, but not for any new tags
    mock_db_session.query(Tag).filter().first.assert_not_called() # No tag lookups if tags list is empty
    
    # Check that only the document was added
    added_objects = [call.args[0] for call in mock_db_session.add.call_args_list]
    assert any(isinstance(obj, Document) and obj.title == title for obj in added_objects), "Document object was not added to session"
    assert not any(isinstance(obj, Tag) for obj in added_objects), "No Tag objects should have been added to session"

    mock_db_session.flush.assert_called_once_with(_expected_order=None), "db.flush() was not called exactly once or with unexpected arguments" 
    mock_db_session.refresh.assert_called_once_with(db_document), "db.refresh() was not called with the document instance"


# --- Tests for public methods using real DB session via `db` fixture ---

def test_get_documents(db: Session, test_documents, test_tenant): # Type hint db for clarity
    """Test retrieving a list of documents."""
    # Arrange
    # test_documents fixture already populates data using the same db session
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    
    # Act
    result = document_service.get_documents(db=db, page=1, per_page=10) # Pass db session
    
    # Assert
    assert "documents" in result, "Result should contain 'documents' key"
    assert "pagination" in result, "Result should contain 'pagination' key"
    assert len(result["documents"]) == 3, f"Expected 3 documents, got {len(result['documents'])}"
    assert result["pagination"]["total"] == 3, f"Expected pagination total 3, got {result['pagination']['total']}"
    
    # Test pagination
    result_pagination = document_service.get_documents(db=db, page=1, per_page=2) # Pass db session
    assert len(result_pagination["documents"]) == 2, f"Expected 2 documents for per_page=2, got {len(result_pagination['documents'])}"
    assert result_pagination["pagination"]["total"] == 3, f"Expected pagination total 3, got {result_pagination['pagination']['total']}"
    assert result_pagination["pagination"]["pages"] == 2, f"Expected 2 pages, got {result_pagination['pagination']['pages']}"

def test_get_documents_with_filters(db: Session, test_documents, test_tags, test_tenant):
    """Test retrieving documents with various filters."""
    # Arrange
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    
    # Act: Filter by tag
    tag_to_filter = test_tags[0].name
    result_tag_filter = document_service.get_documents(db=db, tags=[tag_to_filter]) # Pass db session
    
    # Assert: Tag filter
    assert len(result_tag_filter["documents"]) > 0, f"Expected documents when filtering by tag '{tag_to_filter}', got none."
    for doc_dict in result_tag_filter["documents"]:
        assert tag_to_filter in doc_dict["tags"], f"Document {doc_dict['id']} should have tag '{tag_to_filter}'"
    
    # Act: Filter by date (expecting no documents as date is current)
    from_date = datetime.utcnow().isoformat()
    result_date_filter = document_service.get_documents(db=db, date_from=from_date) # Pass db session
    
    # Assert: Date filter
    assert len(result_date_filter["documents"]) == 0, f"Expected 0 documents when filtering from_date='{from_date}', got {len(result_date_filter['documents'])}"

def test_get_document(db: Session, test_documents, test_tenant):
    """Test retrieving a specific document by its ID."""
    # Arrange
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    doc_to_get = test_documents[0] # Assuming this doc has 2 chunks from fixture setup
    
    # Act
    result = document_service.get_document(db=db, doc_id=str(doc_to_get.id)) # Pass db session
    
    # Assert
    assert result["id"] == str(doc_to_get.id), f"Expected document ID {doc_to_get.id}, got {result['id']}"
    assert result["title"] == doc_to_get.title, f"Expected title '{doc_to_get.title}', got '{result['title']}'"
    assert "preview_chunks" in result, "Result should contain 'preview_chunks' key"
    assert len(result["preview_chunks"]) == 2, f"Expected 2 preview chunks, got {len(result['preview_chunks'])}"
    # This assertion depends on specific content from test_documents fixture
    assert "Content for document 1, chunk 1" in result["preview_chunks"][0]["content"], "Preview chunk content mismatch"


def test_add_and_remove_tag(db: Session, test_documents, test_tenant):
    """Test adding and then removing a tag from a document."""
    # Arrange
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    doc_id_str = str(test_documents[0].id)
    tag_name_to_manage = "new-unique-test-tag"

    # Act: Add tag
    result_add = document_service.add_tag(db=db, doc_id=doc_id_str, tag_name=tag_name_to_manage) # Pass db session
    # Assert: Add tag
    assert "message" in result_add, "Add tag response should contain 'message' key"
    assert f"Tag '{tag_name_to_manage}' added to document {doc_id_str}" in result_add["message"], f"Expected add success message for tag '{tag_name_to_manage}' on doc {doc_id_str}, got '{result_add['message']}'"
    
    # Act: Verify tag was added
    doc_after_add = document_service.get_document(db=db, doc_id=doc_id_str) # Pass db session
    # Assert: Tag presence
    assert tag_name_to_manage in doc_after_add["tags"], f"Tag '{tag_name_to_manage}' should be in document tags after adding"
    
    # Act: Remove tag
    result_remove = document_service.remove_tag(db=db, doc_id=doc_id_str, tag_name=tag_name_to_manage) # Pass db session
    # Assert: Remove tag
    assert "message" in result_remove, "Remove tag response should contain 'message' key"
    assert f"Tag '{tag_name_to_manage}' removed from document {doc_id_str}" in result_remove["message"], f"Expected remove success message for tag '{tag_name_to_manage}' on doc {doc_id_str}, got '{result_remove['message']}'"
    
    # Act: Verify tag was removed
    doc_after_remove = document_service.get_document(db=db, doc_id=doc_id_str) # Pass db session
    # Assert: Tag absence
    assert tag_name_to_manage not in doc_after_remove["tags"], f"Tag '{tag_name_to_manage}' should not be in document tags after removal"

def test_generate_summary(db: Session, test_documents, test_tenant):
    """Test generating a summary for a document."""
    # Arrange
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    doc_id_str = str(test_documents[0].id)
    
    # Act
    result = document_service.generate_summary(db=db, doc_id=doc_id_str) # Pass db session
    
    # Assert
    assert "summary" in result, "Generate summary response should contain 'summary' key"
    assert result["summary"], "Summary should not be empty"

def test_get_signed_download_url(db: Session, test_documents, test_tenant, mock_storage_service):
    """Test obtaining a signed URL for document download."""
    # Arrange
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    document_service.storage_service = mock_storage_service # Inject mock
    doc_to_download = test_documents[0]
    
    # Act
    result = document_service.get_signed_download_url(db=db, doc_id=str(doc_to_download.id)) # Pass db session
    
    # Assert
    assert "url" in result, "Download URL response should contain 'url' key"
    assert "expires_at" in result, "Download URL response should contain 'expires_at' key"
    assert "filename" in result, "Download URL response should contain 'filename' key"
    assert doc_to_download.filename == result["filename"], f"Expected filename '{doc_to_download.filename}', got '{result['filename']}'"
    assert "mock-storage.example.com" in result["url"], f"Expected 'mock-storage.example.com' in URL, got '{result['url']}'"
    assert doc_to_download.filename in result["url"], f"Expected original filename '{doc_to_download.filename}' in URL path, got '{result['url']}'"


def test_get_signed_upload_url(db: Session, test_tenant, mock_storage_service): # Assuming user_id not strictly needed if not interacting with user-specific data
    """Test obtaining a signed URL for document upload."""
    # Arrange
    user_id_for_service = str(uuid4()) # Generate a dummy user_id if required by constructor
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=user_id_for_service)
    document_service.storage_service = mock_storage_service # Inject mock
    
    # Act
    result = document_service.get_signed_upload_url(
        filename="test-upload.txt",
        content_type="text/plain"
        # size is not used by the service method, so removed from here
    )
    
    # Assert
    assert "upload_url" in result, "Upload URL response should contain 'upload_url' key"
    assert "expires_at" in result, "Upload URL response should contain 'expires_at' key"
    assert "file_path" in result, "Upload URL response should contain 'file_path' key"
    assert "doc_id" in result, "Upload URL response should contain 'doc_id' key"
    assert "mock-storage.example.com" in result["upload_url"], f"Expected 'mock-storage.example.com' in upload_url, got '{result['upload_url']}'"
    assert "documents/" in result["file_path"], f"Expected 'documents/' in file_path, got '{result['file_path']}'"
    assert "test-upload.txt" in result["file_path"], f"Expected 'test-upload.txt' in file_path, got '{result['file_path']}'"

def test_extract_text_methods(db: Session, test_tenant): # Assuming user_id not strictly needed
    """Test internal text extraction methods for different file types."""
    # Arrange
    document_service = DocumentService(tenant_id=str(test_tenant.id)) # user_id might not be needed for _extract_text
    
    # Test TXT extraction
    txt_content = b"Este es un archivo de texto simple para pruebas."
    txt_file = io.BytesIO(txt_content)
    
    # Act
    txt_text = document_service._extract_text(txt_file, "txt")
    
    # Assert
    assert txt_text.strip() == txt_content.decode().strip(), "Extracted TXT content does not match original"
    
    # Note: Tests for PDF, DOCX, CSV, and Excel would require actual files
    # o mocks más complejos de sus respectivas bibliotecas
