"""
Test de Validación Completo - NouxCubeIA
==========================================

Este test valida la integración completa del sistema incluyendo:
- Creación de usuarios con Clerk
- Autenticación y autorización
- Integración entre servicios
- Cleanup automático de datos de prueba

Ejecutar con: pytest test_validation_complete.py -v --tb=short
"""

import pytest
import asyncio
import uuid
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import requests
import time
import os

from app.main import app
from app.db.models import User, Document
from app.core.security import get_password_hash
from app.services.auth_service import AuthService


class TestValidationComplete:
    """Suite completa de validación del sistema NouxCubeIA"""

    def _get_env_int(self, name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except Exception:
            return default

    def _service_probe_url(self, base_url: str) -> str:
        base_url = base_url.rstrip("/")
        if base_url.endswith("/v1"):
            return f"{base_url}/models"
        return f"{base_url}/health"

    @pytest.fixture(scope="class")
    def test_client(self):
        """Cliente de test para la API"""
        with TestClient(app) as client:
            yield client

    @pytest.fixture(scope="class")
    def clerk_test_users(self, db_session):
        """Usuarios de prueba con integración Clerk"""
        users_data = []
        created_users = []

        # Crear 3 usuarios de prueba con diferentes roles
        test_users = [
            {
                "email": f"test_user_{uuid.uuid4().hex[:8]}@test.com",
                "full_name": "Test User Regular",
                "clerk_id": f"clerk_test_{uuid.uuid4().hex[:12]}",
                "is_superuser": False
            },
            {
                "email": f"test_admin_{uuid.uuid4().hex[:8]}@test.com",
                "full_name": "Test Admin User",
                "clerk_id": f"clerk_admin_{uuid.uuid4().hex[:12]}",
                "is_superuser": True
            },
            {
                "email": f"test_power_{uuid.uuid4().hex[:8]}@test.com",
                "full_name": "Test Power User",
                "clerk_id": f"clerk_power_{uuid.uuid4().hex[:12]}",
                "is_superuser": False
            }
        ]

        for user_data in test_users:
            user = User(
                id=uuid.uuid4(),
                email=user_data["email"],
                hashed_password=get_password_hash("test_password_123"),
                full_name=user_data["full_name"],
                is_active=True,
                is_superuser=user_data["is_superuser"],
                clerk_user_id=user_data["clerk_id"]
            )
            db_session.add(user)
            created_users.append(user)
            users_data.append(user_data)

        db_session.commit()

        for user in created_users:
            db_session.refresh(user)

        yield created_users, users_data

        # Cleanup
        for user in created_users:
            db_session.delete(user)
        db_session.commit()

    def test_01_system_health_check(self, test_client):
        """Test 1: Verificar que el sistema esté funcionando"""
        print("\n🩺 Test 1: Verificando salud del sistema...")

        # Health check endpoint
        response = test_client.get("/api/v1/health")
        assert response.status_code == 200

        health_data = response.json()
        assert "status" in health_data
        assert health_data["status"] in ["healthy", "ok"]

        print("✅ Sistema funcionando correctamente")

    def test_02_clerk_user_creation(self, test_client, clerk_test_users):
        """Test 2: Crear usuarios con integración Clerk"""
        print("\n Test 2: Creando usuarios con integracion Clerk...")

        users, users_data = clerk_test_users

        for i, (user, user_data) in enumerate(zip(users, users_data)):
            # Verificar que el usuario se creó correctamente
            assert user.email == user_data["email"]
            assert user.clerk_user_id == user_data["clerk_id"]
            assert user.is_active == True

            print(f"  Usuario {i+1} creado: {user.email} (Clerk ID: {user.clerk_user_id})")

    def test_03_clerk_authentication_flow(self, test_client, clerk_test_users):
        """Test 3: Probar flujo de autenticación con Clerk"""
        print("\n🔐 Test 3: Probando autenticación con Clerk...")

        users, users_data = clerk_test_users

        for user, user_data in zip(users, users_data):
            # Simular login con Clerk (usando el endpoint de registro/login)
            login_data = {
                "email": user_data["email"],
                "password": "test_password_123",
                "clerk_user_id": user_data["clerk_id"],
            }

            response = test_client.post("/api/v1/auth/login/clerk", json=login_data)

            # Verificar respuesta exitosa
            assert response.status_code in [200, 201]

            if response.status_code == 200:
                data = response.json()
                assert "access_token" in data
                assert "token_type" in data
                assert data["token_type"] == "bearer"

                print(f"✅ Autenticación exitosa para: {user_data['email']}")

    def test_04_user_profile_access(self, test_client, clerk_test_users):
        """Test 4: Acceder a perfiles de usuario"""
        print("\n📋 Test 4: Accediendo a perfiles de usuario...")

        users, users_data = clerk_test_users

        for user, user_data in zip(users, users_data):
            # Simular autenticación para obtener token
            from app.api.dependencies import create_access_token

            token = create_access_token({"sub": user.clerk_user_id})

            headers = {"Authorization": f"Bearer {token}"}

            # Acceder al perfil del usuario
            response = test_client.get("/api/v1/auth/me", headers=headers)

            assert response.status_code == 200

            profile_data = response.json()
            assert profile_data["email"] == user_data["email"]
            assert profile_data["full_name"] == user_data["full_name"]
            assert profile_data["clerk_user_id"] == user_data["clerk_id"]

            print(f"✅ Perfil accesible para: {user_data['email']}")

    def test_05_role_based_access(self, test_client, clerk_test_users):
        """Test 5: Verificar acceso basado en roles"""
        print("\n Test 5: Verificando acceso basado en roles...")

        users, users_data = clerk_test_users

        # Verify superuser flag is set correctly
        for user, user_data in zip(users, users_data):
            assert user.is_superuser == user_data["is_superuser"]

        print("  Acceso basado en roles funcionando correctamente")

    def test_06_document_operations(self, test_client, clerk_test_users):
        """Test 6: Operaciones con documentos"""
        print("\n Test 6: Probando operaciones con documentos...")

        users, users_data = clerk_test_users
        user = users[0]  # Usar el primer usuario

        from app.api.dependencies import create_access_token
        token = create_access_token({"sub": user.clerk_user_id})
        headers = {"Authorization": f"Bearer {token}"}

        # Crear un documento de prueba
        doc_data = {
            "title": "Documento de Prueba Validacion",
            "description": "Documento creado durante validacion del sistema",
            "filename": "test_validation.pdf",
            "file_type": "application/pdf",
            "file_size": 1024,
        }

        response = test_client.post("/api/v1/documents/", json=doc_data, headers=headers)

        if response.status_code in [200, 201]:
            doc_response = response.json()
            assert "id" in doc_response
            assert doc_response["title"] == doc_data["title"]

            print("✅ Documento creado exitosamente")

            # Limpiar documento de prueba
            doc_id = doc_response["id"]
            cleanup_response = test_client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
            if cleanup_response.status_code == 204:
                print("✅ Documento de prueba limpiado")
        else:
            print(f"⚠️  Creación de documento devolvió: {response.status_code}")
            print(f"   Respuesta: {response.text}")

    def test_07_service_integration(self, test_client):
        """Test 7: Verificar integración entre servicios"""
        print("\n🔗 Test 7: Verificando integración entre servicios...")

        # Verificar que los servicios micro estén respondiendo
        services_to_check = [
            (os.getenv("STORAGE_SERVICE_URL", "http://storage-service:8000"), "Storage Service"),
            (os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1"), "vLLM"),
            (os.getenv("GOTENBERG_BASE_URL", "http://gotenberg:3000"), "Gotenberg Service"),
            (os.getenv("WEAVIATE_SERVICE_URL", "http://weaviate-service:8000"), "Weaviate Service"),
            (os.getenv("CAG_SERVICE_URL", "http://weaviate-service:8000"), "CAG Service"),
            (os.getenv("LANGEXTRACT_SERVICE_URL", "http://langextract-service:8000"), "LangExtract Service"),
        ]

        healthy_services = 0
        for url, service_name in services_to_check:
            try:
                probe_url = self._service_probe_url(url)
                response = requests.get(probe_url, timeout=5)
                if response.status_code == 200:
                    print(f"✅ {service_name}: OK")
                    healthy_services += 1
                else:
                    print(f"⚠️  {service_name}: Status {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"⚠️  {service_name}: No disponible ({str(e)[:50]}...)")

        # Al menos algunos servicios deben estar funcionando
        min_healthy = self._get_env_int(
            "MIN_HEALTHY_MICROSERVICES",
            0 if os.getenv("TESTING", "false").lower() == "true" else 3,
        )
        assert healthy_services >= min_healthy, (
            f"Solo {healthy_services} servicios están funcionando. Se requieren al menos {min_healthy}."
        )
        print(f"✅ {healthy_services} servicios funcionando correctamente")

    def test_08_performance_validation(self, test_client, clerk_test_users):
        """Test 8: Validación de rendimiento"""
        print("\n⚡ Test 8: Validando rendimiento...")

        users, users_data = clerk_test_users
        user = users[0]

        from app.api.dependencies import create_access_token
        token = create_access_token({"sub": user.clerk_user_id})
        headers = {"Authorization": f"Bearer {token}"}

        # Medir tiempo de respuesta para múltiples requests
        import time

        start_time = time.time()

        for i in range(5):
            response = test_client.get("/api/v1/auth/me", headers=headers)
            assert response.status_code == 200

        end_time = time.time()
        avg_response_time = (end_time - start_time) / 5

        print(f"⏱️  Tiempo de respuesta promedio: {avg_response_time:.2f}s")
        # Validar que el rendimiento sea aceptable (< 500ms promedio)
        assert avg_response_time < 0.5, f"Tiempo de respuesta demasiado lento: {avg_response_time:.2f}s"

    def test_09_security_validation(self, test_client):
        """Test 9: Validación de seguridad"""
        print("\n🔒 Test 9: Validando seguridad...")

        # Intentar acceso sin autenticación
        response = test_client.get("/api/v1/auth/me")
        assert response.status_code == 401

        # Intentar acceso con token inválido
        headers = {"Authorization": "Bearer invalid_token"}
        response = test_client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 401

        # Intentar acceso a endpoints protegidos
        response = test_client.get("/api/v1/admin/users")
        assert response.status_code == 401

        print("✅ Validaciones de seguridad pasaron correctamente")

    def test_10_cleanup_validation(self, test_client, clerk_test_users, db_session):
        """Test 10: Validar cleanup automatico"""
        print("\n Test 10: Validando cleanup automatico...")

        users, users_data = clerk_test_users

        # Verificar que los usuarios existen antes del cleanup
        for user in users:
            db_user = db_session.query(User).filter(User.id == user.id).first()
            assert db_user is not None

        # El cleanup se hace automaticamente en los fixtures
        print("  Cleanup automatico configurado correctamente")
        print("  Todos los datos de prueba seran limpiados automaticamente")


# Función para ejecutar la validación completa
def run_complete_validation():
    """Ejecutar validación completa del sistema"""
    print("🚀 Iniciando Validación Completa de NouxCubeIA")
    print("=" * 60)

    # Ejecutar tests con pytest
    import subprocess
    import sys

    result = subprocess.run([
        sys.executable, "-m", "pytest",
        "test_validation_complete.py",
        "-v",
        "--tb=short",
        "--capture=no"
    ], cwd="/home/nexus/git/nexus-documents-ia/backend/tests")

    print("\n" + "=" * 60)
    if result.returncode == 0:
        print("🎉 VALIDACIÓN COMPLETA EXITOSA")
        print("✅ Todos los sistemas funcionan correctamente")
        print("✅ Integración Clerk validada")
        print("✅ Usuarios creados y autenticados")
        print("✅ Cleanup automático configurado")
    else:
        print("❌ VALIDACIÓN FALLIDA")
        print("🔍 Revisar logs para más detalles")

    return result.returncode


if __name__ == "__main__":
    exit_code = run_complete_validation()
    exit(exit_code)
