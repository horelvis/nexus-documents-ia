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
    # For _validate_file and _create_document_record, storage_service, embedding_service, llm_service
    # are not directly called.
    service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(uuid4()))
    # If these services were used, you would mock them:
    # service.storage_service = MagicMock()
    # service.embedding_service = MagicMock()
    # service.llm_service = MagicMock()
    return service

# --- Tests for _validate_file ---

@pytest.mark.asyncio
async def test_validate_file_success(document_service_instance):
    mock_file_content = b"This is a test file."
    mock_upload_file = AsyncMock(spec=UploadFile)
    mock_upload_file.filename = "test.pdf"
    mock_upload_file.read = AsyncMock(return_value=mock_file_content)
    mock_upload_file.seek = AsyncMock() # Mock seek if it's called

    # Ensure 'pdf' is in ALLOWED_EXTENSIONS
    original_allowed_extensions = settings.ALLOWED_EXTENSIONS
    settings.ALLOWED_EXTENSIONS = ["pdf", "txt"]
    
    file_ext, contents, file_size = await document_service_instance._validate_file(mock_upload_file, "test.pdf")
    
    assert file_ext == "pdf"
    assert contents == mock_file_content
    assert file_size == len(mock_file_content)
    mock_upload_file.read.assert_called_once()
    
    settings.ALLOWED_EXTENSIONS = original_allowed_extensions # Reset

@pytest.mark.asyncio
async def test_validate_file_invalid_extension(document_service_instance):
    mock_upload_file = AsyncMock(spec=UploadFile)
    mock_upload_file.filename = "test.exe"
    mock_upload_file.read = AsyncMock(return_value=b"some content")
    mock_upload_file.seek = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await document_service_instance._validate_file(mock_upload_file, "test.exe")
    assert exc_info.value.status_code == 400
    assert "Tipo de archivo no permitido" in exc_info.value.detail

@pytest.mark.asyncio
async def test_validate_file_too_large(document_service_instance):
    mock_file_content = b"a" * (settings.MAX_UPLOAD_SIZE + 1)
    mock_upload_file = AsyncMock(spec=UploadFile)
    mock_upload_file.filename = "large_file.txt"
    mock_upload_file.read = AsyncMock(return_value=mock_file_content)
    mock_upload_file.seek = AsyncMock()

    original_allowed_extensions = settings.ALLOWED_EXTENSIONS
    settings.ALLOWED_EXTENSIONS = ["txt"] # Ensure txt is allowed for this test

    with pytest.raises(HTTPException) as exc_info:
        await document_service_instance._validate_file(mock_upload_file, "large_file.txt")
    assert exc_info.value.status_code == 400
    assert "Tamaño de archivo excede el límite" in exc_info.value.detail

    settings.ALLOWED_EXTENSIONS = original_allowed_extensions

@pytest.mark.asyncio
async def test_validate_file_empty(document_service_instance):
    mock_upload_file = AsyncMock(spec=UploadFile)
    mock_upload_file.filename = "empty.txt"
    mock_upload_file.read = AsyncMock(return_value=b"") # Empty content
    mock_upload_file.seek = AsyncMock()
    
    original_allowed_extensions = settings.ALLOWED_EXTENSIONS
    settings.ALLOWED_EXTENSIONS = ["txt"]

    with pytest.raises(HTTPException) as exc_info:
        await document_service_instance._validate_file(mock_upload_file, "empty.txt")
    assert exc_info.value.status_code == 400
    assert "El archivo está vacío" in exc_info.value.detail

    settings.ALLOWED_EXTENSIONS = original_allowed_extensions

# --- Tests for _create_document_record ---

