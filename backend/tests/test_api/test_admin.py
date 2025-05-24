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
    
    assert response.status_code == 200, f"Expected status 200 but got {response.status_code}. Response: {response.text}"
    content = response.json()
    assert isinstance(content, list), f"Expected response content to be a list, got {type(content)}"
    assert len(content) >= 2, f"Expected at least 2 users, got {len(content)}"
    
    # Verificar que los usuarios existen en la respuesta
    user_emails = [user["email"] for user in content]
    assert test_user.email in user_emails, f"Expected email '{test_user.email}' not found in response: {user_emails}"
    assert test_superuser.email in user_emails, f"Expected email '{test_superuser.email}' not found in response: {user_emails}"

def test_list_users_unauthorized(client, normal_user_token_headers):
    """Prueba para listar usuarios sin permisos de admin"""
    response = client.get(
        "/api/v1/admin/users",
        headers=normal_user_token_headers
    )
    
    print(f"DEBUG - Auth test status: {response.status_code}")
    print(f"DEBUG - Auth test content: {response.text}")
    
    # Puede ser 403 (Forbidden) o 401 (Unauthorized)
    assert response.status_code in [401, 403], f"Expected status 401 or 403 but got {response.status_code}. Response: {response.text}"
    
    # Verificar mensaje de error apropiado
    content = response.json()
    assert "detail" in content, "Error response JSON should contain 'detail' key"
    # Mensaje puede variar, así que verificamos contenido general
    assert any(keyword in content["detail"].lower() for keyword in ["privilege", "permission", "forbidden", "unauthorized"]), f"Error detail '{content['detail']}' does not indicate an authorization error."

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
    
    assert response.status_code == 200, f"Expected status 200 but got {response.status_code}. Response: {response.text}"
    content = response.json()
    assert content["email"] == user_data["email"], f"Expected email '{user_data['email']}', got '{content['email']}'"
    assert content["full_name"] == user_data["full_name"], f"Expected full_name '{user_data['full_name']}', got '{content['full_name']}'"
    assert content["is_superuser"] is user_data["is_superuser"], f"Expected is_superuser '{user_data['is_superuser']}', got '{content['is_superuser']}'"
    assert content["tenant_id"] == user_data["tenant_id"], f"Expected tenant_id '{user_data['tenant_id']}', got '{content['tenant_id']}'"

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
    
    assert response.status_code == 400, f"Expected status 400 but got {response.status_code}. Response: {response.text}"
    content = response.json()
    assert "detail" in content, "Error response JSON should contain 'detail' key"
    assert "email" in content["detail"].lower(), f"Error detail '{content['detail']}' should mention 'email'"
    assert any(keyword in content["detail"].lower() for keyword in ["registrado", "existe", "duplicate", "already"]), f"Error detail '{content['detail']}' does not indicate a duplicate email error."

def test_get_user(client, test_user, superuser_token_headers):
    """Prueba para obtener un usuario específico (solo admin)"""
    response = client.get(
        f"/api/v1/admin/users/{test_user.id}",
        headers=superuser_token_headers
    )
    
    print(f"DEBUG - Get user status: {response.status_code}")
    print(f"DEBUG - Get user content: {response.text}")
    
    assert response.status_code == 200, f"Expected status 200 but got {response.status_code}. Response: {response.text}"
    content = response.json()
    assert content["id"] == str(test_user.id), f"Expected user ID '{test_user.id}', got '{content['id']}'"
    assert content["email"] == test_user.email, f"Expected email '{test_user.email}', got '{content['email']}'"
    assert content["full_name"] == test_user.full_name, f"Expected full_name '{test_user.full_name}', got '{content['full_name']}'"

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
    
    assert response.status_code == 200, f"Expected status 200 but got {response.status_code}. Response: {response.text}"
    content = response.json()
    assert content["id"] == str(test_user.id), f"Expected user ID '{test_user.id}', got '{content['id']}'"
    assert content["email"] == test_user.email, f"Expected email '{test_user.email}', got '{content['email']}'" # Email should not change
    assert content["full_name"] == update_data["full_name"], f"Expected full_name '{update_data['full_name']}', got '{content['full_name']}'"
    assert content["is_active"] is update_data["is_active"], f"Expected is_active '{update_data['is_active']}', got '{content['is_active']}'"

