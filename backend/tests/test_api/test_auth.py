import pytest
from fastapi.testclient import TestClient

def test_login_success(client, test_user):
    """Prueba de login exitoso"""
    response = client.post(
        "/api/v1/auth/login/access-token",
        data={"username": test_user.email, "password": "password"}
    )
    assert response.status_code == 200
    content = response.json()
    assert "access_token" in content
    assert content["token_type"] == "bearer"

def test_login_wrong_password(client, test_user):
    """Prueba de login con contraseña incorrecta"""
    response = client.post(
        "/api/v1/auth/login/access-token",
        data={"username": test_user.email, "password": "wrong_password"}
    )
    assert response.status_code == 401
    content = response.json()
    assert "detail" in content
    assert "Incorrect email or password" in content["detail"]

def test_login_nonexistent_user(client):
    """Prueba de login con usuario inexistente"""
    response = client.post(
        "/api/v1/auth/login/access-token",
        data={"username": "nonexistent@example.com", "password": "password"}
    )
    assert response.status_code == 401

def test_register_user(client, test_tenant):
    """Prueba de registro de usuario"""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "newpassword",
            "full_name": "New User",
            "tenant_id": str(test_tenant.id)
        }
    )
    assert response.status_code == 200
    content = response.json()
    assert content["email"] == "newuser@example.com"
    assert content["full_name"] == "New User"
    assert content["is_active"] is True
    assert content["is_superuser"] is False

def test_register_existing_email(client, test_user):
    """Prueba de registro con email existente"""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": test_user.email,
            "password": "newpassword",
            "full_name": "Duplicate User",
            "tenant_id": str(test_user.tenant_id)
        }
    )
    assert response.status_code == 400
    content = response.json()
    assert "detail" in content
    assert "Email already registered" in content["detail"]

def test_get_current_user(client, normal_user_token_headers):
    """Prueba para obtener el usuario actual"""
    response = client.get(
        "/api/v1/auth/me",
        headers=normal_user_token_headers
    )
    assert response.status_code == 200
    content = response.json()
    assert content["email"] == "test@example.com"
    assert content["full_name"] == "Test User"

def test_access_without_token(client):
    """Prueba de acceso sin token"""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    content = response.json()
    assert "detail" in content
    assert "Not authenticated" in content["detail"]

def test_access_with_invalid_token(client):
    """Prueba de acceso con token inválido"""
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid_token"}
    )
    assert response.status_code == 403
    content = response.json()
    assert "detail" in content
    assert "Could not validate credentials" in content["detail"]