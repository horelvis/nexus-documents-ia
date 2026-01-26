#!/usr/bin/env python3
"""
Validación Simple del Sistema NouxCubeIA
==========================================

Script que valida los servicios disponibles sin depender de Docker.
"""

import socket
import requests
import time
from datetime import datetime
import sys

def check_service(host, port, service_name, timeout=2):
    """Verificar si un servicio está disponible"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False

def check_http_service(url, service_name, timeout=5):
    """Verificar si un servicio HTTP está disponible"""
    try:
        response = requests.get(url, timeout=timeout)
        return response.status_code == 200
    except:
        return False

def main():
    print("🚀 NouxCubeIA - Validación de Servicios")
    print("=" * 60)
    print(f"⏰ Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    services_to_check = [
        # Base de datos y cache
        ("PostgreSQL", "localhost", 5432, "tcp"),
        ("Redis", "localhost", 6379, "tcp"),

        # Servicios de búsqueda e IA
        ("Weaviate", "localhost", 8080, "tcp"),
        ("Elasticsearch", "localhost", 9200, "tcp"),

        # Microservicios
        ("Storage Service", "localhost", 8003, "http", "http://localhost:8003/health"),
        ("Weaviate Service", "localhost", 8007, "http", "http://localhost:8007/health"),
        ("CAG API (via Weaviate)", "localhost", 8007, "http", "http://localhost:8007/api/v1/cag/health"),
        ("LangExtract Service", "localhost", 8009, "http", "http://localhost:8009/health"),
        ("Signature Service", "localhost", 8006, "http", "http://localhost:8006/health"),

        # Servicios externos
        ("Gotenberg", "localhost", 3333, "http", "http://localhost:3333/health"),
        ("Ollama", "localhost", 11434, "tcp"),
        ("TemporalIO", "localhost", 7233, "tcp"),
        ("Kibana", "localhost", 5601, "tcp"),
    ]

    available_services = 0
    total_services = len(services_to_check)

    print("🔍 Verificando servicios disponibles...")
    print("-" * 60)

    for service_info in services_to_check:
        service_name = service_info[0]
        host = service_info[1]
        port = service_info[2]
        service_type = service_info[3]

        if service_type == "tcp":
            is_available = check_service(host, port, service_name)
            if is_available:
                print(f"✅ {service_name}: Puerto {port} abierto")
                available_services += 1
            else:
                print(f"❌ {service_name}: Puerto {port} cerrado")

        elif service_type == "http":
            url = service_info[4]
            is_available = check_http_service(url, service_name)
            if is_available:
                print(f"✅ {service_name}: OK")
                available_services += 1
            else:
                print(f"❌ {service_name}: No disponible")

    print("-" * 60)
    print(f"📊 Resumen: {available_services}/{total_services} servicios disponibles")

    # Validar requisitos mínimos
    critical_services = ["PostgreSQL", "Redis", "Weaviate", "Storage Service"]
    critical_available = sum(1 for s in services_to_check
                           if s[0] in critical_services
                           and ((s[3] == "tcp" and check_service(s[1], s[2], s[0])) or
                                (s[3] == "http" and check_http_service(s[4], s[0]))))

    print(f"🔧 Servicios críticos: {critical_available}/{len(critical_services)} disponibles")

    print("\n" + "=" * 60)

    if critical_available >= 3:
        print("🎉 VALIDACIÓN EXITOSA")
        print("✅ Servicios críticos funcionando")
        print("✅ Sistema listo para desarrollo")
        print("\n💡 Próximos pasos:")
        print("   1. Ejecutar migraciones: cd backend && python scripts/alembic_safe_migrate.py")
        print("   2. Iniciar API: cd backend/docker && ./start-dev.sh")
        print("   3. Verificar frontend: cd frontend && npm run dev")
        return 0
    else:
        print("❌ VALIDACIÓN FALLIDA")
        print("🔍 Servicios críticos no disponibles")
        print("\n💡 Solución:")
        print("   1. Verificar Docker: docker compose ps")
        print("   2. Reiniciar servicios: cd backend/docker && ./start-dev.sh")
        print("   3. Verificar logs: docker compose logs")
        return 1

if __name__ == "__main__":
    exit_code = main()
    print(f"\n🏁 Finalizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    exit(exit_code)