def test_create_document_record_success(document_service_instance, mock_db_session):
    title = "Test Document"
    description = "A document for testing"
    filename = "test_doc.pdf"
    file_ext = "pdf"
    file_size = 1024
    tags_input = ["tag1", "new_tag"] # tag1 exists, new_tag does not

    # Mock Tag query: tag1 exists, new_tag does not
    existing_tag_obj = Tag(id=1, name="tag1", tenant_id=document_service_instance.tenant_id)
    
    def mock_tag_query_logic(model):
        if model == Tag:
            filter_mock = MagicMock()
            def first_side_effect():
                # This part needs to be dynamic based on the filter's criteria,
                # which is tricky with a simple side_effect list.
                # For simplicity, we assume the filter check is for 'name' and 'tenant_id'.
                # This mock is simplified; a more robust mock would inspect the filter arguments.
                # Let's simulate based on the tag name passed to filter.
                # This requires knowing how filter is called, which is inside the method.
                # A more advanced mock might use a callback for side_effect.
                current_call_args = filter_mock.call_args
                if current_call_args and "name='tag1'" in str(current_call_args): # Simplified check
                     return existing_tag_obj
                return None # For "new_tag"
            
            filter_mock.first.side_effect = first_side_effect 
            # This is a bit of a hack; ideally, you'd inspect the actual filter arguments.
            # A better way is to set side_effect on filter().first() based on a list of expected calls.
            # For this example, let's assume two calls to first(), one for "tag1", one for "new_tag".
            mock_db_session.query(Tag).filter().first.side_effect = [
                existing_tag_obj, # For "tag1"
                None              # For "new_tag"
            ]
            return filter_mock
        return MagicMock() # Default for other queries
        
    mock_db_session.query.side_effect = mock_tag_query_logic


    db_document = document_service_instance._create_document_record(
        db=mock_db_session,
        title=title,
        description=description,
        filename=filename,
        file_ext=file_ext,
        file_size=file_size,
        tags=tags_input
    )

    assert isinstance(db_document, Document)
    assert db_document.title == title
    assert db_document.description == description
    assert db_document.filename == filename
    assert db_document.file_type == file_ext
    assert db_document.file_size == file_size
    assert db_document.tenant_id == UUID(document_service_instance.tenant_id)
    assert db_document.created_by == UUID(document_service_instance.user_id)
    assert db_document.indexed == IndexingStatus.PROCESSING
    assert filename in db_document.file_path
    assert str(db_document.id) in db_document.file_path
    
    # Check tags
    assert len(db_document.tags) == 2
    # Order might not be guaranteed, so check names
    tag_names_in_doc = sorted([tag.name for tag in db_document.tags])
    assert tag_names_in_doc == sorted(["tag1", "new_tag"])

    # Check db calls
    # mock_db_session.add.assert_any_call(db_document) # Document is added
    # One add for the new_tag, one for the document itself
    assert mock_db_session.add.call_count >= 2 # At least document and new tag
    
    # Check that a new Tag object was created for "new_tag"
    added_objects = [call.args[0] for call in mock_db_session.add.call_args_list]
    assert any(isinstance(obj, Document) and obj.title == title for obj in added_objects)
    assert any(isinstance(obj, Tag) and obj.name == "new_tag" for obj in added_objects)


    mock_db_session.flush.assert_called()
    mock_db_session.refresh.assert_called_with(db_document)


def test_create_document_record_no_tags(document_service_instance, mock_db_session):
    title = "No Tags Doc"
    # ... other params ...

    db_document = document_service_instance._create_document_record(
        db=mock_db_session,
        title=title,
        description=None,
        filename="notags.txt",
        file_ext="txt",
        file_size=100,
        tags=[] # No tags
    )

    assert isinstance(db_document, Document)
    assert db_document.title == title
    assert len(db_document.tags) == 0
    
    # Assert that db.add was called for the document, but not for any new tags
    # (unless Tag query was still made and returned None)
    mock_db_session.query(Tag).filter().first.assert_not_called() # No tag lookups if tags list is empty
    
    # Check that only the document was added
    added_objects = [call.args[0] for call in mock_db_session.add.call_args_list]
    assert any(isinstance(obj, Document) and obj.title == title for obj in added_objects)
    assert not any(isinstance(obj, Tag) for obj in added_objects)

    mock_db_session.flush.assert_called_once() # Only document related flush
    mock_db_session.refresh.assert_called_once_with(db_document)


# --- Keep existing tests and update them if needed ---

def test_get_documents(db, test_documents, test_tenant):
    """Prueba para obtener lista de documentos"""
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    
    result = document_service.get_documents(page=1, per_page=10)
    
    assert "documents" in result
    assert "pagination" in result
    assert len(result["documents"]) == 3
    assert result["pagination"]["total"] == 3
    
    # Probar paginación
    result = document_service.get_documents(page=1, per_page=2)
    assert len(result["documents"]) == 2
    assert result["pagination"]["total"] == 3
    assert result["pagination"]["pages"] == 2

