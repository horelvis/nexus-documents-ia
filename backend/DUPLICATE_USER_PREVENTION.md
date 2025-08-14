# Prevención de Usuarios Duplicados

## Problema Identificado

El sistema tenía un potencial problema donde se podían crear usuarios duplicados con el mismo email sin verificación adecuada, específicamente en el proceso de sincronización con Clerk.

## Solución Implementada

### 1. Verificación a Nivel de Base de Datos

**Modelo User** (`app/db/models.py`):
```python
email = Column(String(255), unique=True, index=True, nullable=False)
clerk_user_id = Column(String(255), nullable=True, unique=True, index=True)
```

- ✅ Restricción única en email
- ✅ Restricción única en clerk_user_id
- ✅ Índices para rendimiento

### 2. Verificación a Nivel de Aplicación

**AsyncAuthService** (`app/services/async_auth_service.py`):

#### Función `create_user`:
```python
# Verificar que el email no esté ya registrado
result = await db.execute(
    select(User).where(User.email == email)
)
existing_user = result.scalar_one_or_none()

if existing_user:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Email already registered"
    )
```

#### Función `sync_user_from_clerk` (Mejorada):
```python
if user_by_email:
    # Usuario existe por email pero sin clerk_user_id
    if user_by_email.clerk_user_id:
        # Ya tiene un clerk_user_id diferente - posible duplicado
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email {email} is already registered with a different account"
        )
```

### 3. Manejo de Errores de Integridad

**Captura de IntegrityError**:
```python
try:
    await db.commit()
    return new_user
except IntegrityError as e:
    await db.rollback()
    if "unique constraint" in str(e).lower() and "email" in str(e).lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email {email} is already registered"
        )
```

## Scripts de Verificación y Limpieza

### Script de Verificación
```bash
# Ejecutar dentro del contenedor de la API
docker exec docker-api-1 python scripts/check_duplicate_users.py
```

**Funcionalidades**:
- ✅ Detecta emails duplicados
- ✅ Detecta clerk_user_id duplicados  
- ✅ Muestra estadísticas de usuarios
- ✅ Genera reporte detallado

### Script de Limpieza
```bash
# Modo DRY RUN (solo análisis)
docker exec docker-api-1 python scripts/cleanup_duplicate_users.py

# Modo ejecución (cambios reales)
docker exec docker-api-1 python scripts/cleanup_duplicate_users.py --execute
```

**Funcionalidades**:
- ✅ Identifica usuario a mantener por criterios de puntuación
- ✅ Transfiere datos importantes (documentos, información de perfil)
- ✅ Elimina usuarios duplicados de forma segura
- ✅ Modo DRY RUN para pruebas seguras

## Criterios de Priorización de Usuarios

Cuando se encuentran duplicados, el sistema mantiene el usuario con mayor puntuación:

1. **+10 puntos**: Tiene Clerk ID
2. **+5 puntos**: Tiene Stripe ID  
3. **+3 puntos**: Onboarding completado
4. **+2 puntos**: Usuario activo
5. **+1 punto**: Es superusuario
6. **Bonus**: Antigüedad (días/10)

## Verificación de Estado Actual

```bash
# Estado actual del sistema (2025-01-14)
docker exec docker-api-1 python scripts/check_duplicate_users.py
```

**Resultado**:
- ✅ Sin emails duplicados
- ✅ Sin Clerk IDs duplicados  
- 📊 1 usuario activo con integridad completa

## Endpoints Afectados

### `/auth/register` 
- ✅ Verifica email duplicado antes de crear
- ✅ Maneja IntegrityError de base de datos

### `/auth/sync-user`
- ✅ Verifica email duplicado con diferentes clerk_user_id
- ✅ Vincula usuario existente si no tiene clerk_user_id
- ✅ Maneja IntegrityError de base de datos

## Recomendaciones

1. **Ejecutar verificación periódica**:
   ```bash
   docker exec docker-api-1 python scripts/check_duplicate_users.py
   ```

2. **Monitorear logs de IntegrityError** para detectar intentos de duplicación

3. **Mantener restricciones únicas** en migraciones de base de datos

4. **Ejecutar script de limpieza** si se detectan duplicados en el futuro

## Testing

Para probar la prevención de duplicados:

```python
# Ejemplo de test
async def test_prevent_duplicate_email():
    # Crear primer usuario
    user1 = await AsyncAuthService.create_user(
        db=db,
        email="test@example.com", 
        password="password123",
        tenant_id=tenant_id
    )
    
    # Intentar crear segundo usuario con mismo email
    with pytest.raises(HTTPException) as exc_info:
        user2 = await AsyncAuthService.create_user(
            db=db,
            email="test@example.com",  # Mismo email
            password="password456",
            tenant_id=tenant_id
        )
    
    assert exc_info.value.status_code == 400
    assert "already registered" in str(exc_info.value.detail)
```

## Migraciones Futuras

Al crear nuevas migraciones, asegurar que se mantengan las restricciones únicas:

```python
def upgrade():
    # Mantener restricciones existentes
    op.create_unique_constraint('uq_users_email', 'users', ['email'])
    op.create_unique_constraint('uq_users_clerk_user_id', 'users', ['clerk_user_id'])
```

---

**Última actualización**: 2025-01-14  
**Estado**: ✅ Implementado y verificado  
**Mantenimiento**: Scripts automáticos disponibles