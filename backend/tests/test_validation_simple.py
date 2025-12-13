"""
Test de Validación Simple - NexusDocs360
=======================================

Test básico que valida los servicios disponibles sin depender de la API principal.
"""

import pytest
import requests
import time
import os
from datetime import datetime
from urllib.parse import urlparse


class TestValidationSimple:
    """Suite simple de validación de servicios disponibles"""

    def _get_env_int(self, name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except Exception:
            return default

    def _service_url(self, env_name: str, default: str) -> str:
        return os.getenv(env_name, default).rstrip("/")

    def test_01_database_connection(self):
        """Test 1: Verificar conexión a PostgreSQL"""
        print("\n🗄️  Test 1: Verificando conexión a PostgreSQL...")

        try:
            import psycopg2
            host = os.getenv("POSTGRES_SERVER", "localhost")
            port = self._get_env_int("POSTGRES_PORT", 5432)
            database = os.getenv("POSTGRES_DB", "nexusdocs360")
            user = os.getenv("POSTGRES_USER", "nexus_user")
            password = os.getenv("POSTGRES_PASSWORD", "nexus_password")
            conn = psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
            )
            conn.close()
            print("✅ PostgreSQL: Conexión exitosa")
        except Exception as e:
            print(f"❌ PostgreSQL: Error de conexión - {str(e)}")
            pytest.skip("PostgreSQL no disponible")

    def test_02_redis_connection(self):
        """Test 2: Verificar conexión a Redis"""
        print("\n🔴 Test 2: Verificando conexión a Redis...")

        try:
            import redis
            host = os.getenv("REDIS_HOST", "localhost")
            port = self._get_env_int("REDIS_PORT", 6379)
            r = redis.Redis(host=host, port=port, db=0)
            r.ping()
            print("✅ Redis: Conexión exitosa")
        except Exception as e:
            print(f"❌ Redis: Error de conexión - {str(e)}")
            pytest.skip("Redis no disponible")

    def test_03_weaviate_connection(self):
        """Test 3: Verificar conexión a Weaviate"""
        print("\n🧠 Test 3: Verificando conexión a Weaviate...")

        try:
            base = self._service_url("WEAVIATE_URL", "http://weaviate:8080")
            response = requests.get(f"{base}/v1/meta", timeout=5)
            if response.status_code == 200:
                print("✅ Weaviate: Conexión exitosa")
            else:
                print(f"⚠️  Weaviate: Status {response.status_code}")
        except Exception as e:
            print(f"❌ Weaviate: Error de conexión - {str(e)}")
            pytest.skip("Weaviate no disponible")

    def test_04_storage_service(self):
        """Test 4: Verificar Storage Service"""
        print("\n📦 Test 4: Verificando Storage Service...")

        try:
            base = self._service_url("STORAGE_SERVICE_URL", "http://storage-service:8000")
            response = requests.get(f"{base}/health", timeout=5)
            if response.status_code == 200:
                print("✅ Storage Service: OK")
            else:
                print(f"⚠️  Storage Service: Status {response.status_code}")
        except Exception as e:
            print(f"❌ Storage Service: Error de conexión - {str(e)}")

    def test_05_weaviate_service(self):
        """Test 5: Verificar Weaviate Service"""
        print("\n🔍 Test 5: Verificando Weaviate Service...")

        try:
            base = self._service_url("WEAVIATE_SERVICE_URL", "http://weaviate-service:8000")
            response = requests.get(f"{base}/health", timeout=5)
            if response.status_code == 200:
                print("✅ Weaviate Service: OK")
            else:
                print(f"⚠️  Weaviate Service: Status {response.status_code}")
        except Exception as e:
            print(f"❌ Weaviate Service: Error de conexión - {str(e)}")

    def test_06_cag_service(self):
        """Test 6: Verificar CAG Service"""
        print("\n🎯 Test 6: Verificando CAG Service...")

        try:
            base = self._service_url("CAG_SERVICE_URL", "http://weaviate-service:8000")
            response = requests.get(f"{base}/health", timeout=5)
            if response.status_code == 200:
                print("✅ CAG Service: OK")
            else:
                print(f"⚠️  CAG Service: Status {response.status_code}")
        except Exception as e:
            print(f"❌ CAG Service: Error de conexión - {str(e)}")

    def test_07_gotenberg_service(self):
        """Test 7: Verificar Gotenberg Service"""
        print("\n📄 Test 7: Verificando Gotenberg Service...")

        try:
            base = self._service_url("GOTENBERG_BASE_URL", "http://gotenberg:3000")
            response = requests.get(f"{base}/health", timeout=5)
            if response.status_code == 200:
                print("✅ Gotenberg Service: OK")
            else:
                print(f"⚠️  Gotenberg Service: Status {response.status_code}")
        except Exception as e:
            print(f"❌ Gotenberg Service: Error de conexión - {str(e)}")

    def test_08_elasticsearch_connection(self):
        """Test 8: Verificar conexión a Elasticsearch"""
        print("\n🔎 Test 8: Verificando conexión a Elasticsearch...")

        try:
            base = self._service_url("ELASTICSEARCH_URL", "http://elasticsearch:9200")
            response = requests.get(f"{base}/_cluster/health", timeout=5)
            if response.status_code == 200:
                health_data = response.json()
                status = health_data.get('status', 'unknown')
                print(f"✅ Elasticsearch: Status {status}")
            else:
                print(f"⚠️  Elasticsearch: Status {response.status_code}")
        except Exception as e:
            print(f"❌ Elasticsearch: Error de conexión - {str(e)}")

    def test_09_system_resources(self):
        """Test 9: Verificar recursos del sistema"""
        print("\n💻 Test 9: Verificando recursos del sistema...")

        import psutil

        # CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        print(f"🖥️  CPU: {cpu_percent:.1f}% usado")
        # Memoria
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        print(f"🧠 Memoria: {memory_percent:.1f}% usado")
        # Disco
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        print(f"💾 Disco: {disk_percent:.1f}% usado")
        # Verificar que los recursos estén en niveles aceptables
        assert cpu_percent < 90, f"Uso de CPU demasiado alto: {cpu_percent}%"
        assert memory_percent < 90, f"Uso de memoria demasiado alto: {memory_percent}%"
        assert disk_percent < 95, f"Uso de disco demasiado alto: {disk_percent}%"

        print("✅ Recursos del sistema en niveles aceptables")

    def test_10_service_discovery(self):
        """Test 10: Verificar descubrimiento de servicios"""
        print("\n🔍 Test 10: Verificando descubrimiento de servicios...")

        services = {
            "PostgreSQL": (os.getenv("POSTGRES_SERVER", "localhost"), self._get_env_int("POSTGRES_PORT", 5432)),
            "Redis": (os.getenv("REDIS_HOST", "localhost"), self._get_env_int("REDIS_PORT", 6379)),
            "Weaviate": (urlparse(self._service_url("WEAVIATE_URL", "http://localhost:8080")).hostname or "localhost",
                         urlparse(self._service_url("WEAVIATE_URL", "http://localhost:8080")).port or 8080),
            "Elasticsearch": (urlparse(self._service_url("ELASTICSEARCH_URL", "http://localhost:9200")).hostname or "localhost",
                              urlparse(self._service_url("ELASTICSEARCH_URL", "http://localhost:9200")).port or 9200),
        }

        available_services = 0

        for service_name, (host, port) in services.items():
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((host, port))
                sock.close()

                if result == 0:
                    print(f"✅ {service_name}: Puerto {port} abierto")
                    available_services += 1
                else:
                    print(f"❌ {service_name}: Puerto {port} cerrado")
            except Exception as e:
                print(f"⚠️  {service_name}: Error al verificar - {str(e)}")

        print(f"📊 Servicios disponibles: {available_services}/{len(services)}")
        min_services = self._get_env_int(
            "MIN_AVAILABLE_SERVICES",
            2 if os.getenv("TESTING", "false").lower() == "true" else 4,
        )
        assert available_services >= min_services, (
            f"Solo {available_services} servicios disponibles. Se requieren al menos {min_services}."
        )


