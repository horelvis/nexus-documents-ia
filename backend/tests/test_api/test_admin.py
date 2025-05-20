import pytest
from fastapi.testclient import TestClient
from uuid import uuid4

def test_list_users(client, test_user, test_superuser, superuser_token_headers):
    """Prueba para listar usuarios (solo admin)"""
    response = client.get(
        "/api/v1/admin/users",
        headers=superuser_token_headers
    )
    
    assert response.status_code == 200
    content = response.json()
    assert isinstance(content, list)
    assert len(content) >= 2  # Al menos los dos usuarios creados
    
    # Verificar que los usuarios existen en la respuesta
    user_emails = [user["email"] for user in content]
    assert test_user.email in user_emails
    assert test_superuser.email in user_emails

def test_list_users_unauthorized(client, normal_user_token_headers):
    """Prueba para listar usuarios sin permisos de admin"""
    response = client.get(
        "/api/v1/admin/users",
        headers=normal_user_token_headers
    )
    
    assert response.status_code == 403
    assert "The user doesn't have enough privileges" in response.json()["detail"]

def test_create_user(client, test_tenant, superuser_token_headers):
    """Prueba para crear un usuario (solo admin)"""
    response = client.post(
        "/api/v1/admin/users",
        headers=superuser_token_headers,
        json={
            "email": "newadminuser@example.com",
            "password": "password123",
            "full_name": "New Admin User",
            "is_superuser": True,
            "tenant_id": str(test_tenant.id)
        }
    )
    
    assert response.status_code == 200
    content = response.json()
    assert content["email"] == "newadminuser@example.com"
    assert content["full_name"] == "New Admin User"
    assert content["is_superuser"] is True
    assert content["tenant_id"] == str(test_tenant.id)

def test_create_user_duplicate_email(client, test_user, superuser_token_headers):
    """Prueba para crear un usuario con email duplicado"""
    response = client.post(
        "/api/v1/admin/users",
        headers=superuser_token_headers,
        json={
            "email": test_user.email,  # Email existente
            "password": "password123",
            "full_name": "Duplicate Email User",
            "is_superuser": False,
            "tenant_id": str(test_user.tenant_id)
        }
    )
    
    assert response.status_code == 400
    assert "El email ya está registrado" in response.json()["detail"]

def test_get_user(client, test_user, superuser_token_headers):
    """Prueba para obtener un usuario específico (solo admin)"""
    response = client.get(
        f"/api/v1/admin/users/{test_user.id}",
        headers=superuser_token_headers
    )
    
    assert response.status_code == 200
    content = response.json()
    assert content["id"] == str(test_user.id)
    assert content["email"] == test_user.email
    assert content["full_name"] == test_user.full_name

def test_update_user(client, test_user, superuser_token_headers):
    """Prueba para actualizar un usuario (solo admin)"""
    response = client.put(
        f"/api/v1/admin/users/{test_user.id}",
        headers=superuser_token_headers,
        json={
            "full_name": "Updated Test User",
            "is_active": True
        }
    )
    
    assert response.status_code == 200
    content = response.json()
    assert content["id"] == str(test_user.id)
    assert content["email"] == test_user.email
    assert content["full_name"] == "Updated Test User"
    assert content["is_active"] is True

def test_delete_user(client, test_user, superuser_token_headers):
    """Prueba para eliminar un usuario (solo admin)"""
    response = client.delete(
        f"/api/v1/admin/users/{test_user.id}",
        headers=superuser_token_headers
    )
    
    assert response.status_code == 200
    assert "eliminado exitosamente" in response.json()["message"]
    
    # Verificar que el usuario fue eliminado
    response = client.get(
        f"/api/v1/admin/users/{test_user.id}",
        headers=superuser_token_headers
    )
    assert response.status_code == 404

def test_delete_self(client, test_superuser, superuser_token_headers):
    """Prueba para evitar que un admin se elimine a sí mismo"""
    response = client.delete(
        f"/api/v1/admin/users/{test_superuser.id}",
        headers=superuser_token_headers
    )
    
    assert response.status_code == 400
    assert "No puedes eliminar tu propio usuario" in response.json()["detail"]

def test_list_all_documents(client, test_documents, superuser_token_headers):
    """Prueba para listar todos los documentos (solo admin)"""
    response = client.get(
        "/api/v1/admin/documents",
        headers=superuser_token_headers
    )
    
    assert response.status_code == 200
    content = response.json()
    assert "documents" in content
    assert "pagination" in content
    assert len(content["documents"]) == 3  # Los tres documentos de prueba
    assert content["pagination"]["total"] == 3

def test_get_system_stats(client, superuser_token_headers):
    """Prueba para obtener estadísticas del sistema (solo admin)"""
    response = client.get(
        "/api/v1/admin/stats",
        headers=superuser_token_headers
    )
    
    assert response.status_code == 200
    content = response.json()
    assert "users" in content
    assert "tenants" in content
    assert "documents" in content
    assert "storage" in content
    
    # Verificar estructura
    assert "total" in content["users"]
    assert "active" in content["users"]
    assert "total" in content["tenants"]
    assert "active" in content["tenants"]
    assert "total" in content["documents"]
    assert "indexed" in content["documents"]
    assert "by_type" in content["documents"]
    assert "total_bytes" in content["storage"]

def test_init_ollama_model(client, superuser_token_headers, monkeypatch):
    """Prueba para inicializar un modelo en Ollama (solo admin)"""
    # Mock de la respuesta de requests para Ollama
    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json_data = json_data
            self.text = "Mock response text"
        
        def json(self):
            return self._json_data
    
    def mock_get(*args, **kwargs):
        return MockResponse(200, {"models": []})
    
    def mock_post(*args, **kwargs):
        return MockResponse(200, {"status": "success"})
    
    # Aplicar los mocks
    import requests
    monkeypatch.setattr(requests, "get", mock_get)
    monkeypatch.setattr(requests, "post", mock_post)
    
    # Realizar la prueba
    response = client.post(
        "/api/v1/admin/init-ollama-model",
        headers=superuser_token_headers,
        json={"model_name": "llama2"}
    )
    
    assert response.status_code == 200
    content = response.json()
    assert "message" in content
    assert "llama2" in content["message"]
    assert "descargado exitosamente" in content["message"]