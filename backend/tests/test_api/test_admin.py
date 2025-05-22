import pytest
from fastapi.testclient import TestClient
from uuid import uuid4

def test_list_users(client, test_user, test_superuser, superuser_token_headers):
    """Prueba para listar usuarios (solo admin)"""
    # Debug: Verificar que el superuser tiene permisos
    print(f"DEBUG - Superuser ID: {test_superuser.id}")
    print(f"DEBUG - Is superuser: {test_superuser.is_superuser}")
    print(f"DEBUG - Token headers: {superuser_token_headers}")
    
    response = client.get(
        "/api/v1/admin/users",
        headers=superuser_token_headers
    )
    
    print(f"DEBUG - Response status: {response.status_code}")
    print(f"DEBUG - Response content: {response.text}")
    
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
    
    print(f"DEBUG - Auth test status: {response.status_code}")
    print(f"DEBUG - Auth test content: {response.text}")
    
    # Puede ser 403 (Forbidden) o 401 (Unauthorized)
    assert response.status_code in [401, 403]
    
    # Verificar mensaje de error apropiado
    content = response.json()
    assert "detail" in content
    # Mensaje puede variar, así que verificamos contenido general
    assert any(keyword in content["detail"].lower() for keyword in ["privilege", "permission", "forbidden", "unauthorized"])

def test_create_user(client, test_tenant, superuser_token_headers):
    """Prueba para crear un usuario (solo admin)"""
    user_data = {
        "email": "newadminuser@example.com",
        "password": "password123",
        "full_name": "New Admin User",
        "is_superuser": True,
        "tenant_id": str(test_tenant.id)
    }
    
    response = client.post(
        "/api/v1/admin/users",
        headers=superuser_token_headers,
        json=user_data
    )
    
    print(f"DEBUG - Create user status: {response.status_code}")
    print(f"DEBUG - Create user content: {response.text}")
    
    assert response.status_code == 200
    content = response.json()
    assert content["email"] == "newadminuser@example.com"
    assert content["full_name"] == "New Admin User"
    assert content["is_superuser"] is True
    assert content["tenant_id"] == str(test_tenant.id)

def test_create_user_duplicate_email(client, test_user, superuser_token_headers):
    """Prueba para crear un usuario con email duplicado"""
    user_data = {
        "email": test_user.email,  # Email existente
        "password": "password123",
        "full_name": "Duplicate Email User",
        "is_superuser": False,
        "tenant_id": str(test_user.tenant_id)
    }
    
    response = client.post(
        "/api/v1/admin/users",
        headers=superuser_token_headers,
        json=user_data
    )
    
    print(f"DEBUG - Duplicate email status: {response.status_code}")
    print(f"DEBUG - Duplicate email content: {response.text}")
    
    assert response.status_code == 400
    content = response.json()
    assert "detail" in content
    assert "email" in content["detail"].lower()
    assert any(keyword in content["detail"].lower() for keyword in ["registrado", "existe", "duplicate", "already"])

def test_get_user(client, test_user, superuser_token_headers):
    """Prueba para obtener un usuario específico (solo admin)"""
    response = client.get(
        f"/api/v1/admin/users/{test_user.id}",
        headers=superuser_token_headers
    )
    
    print(f"DEBUG - Get user status: {response.status_code}")
    print(f"DEBUG - Get user content: {response.text}")
    
    assert response.status_code == 200
    content = response.json()
    assert content["id"] == str(test_user.id)
    assert content["email"] == test_user.email
    assert content["full_name"] == test_user.full_name

def test_update_user(client, test_user, superuser_token_headers):
    """Prueba para actualizar un usuario (solo admin)"""
    update_data = {
        "full_name": "Updated Test User",
        "is_active": True
    }
    
    response = client.put(
        f"/api/v1/admin/users/{test_user.id}",
        headers=superuser_token_headers,
        json=update_data
    )
    
    print(f"DEBUG - Update user status: {response.status_code}")
    print(f"DEBUG - Update user content: {response.text}")
    
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
    
    print(f"DEBUG - Delete user status: {response.status_code}")
    print(f"DEBUG - Delete user content: {response.text}")
    
    assert response.status_code == 200
    content = response.json()
    assert "message" in content
    assert "eliminado exitosamente" in content["message"]
    
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
    
    print(f"DEBUG - Delete self status: {response.status_code}")
    print(f"DEBUG - Delete self content: {response.text}")
    
    assert response.status_code == 400
    content = response.json()
    assert "detail" in content
    assert any(keyword in content["detail"].lower() for keyword in ["propio", "self", "mismo"])

def test_list_all_documents(client, test_documents, superuser_token_headers):
    """Prueba para listar todos los documentos (solo admin)"""
    response = client.get(
        "/api/v1/admin/documents",
        headers=superuser_token_headers
    )
    
    print(f"DEBUG - List documents status: {response.status_code}")
    print(f"DEBUG - List documents content: {response.text}")
    
    assert response.status_code == 200
    content = response.json()
    assert "documents" in content
    assert "pagination" in content
    # Más flexible con el número de documentos
    assert isinstance(content["documents"], list)
    assert isinstance(content["pagination"], dict)
    assert "total" in content["pagination"]

def test_get_system_stats(client, superuser_token_headers):
    """Prueba para obtener estadísticas del sistema (solo admin)"""
    response = client.get(
        "/api/v1/admin/stats",
        headers=superuser_token_headers
    )
    
    print(f"DEBUG - System stats status: {response.status_code}")
    print(f"DEBUG - System stats content: {response.text}")
    
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
    
    print(f"DEBUG - Ollama model status: {response.status_code}")
    print(f"DEBUG - Ollama model content: {response.text}")
    
    assert response.status_code == 200
    content = response.json()
    assert "message" in content
    assert "llama2" in content["message"]