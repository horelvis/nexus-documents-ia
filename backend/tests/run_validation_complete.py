#!/usr/bin/env python3
"""
Script para ejecutar validación completa del sistema NexusDocs360
====================================================================

Este script ejecuta una suite completa de tests que valida:
- Integración con Clerk
- Creación y autenticación de usuarios
- Funcionamiento de servicios
- Integración entre sistemas
- Cleanup automático

Uso:
    python run_validation_complete.py

O desde el directorio de tests:
    python run_validation_complete.py
"""

import subprocess
import sys
import os
from datetime import datetime
import time

def print_header():
    """Imprimir header del script"""
    print("🚀 NexusDocs360 - Validación Completa del Sistema")
    print("=" * 60)
    print(f"⏰ Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

def check_system_status():
    """Verificar que el sistema esté funcionando"""
    print("🩺 Verificando estado del sistema...")

    services = [
        ("http://localhost:8000", "API Principal"),
        ("http://localhost:8001", "LangChain Service"),
        ("http://localhost:8002", "Langroid Service"),
        ("http://localhost:8003", "Storage Service"),
        ("http://localhost:8004", "Ollama Service"),
        ("http://localhost:8005", "Gotenberg Service")
    ]

    healthy_services = 0

    for url, name in services:
        try:
            import requests
            response = requests.get(f"{url}/health", timeout=3)
            if response.status_code == 200:
                print(f"✅ {name}: OK")
                healthy_services += 1
            else:
                print(f"⚠️  {name}: Status {response.status_code}")
        except:
            print(f"❌ {name}: No disponible")

    if healthy_services >= 4:  # Al menos API + 3 servicios
        print("✅ Sistema listo para validación\n")
        return True
    else:
        print("❌ Sistema no está completamente operativo\n")
        return False

def run_validation_tests():
    """Ejecutar los tests de validación"""
    print("🧪 Ejecutando tests de validación completa...")

    # Cambiar al directorio de tests
    test_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(test_dir)

    # Ejecutar pytest con configuración específica
    cmd = [
        sys.executable, "-m", "pytest",
        "test_validation_complete.py",
        "-v",
        "--tb=short",
        "--capture=no",
        "--disable-warnings",
        "--strict-markers"
    ]

    print(f"📋 Comando: {' '.join(cmd)}")
    print("-" * 60)

    start_time = time.time()
    result = subprocess.run(cmd)
    end_time = time.time()

    duration = end_time - start_time
    print("-" * 60)
    print(".2f"
    return result.returncode, duration

def print_summary(exit_code, duration, start_time):
    """Imprimir resumen de la validación"""
    print("\n" + "=" * 60)
    print("📊 RESUMEN DE VALIDACIÓN")
    print("=" * 60)

    if exit_code == 0:
        print("🎉 RESULTADO: VALIDACIÓN EXITOSA")
        print("✅ Todos los componentes funcionan correctamente")
        print("✅ Integración Clerk validada")
        print("✅ Usuarios creados y autenticados")
        print("✅ Servicios integrados correctamente")
        print("✅ Cleanup automático configurado")
    else:
        print("❌ RESULTADO: VALIDACIÓN FALLIDA")
        print("🔍 Revisar logs detallados arriba")
        print("💡 Posibles causas:")
        print("   - Servicios no disponibles")
        print("   - Problemas de conectividad")
        print("   - Configuración incorrecta")
        print("   - Base de datos no accesible")

    print(f"⏱️  Duración total: {duration:.2f} segundos")
    print(f"🏁 Finalizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def main():
    """Función principal"""
    print_header()

    # Verificar estado del sistema
    if not check_system_status():
        print("❌ Sistema no operativo. Abortando validación.")
        return 1

    # Ejecutar tests
    exit_code, duration = run_validation_tests()

    # Imprimir resumen
    print_summary(exit_code, duration, datetime.now())

    return exit_code

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)