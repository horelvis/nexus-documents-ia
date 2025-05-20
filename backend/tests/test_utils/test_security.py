import pytest
import jwt
from datetime import datetime, timedelta

from app.core.security import create_access_token, verify_password, get_password_hash


def test_password_hashing():
    """Prueba de hash y verificación de contraseñas"""
    plain_password = "testpassword123"
    
    # Generar hash
    hashed_password = get_password_hash(plain_password)
    
    # Verificar que no es la contraseña original
    assert hashed_password != plain_password
    
    # Verificar que es correcto
    assert verify_password(plain_password, hashed_password) is True
    
    # Verificar que rechaza contraseña incorrecta
    assert verify_password("wrongpassword", hashed_password) is False

def test_create_access_token():
    """Prueba de creación de token JWT"""
    # Crear token
    user_id = "test-user-id"
    tenant_id = "test-tenant-id"
    token = create_access_token(subject=user_id, tenant_id=tenant_id)
    
    # Verificar que es un string
    assert isinstance(token, str)
    
    # Decodificar token
    from app.core.config import settings
    decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    
    # Verificar contenido
    assert decoded["sub"] == user_id
    assert decoded["tid"] == tenant_id
    assert "exp" in decoded
    
    # Verificar que no está expirado
    assert datetime.fromtimestamp(decoded["exp"]) > datetime.utcnow()

def test_create_access_token_with_expiry():
    """Prueba de creación de token JWT con expiración personalizada"""
    # Crear token con expiración de 5 minutos
    expires_delta = timedelta(minutes=5)
    token = create_access_token(
        subject="test-user-id", 
        tenant_id="test-tenant-id",
        expires_delta=expires_delta
    )
    
    # Decodificar token
    from app.core.config import settings
    decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    
    # Verificar fecha de expiración
    expiry = datetime.fromtimestamp(decoded["exp"])
    
    # Debe ser cercano a la hora actual + 5 minutos (con margen de 5 segundos)
    expected_expiry = datetime.utcnow() + expires_delta
    assert abs((expiry - expected_expiry).total_seconds()) < 5