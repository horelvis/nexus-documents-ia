#!/usr/bin/env python3
"""
Test directo del marcado de documentos como visualizados
"""
import requests
import time

print("🔍 Probando marcado de documentos como visualizados...")

# Primero voy a probar el endpoint de documento-insights directamente
base_url = "http://localhost:8000"

# Test 1: Intentar marcar un documento como visto usando el endpoint directo
print("\n📝 Probando endpoint directo de document-insights...")

# Crear data de prueba
test_data = {
    "document_id": "549d6642-fac9-4fb3-acb4-5e270192b2c3",  # ID del documento de la UI
    "view_duration_seconds": 10,
    "scroll_percentage": 50.0
}

try:
    response = requests.post(
        f"{base_url}/api/v1/document-insights/mark-viewed",
        params=test_data,
        headers={"Authorization": "Bearer fake_token_for_testing"}
    )
    print(f"✅ Response status: {response.status_code}")
    print(f"📄 Response: {response.text[:200]}")
except Exception as e:
    print(f"❌ Error: {e}")

# Test 2: Obtener documentos recientes
print("\n📋 Probando obtener documentos recientes...")
try:
    response = requests.get(
        f"{base_url}/api/v1/document-insights/recently-viewed?limit=5&user_specific=true",
        headers={"Authorization": "Bearer fake_token_for_testing"}
    )
    print(f"✅ Response status: {response.status_code}")
    print(f"📄 Response: {response.text[:200]}")
except Exception as e:
    print(f"❌ Error: {e}")

print("\n🎉 Prueba completada")