def test_get_documents_with_filters(db, test_documents, test_tags, test_tenant):
    """Prueba para obtener documentos con filtros"""
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    
    # Filtrar por tag
    result = document_service.get_documents(tags=[test_tags[0].name])
    assert len(result["documents"]) > 0
    for doc in result["documents"]:
        assert test_tags[0].name in doc["tags"]
    
    # Filtrar por fecha
    from_date = datetime.utcnow().isoformat()
    result = document_service.get_documents(date_from=from_date)
    assert len(result["documents"]) == 0  # No debería haber documentos después de la fecha actual

def test_get_document(db, test_documents, test_tenant):
    """Prueba para obtener un documento específico"""
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    
    result = document_service.get_document(doc_id=str(test_documents[0].id))
    
    assert result["id"] == str(test_documents[0].id)
    assert result["title"] == test_documents[0].title
    assert "preview_chunks" in result
    assert len(result["preview_chunks"]) == 2  # Dos chunks creados en fixture

def test_add_and_remove_tag(db, test_documents, test_tenant):
    """Prueba para añadir y eliminar etiquetas"""
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    
    # Añadir tag
    tag_name = "new-test-tag"
    result = document_service.add_tag(doc_id=str(test_documents[0].id), tag_name=tag_name)
    assert "message" in result
    assert tag_name in result["message"]
    
    # Verificar que se añadió
    doc = document_service.get_document(doc_id=str(test_documents[0].id))
    assert tag_name in doc["tags"]
    
    # Eliminar tag
    result = document_service.remove_tag(doc_id=str(test_documents[0].id), tag_name=tag_name)
    assert "message" in result
    assert "removed" in result["message"]
    
    # Verificar que se eliminó
    doc = document_service.get_document(doc_id=str(test_documents[0].id))
    assert tag_name not in doc["tags"]

def test_generate_summary(db, test_documents, test_tenant, mock_llm_service):
    """Prueba para generar resumen de documento"""
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    document_service.llm_service = mock_llm_service
    
    result = document_service.generate_summary(doc_id=str(test_documents[0].id))
    
    assert "summary" in result
    assert "mock summary" in result["summary"].lower()

def test_get_signed_download_url(db, test_documents, test_tenant, mock_storage_service):
    """Prueba para obtener URL firmada de descarga"""
    document_service = DocumentService(tenant_id=str(test_tenant.id), user_id=str(test_documents[0].created_by))
    document_service.storage_service = mock_storage_service
    
    result = document_service.get_signed_download_url(doc_id=str(test_documents[0].id))
    
    assert "url" in result
    assert "expires_at" in result
    assert "filename" in result
    assert test_documents[0].filename == result["filename"]
    assert "mock-storage.example.com" in result["url"]

def test_get_signed_upload_url(db, test_tenant, mock_storage_service):
    """Prueba para obtener URL firmada de carga"""
    document_service = DocumentService(tenant_id=str(test_tenant.id))
    document_service.storage_service = mock_storage_service
    
    result = document_service.get_signed_upload_url(
        filename="test-upload.txt",
        content_type="text/plain"
    )
    
    assert "upload_url" in result
    assert "expires_at" in result
    assert "file_path" in result
    assert "doc_id" in result
    assert "mock-storage.example.com" in result["upload_url"]
    assert "documents/" in result["file_path"]
    assert "test-upload.txt" in result["file_path"]

def test_extract_text_methods(db, test_tenant):
    """Prueba para métodos de extracción de texto"""
    document_service = DocumentService(tenant_id=str(test_tenant.id))
    
    # Prueba con TXT
    txt_content = b"Este es un archivo de texto simple para pruebas."
    txt_file = io.BytesIO(txt_content)
    txt_text = document_service._extract_text(txt_file, "txt")
    assert txt_text.strip() == txt_content.decode().strip()
    
    # Nota: Las pruebas para PDF, DOCX, CSV y Excel requieren archivos reales
    # o mocks más complejos de sus respectivas bibliotecas