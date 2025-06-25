"""
Test cases para API de documentos - Backend Nexus
Usando pytest y httpx para pruebas de API
"""
import pytest
from httpx import AsyncClient
from datetime import datetime
import io
from PIL import Image
import PyPDF2

from app.main import app
from app.db.models import User, Document, Tenant
from tests.conftest import TestingSessionLocal


class TestDocumentAPI:
    """Casos de prueba para gestión de documentos"""

    @pytest.mark.asyncio
    async def test_upload_single_document(self, client: AsyncClient, auth_headers: dict):
        """TC-DOC-001: Subir documento individual"""
        # Crear un PDF de prueba
        pdf_content = b"%PDF-1.4\n%Fake PDF content for testing"
        files = {
            "file": ("test_document.pdf", pdf_content, "application/pdf")
        }
        
        response = await client.post(
            "/api/v1/documents/upload",
            files=files,
            headers=auth_headers,
            data={"tags": "test,automation"}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test_document.pdf"
        assert data["mime_type"] == "application/pdf"
        assert data["status"] == "processing"
        assert "test" in data["tags"]
        assert "automation" in data["tags"]

    @pytest.mark.asyncio
    async def test_upload_invalid_file_type(self, client: AsyncClient, auth_headers: dict):
        """TC-DOC-001: Rechazar archivos no soportados"""
        # Intentar subir un archivo .exe
        exe_content = b"MZ\x90\x00\x03\x00\x00\x00"  # Header de archivo ejecutable
        files = {
            "file": ("malicious.exe", exe_content, "application/x-msdownload")
        }
        
        response = await client.post(
            "/api/v1/documents/upload",
            files=files,
            headers=auth_headers
        )
        
        assert response.status_code == 400
        assert "Tipo de archivo no soportado" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_multiple_documents(self, client: AsyncClient, auth_headers: dict):
        """TC-DOC-002: Subir múltiples documentos"""
        # Crear múltiples archivos
        files = [
            ("files", ("doc1.pdf", b"%PDF-1.4\nDoc 1", "application/pdf")),
            ("files", ("doc2.txt", b"Document 2 content", "text/plain")),
            ("files", ("doc3.docx", b"PK\x03\x04", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
        ]
        
        response = await client.post(
            "/api/v1/documents/upload-multiple",
            files=files,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert len(data["documents"]) == 3
        assert data["total_uploaded"] == 3
        assert all(doc["status"] == "processing" for doc in data["documents"])

    @pytest.mark.asyncio
    async def test_upload_exceeds_limit(self, client: AsyncClient, auth_headers: dict):
        """TC-DOC-002: Respetar límite de archivos"""
        # Crear 11 archivos (límite es 10)
        files = []
        for i in range(11):
            files.append(
                ("files", (f"doc{i}.txt", f"Content {i}".encode(), "text/plain"))
            )
        
        response = await client.post(
            "/api/v1/documents/upload-multiple",
            files=files,
            headers=auth_headers
        )
        
        assert response.status_code == 400
        assert "Máximo 10 archivos permitidos" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_document_details(self, client: AsyncClient, auth_headers: dict, test_document: Document):
        """TC-DOC-003: Ver detalles de documento"""
        response = await client.get(
            f"/api/v1/documents/{test_document.id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_document.id)
        assert data["name"] == test_document.name
        assert data["size"] == test_document.size
        assert "created_at" in data
        assert "mime_type" in data
        assert "status" in data
        
        # Verificar análisis IA si está disponible
        if data["status"] == "completed":
            assert "ai_analysis" in data
            assert "summary" in data["ai_analysis"]
            assert "suggested_tags" in data["ai_analysis"]

    @pytest.mark.asyncio
    async def test_download_document(self, client: AsyncClient, auth_headers: dict, test_document: Document):
        """TC-DOC-004: Descargar documento"""
        response = await client.get(
            f"/api/v1/documents/{test_document.id}/download",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == test_document.mime_type
        assert f'filename="{test_document.name}"' in response.headers["content-disposition"]
        assert len(response.content) > 0

    @pytest.mark.asyncio
    async def test_delete_document(self, client: AsyncClient, auth_headers: dict, test_document: Document):
        """TC-DOC-005: Eliminar documento"""
        # Primero verificar que existe
        response = await client.get(
            f"/api/v1/documents/{test_document.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        # Eliminar documento
        response = await client.delete(
            f"/api/v1/documents/{test_document.id}",
            headers=auth_headers
        )
        
        assert response.status_code == 204
        
        # Verificar que fue eliminado
        response = await client.get(
            f"/api/v1/documents/{test_document.id}",
            headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_share_document(self, client: AsyncClient, auth_headers: dict, test_document: Document):
        """TC-DOC-006: Compartir documento"""
        share_data = {
            "recipient_email": "colleague@example.com",
            "permissions": "view",
            "message": "Por favor revisa este documento"
        }
        
        response = await client.post(
            f"/api/v1/documents/{test_document.id}/share",
            json=share_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["recipient_email"] == share_data["recipient_email"]
        assert data["permissions"] == share_data["permissions"]
        assert data["status"] == "pending"
        assert "share_link" in data

    @pytest.mark.asyncio
    async def test_list_documents_with_filters(self, client: AsyncClient, auth_headers: dict):
        """Prueba de listado con filtros"""
        # Listar sin filtros
        response = await client.get(
            "/api/v1/documents",
            headers=auth_headers
        )
        assert response.status_code == 200
        total_docs = response.json()["total"]
        
        # Filtrar por tipo
        response = await client.get(
            "/api/v1/documents?mime_type=application/pdf",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["total"] <= total_docs
        
        # Filtrar por fecha
        response = await client.get(
            "/api/v1/documents?created_after=2024-01-01",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        # Filtrar por tags
        response = await client.get(
            "/api/v1/documents?tags=important,urgent",
            headers=auth_headers
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_document_permissions(self, client: AsyncClient, auth_headers: dict, other_user_headers: dict, test_document: Document):
        """Verificar permisos de documentos"""
        # Usuario propietario puede acceder
        response = await client.get(
            f"/api/v1/documents/{test_document.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        # Otro usuario no puede acceder
        response = await client.get(
            f"/api/v1/documents/{test_document.id}",
            headers=other_user_headers
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_document_metadata(self, client: AsyncClient, auth_headers: dict, test_document: Document):
        """Actualizar metadatos del documento"""
        update_data = {
            "name": "Updated Document Name.pdf",
            "tags": ["updated", "test", "metadata"],
            "description": "This is an updated description"
        }
        
        response = await client.patch(
            f"/api/v1/documents/{test_document.id}",
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == update_data["name"]
        assert set(data["tags"]) == set(update_data["tags"])
        assert data["description"] == update_data["description"]