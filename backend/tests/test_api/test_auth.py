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
    new_user_email = "newuser_clerk@example.com"
    clerk_id_value = "clerk_test_12345"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": new_user_email,
            "password": "newpassword",
            "full_name": "New Clerk User",
            "tenant_id": str(test_tenant.id),
            "clerk_user_id": clerk_id_value
        }
    )
    assert response.status_code == 200
    content = response.json()
    assert content["email"] == new_user_email
    assert content["full_name"] == "New Clerk User"
    assert content["clerk_user_id"] == clerk_id_value
    assert content["is_active"] is True
    assert content["is_superuser"] is False
    assert content["image"] is None
    assert content["roles"] == []
    assert content["subscription"] is None

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
    assert content["email"] == "test@example.com"  # Assuming test_user's email
    assert content["full_name"] == "Test User"   # Assuming test_user's full_name
    assert "clerk_user_id" in content  # Check for presence
    assert "image" in content
    assert "roles" in content
    assert "subscription" in content
    # Specific values for clerk_user_id, image, roles, subscription will depend
    # on how the mock for the 'test_user' underlying normal_user_token_headers is set up.
    # For now, checking key presence is the primary goal.
    # Example: if test_user mock was augmented:
    # assert content["clerk_user_id"] == "expected_clerk_id_for_test_user"
    # assert content["roles"] == [{"id": "some_role_id", "name": "some_role", ...}]

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