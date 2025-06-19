#!/usr/bin/env python3
"""
Script para generar API keys seguras para desarrollo y producción
"""
import secrets
import string
import base64
import uuid
import hashlib
from datetime import datetime


def generate_simple_key(length=32):
    """Genera una API key simple alfanumérica"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_prefixed_key(prefix="nxs", length=32):
    """Genera una API key con prefijo (estilo Stripe)"""
    key = generate_simple_key(length)
    return f"{prefix}_{key}"


def generate_uuid_based_key():
    """Genera una API key basada en UUID"""
    return f"nxs_{uuid.uuid4().hex}"


def generate_base64_key():
    """Genera una API key codificada en base64"""
    random_bytes = secrets.token_bytes(32)
    return base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')


def generate_hashed_key():
    """Genera un par de API key y su hash (para almacenar el hash en DB)"""
    # Generar la key raw
    raw_key = generate_prefixed_key("nxs_sk", 48)
    
    # Generar el hash para almacenar en la base de datos
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    
    return {
        "api_key": raw_key,
        "key_hash": key_hash,
        "key_hint": f"{raw_key[:8]}...{raw_key[-4:]}",
        "created_at": datetime.utcnow().isoformat()
    }


def generate_development_keys():
    """Genera un conjunto de keys para desarrollo"""
    return {
        "simple": generate_simple_key(),
        "prefixed": generate_prefixed_key("nxs_dev"),
        "uuid_based": generate_uuid_based_key(),
        "base64": generate_base64_key(),
        "secure_pair": generate_hashed_key()
    }


def main():
    print("🔐 Generador de API Keys para Nexus Document\n")
    
    print("1. API Key Simple (32 caracteres):")
    print(f"   {generate_simple_key()}\n")
    
    print("2. API Key con Prefijo (estilo Stripe):")
    print(f"   {generate_prefixed_key('nxs_dev')}\n")
    
    print("3. API Key basada en UUID:")
    print(f"   {generate_uuid_based_key()}\n")
    
    print("4. API Key en Base64:")
    print(f"   {generate_base64_key()}\n")
    
    print("5. Par Seguro (Key + Hash para DB):")
    secure = generate_hashed_key()
    print(f"   API Key: {secure['api_key']}")
    print(f"   Hash DB: {secure['key_hash']}")
    print(f"   Hint:    {secure['key_hint']}\n")
    
    print("📋 Recomendaciones:")
    print("   - Para desarrollo: Usa cualquiera de las opciones 1-4")
    print("   - Para producción: Usa la opción 5 y guarda solo el hash en la DB")
    print("   - Longitud mínima recomendada: 32 caracteres")
    print("   - Rota las keys regularmente")
    print("\n🔧 Para usar en .env:")
    dev_key = generate_prefixed_key("nxs_dev", 40)
    print(f"   MICROSERVICES_API_KEY={dev_key}")


if __name__ == "__main__":
    main()