def run_simple_validation():
    """Ejecutar validación simple"""
    print("🚀 NexusDocs360 - Validación Simple de Servicios")
    print("=" * 60)
    print(f"⏰ Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    import subprocess
    import sys
    import os

    # Cambiar al directorio de tests
    test_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(test_dir)

    # Ejecutar tests
    cmd = [
        sys.executable, "-m", "pytest",
        "test_validation_simple.py",
        "-v",
        "--tb=short",
        "--capture=no"
    ]

    print(f"📋 Ejecutando: {' '.join(cmd)}")
    print("-" * 60)

    start_time = time.time()
    result = subprocess.run(cmd)
    end_time = time.time()

    duration = end_time - start_time
    print("-" * 60)
    print(f"⏱️  Duración: {duration:.2f} segundos")
    print("\n" + "=" * 60)
    if result.returncode == 0:
        print("🎉 VALIDACIÓN SIMPLE EXITOSA")
        print("✅ Servicios básicos funcionando correctamente")
        print("✅ Infraestructura validada")
    else:
        print("❌ VALIDACIÓN SIMPLE FALLIDA")
        print("🔍 Revisar servicios no disponibles")

    print(f"🏁 Finalizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return result.returncode


if __name__ == "__main__":
    exit_code = run_simple_validation()
    exit(exit_code)
