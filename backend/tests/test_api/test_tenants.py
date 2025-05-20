import pytest
from fastapi.testclient import TestClient
from uuid import uuid4

def test_list_tenants(client, test_tenant, superuser_token_headers):
    """Prueba para listar todos los tenants (solo admin)"""
    response = client.get(
        "/api/v1/tenants/",
        headers=superuser_token_headers
    )
    
    assert response.status_code == 200
    content = response.json()
    assert isinstance(content, list)
    assert len(content) >= 1  # Al menos el tenant de prueba
    
    # Verificar que el tenant de prueba está en la lista
    tenant_names = [tenant["name"] for tenant in content]
    assert test_tenant.name in tenant_names

def test_list_tenants_unauthorized(client, normal_user_token_headers):
    """Prueba para listar tenants sin permisos de admin"""
    response = client.get(
        "/api/v1/tenants/",
        headers=normal_user_token_headers
    )
    
    assert response.status_code == 403
    assert "enough privileges" in response.json()["detail"]

def test_create_tenant(client, superuser_token_headers):
    """Prueba para crear un nuevo tenant (solo admin)"""
    response = client.post(
        "/api/v1/tenants/",
        headers=superuser_token_headers,
        json={
            "name": "new-test-tenant",
            "description": "A new test tenant",
            "settings": {"feature_enabled": True}
        }
    )
    
    assert response.status_code == 200
    content = response.json()
    assert content["name"] == "new-test-tenant"
    assert content["description"] == "A new test tenant"
    assert content["settings"]["feature_enabled"] is True
    assert "bucket_name" in content
    assert "new-test-tenant" in content["bucket_name"]

def test_create_tenant_duplicate_name(client, test_tenant, superuser_token_headers):
    """Prueba para crear un tenant con nombre duplicado"""
    response = client.post(
        "/api/v1/tenants/",
        headers=superuser_token_headers,
        json={
            "name": test_tenant.name,  # Nombre existente
            "description": "Duplicate tenant name"
        }
    )
    
    assert response.status_code == 400
    assert "ya existe" in response.json()["detail"]

def test_get_tenant(client, test_tenant, superuser_token_headers):
    """Prueba para obtener un tenant específico (solo admin)"""
    response = client.get(
        f"/api/v1/tenants/{test_tenant.id}",
        headers=superuser_token_headers
    )
    
    assert response.status_code == 200
    content = response.json()
    assert content["id"] == str(test_tenant.id)
    assert content["name"] == test_tenant.name
    assert "users" in content  # Debería incluir usuarios

def test_update_tenant(client, test_tenant, superuser_token_headers):
    """Prueba para actualizar un tenant (solo admin)"""
    response = client.put(
        f"/api/v1/tenants/{test_tenant.id}",
        headers=superuser_token_headers,
        json={
            "description": "Updated test tenant description",
            "settings": {"new_setting": "value"}
        }
    )
    
    assert response.status_code == 200
    content = response.json()
    assert content["id"] == str(test_tenant.id)
    assert content["name"] == test_tenant.name
    assert content["description"] == "Updated test tenant description"
    assert content["settings"]["new_setting"] == "value"

def test_delete_tenant_with_users(client, test_tenant, superuser_token_headers):
    """Prueba para prevenir eliminación de tenant con usuarios"""
    response = client.delete(
        f"/api/v1/tenants/{test_tenant.id}",
        headers=superuser_token_headers
    )
    
    assert response.status_code == 400
    assert "usuarios asociados" in response.json()["detail"]

def test_delete_tenant(client, db, superuser_token_headers):
    """Prueba para eliminar un tenant sin usuarios (solo admin)"""
    # Crear tenant temporal sin usuarios
    from app.db.models import Tenant
    import uuid
    from datetime import datetime
    
    temp_tenant = Tenant(
        id=uuid.uuid4(),
        name="temp-tenant-for-deletion",
        description="Temporary tenant for deletion test",
        bucket_name="temp-bucket",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(temp_tenant)
    db.commit()
    db.refresh(temp_tenant)
    
    # Intentar eliminar
    response = client.delete(
        f"/api/v1/tenants/{temp_tenant.id}",
        headers=superuser_token_headers
    )
    
    assert response.status_code == 200
    assert "eliminado exitosamente" in response.json()["message"]
    
    # Verificar que fue eliminado
    response = client.get(
        f"/api/v1/tenants/{temp_tenant.id}",
        headers=superuser_token_headers
    )
    assert response.status_code == 404

def test_get_current_tenant(client, test_tenant, normal_user_token_headers):
    """Prueba para obtener información del tenant actual"""
    response = client.get(
        "/api/v1/tenants/current",
        headers=normal_user_token_headers
    )
    
    assert response.status_code == 200
    content = response.json()
    assert content["id"] == str(test_tenant.id)
    assert content["name"] == test_tenant.name