def test_delete_user(client, test_user, superuser_token_headers):
    """Prueba para eliminar un usuario (solo admin)"""
    response = client.delete(
        f"/api/v1/admin/users/{test_user.id}",
        headers=superuser_token_headers
    )
    
    print(f"DEBUG - Delete user status: {response.status_code}")
    print(f"DEBUG - Delete user content: {response.text}")
    
    assert response.status_code == 200, f"Expected status 200 but got {response.status_code}. Response: {response.text}"
    content = response.json()
    assert "message" in content, "Delete response JSON should contain 'message' key"
    assert "eliminado exitosamente" in content["message"], f"Expected 'eliminado exitosamente' in message, got '{content['message']}'"
    
    # Verificar que el usuario fue eliminado
    response_get_deleted = client.get(
        f"/api/v1/admin/users/{test_user.id}",
        headers=superuser_token_headers
    )
    assert response_get_deleted.status_code == 404, f"Expected status 404 after deleting user, but got {response_get_deleted.status_code}. Response: {response_get_deleted.text}"

def test_delete_self(client, test_superuser, superuser_token_headers):
    """Prueba para evitar que un admin se elimine a sí mismo"""
    response = client.delete(
        f"/api/v1/admin/users/{test_superuser.id}",
        headers=superuser_token_headers
    )
    
    print(f"DEBUG - Delete self status: {response.status_code}")
    print(f"DEBUG - Delete self content: {response.text}")
    
    assert response.status_code == 400, f"Expected status 400 but got {response.status_code}. Response: {response.text}"
    content = response.json()
    assert "detail" in content, "Error response JSON should contain 'detail' key"
    assert any(keyword in content["detail"].lower() for keyword in ["propio", "self", "mismo"]), f"Error detail '{content['detail']}' does not indicate a self-deletion error."

def test_list_all_documents(client, test_documents, superuser_token_headers):
    """Prueba para listar todos los documentos (solo admin)"""
    response = client.get(
        "/api/v1/admin/documents",
        headers=superuser_token_headers
    )
    
    print(f"DEBUG - List documents status: {response.status_code}")
    print(f"DEBUG - List documents content: {response.text}")
    
    assert response.status_code == 200, f"Expected status 200 but got {response.status_code}. Response: {response.text}"
    content = response.json()
    assert "documents" in content, "Response JSON should contain 'documents' key"
    assert "pagination" in content, "Response JSON should contain 'pagination' key"
    # Más flexible con el número de documentos
    assert isinstance(content["documents"], list), f"Expected 'documents' to be a list, got {type(content['documents'])}"
    assert isinstance(content["pagination"], dict), f"Expected 'pagination' to be a dict, got {type(content['pagination'])}"
    assert "total" in content["pagination"], "Pagination data should contain 'total' key"

def test_get_system_stats(client, superuser_token_headers):
    """Prueba para obtener estadísticas del sistema (solo admin)"""
    response = client.get(
        "/api/v1/admin/stats",
        headers=superuser_token_headers
    )
    
    print(f"DEBUG - System stats status: {response.status_code}")
    print(f"DEBUG - System stats content: {response.text}")
    
    assert response.status_code == 200, f"Expected status 200 but got {response.status_code}. Response: {response.text}"
    content = response.json()
    assert "users" in content, "Stats response should contain 'users' key"
    assert "tenants" in content, "Stats response should contain 'tenants' key"
    assert "documents" in content, "Stats response should contain 'documents' key"
    assert "storage" in content, "Stats response should contain 'storage' key"
    
    # Verificar estructura de 'users'
    assert "total" in content["users"], "'users' stats should contain 'total' key"
    assert "active" in content["users"], "'users' stats should contain 'active' key"
    # Verificar estructura de 'tenants'
    assert "total" in content["tenants"], "'tenants' stats should contain 'total' key"
    assert "active" in content["tenants"], "'tenants' stats should contain 'active' key"
    # Verificar estructura de 'documents'
    assert "total" in content["documents"], "'documents' stats should contain 'total' key"
    assert "indexed" in content["documents"], "'documents' stats should contain 'indexed' key"
    assert "by_type" in content["documents"], "'documents' stats should contain 'by_type' key"
    # Verificar estructura de 'storage'
    assert "total_bytes" in content["storage"], "'storage' stats should contain 'total_bytes' key"

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
    
    assert response.status_code == 200, f"Expected status 200 but got {response.status_code}. Response: {response.text}"
    content = response.json()
    assert "message" in content, "Response JSON should contain 'message' key"
    assert "llama2" in content["message"], f"Expected 'llama2' in success message, got '{content['message']}'"