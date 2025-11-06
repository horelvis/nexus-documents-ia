import pytest

from app.core.security import verify_password, get_password_hash


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