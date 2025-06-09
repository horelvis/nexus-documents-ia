# Sistema de Control de Suscripciones - Arquitectura

## 🎯 Filosofía de Diseño: Minimizar Dependencias

En lugar de duplicar datos entre servicios externos (Clerk, Stripe) y nuestra base de datos, optamos por una arquitectura que obtiene datos en tiempo real de las fuentes oficiales:

- **Clerk** → Datos de perfil personal y autenticación
- **Stripe** → Estado de suscripciones y pagos  
- **Nuestra DB** → Solo lógica de negocio y control de acceso

## 🏗️ Componentes del Sistema

### Backend (Python/FastAPI)

#### 1. **SubscriptionService** (`app/services/subscription_service.py`)
- ✅ **Verificación en tiempo real con Stripe** - Sincroniza estado automáticamente
- ✅ **Permisos granulares** - Por funcionalidad (upload, chat, agents, etc.)
- ✅ **Estados de suscripción** - Activo, cancelado, expirado, impago
- ✅ **Límites personalizables** - Documentos, uploads, tamaño de archivos

#### 2. **Dependencias FastAPI** (`app/api/dependencies.py`)
- `require_subscription_permission(permission)` - Middleware genérico
- `require_document_upload_permission()` - Específico para uploads
- `require_active_subscription()` - Verifica suscripción no limitada

#### 3. **Endpoints Protegidos**
```python
# Ejemplo de uso
@router.post("/documents")
async def create_document(
    current_user: User = Depends(require_document_upload_permission),
    # ... otros parámetros
):
    # Función ya verificada automáticamente
```

### Frontend (React/Next.js)

#### 1. **Hook `useSubscription`** (`hooks/use-subscription.ts`)
```typescript
const { 
  canUploadDocuments, 
  canUseChat, 
  isLimited, 
  maxDocuments 
} = useSubscription()
```

#### 2. **Componente `SubscriptionStatusBanner`** (`components/common/subscription-status-banner.tsx`)
- Muestra estado actual de suscripción
- Botones de reactivación automáticos
- Modo compacto y completo

## 🔄 Flujos de Control

### Usuario con Suscripción Activa
```
Usuario → Acción → ✅ Permitida
```

### Usuario con Suscripción Expirada  
```
Usuario → Acción → ❌ Error 402 → UI: "Reactiva tu suscripción"
```

### Usuario en Plan Gratuito con Límites
```
Usuario → Upload (10/10) → ❌ Error 403 → UI: "Actualiza tu plan"
```

## 🎛️ Configuración de Permisos

### Plan Gratuito
```python
{
    "max_documents": 10,
    "max_monthly_uploads": 5,
    "can_upload_documents": True,
    "can_use_chat": True,
    "can_use_agents": False,
    "max_file_size_mb": 10,
}
```

### Plan Pro
```python
{
    "max_documents": 1000,
    "max_monthly_uploads": 100,
    "can_upload_documents": True,
    "can_use_chat": True,
    "can_use_agents": True,
    "max_file_size_mb": 100,
}
```

### Modo Limitado (Suscripción Expirada)
```python
{
    "max_documents": 0,  # No puede subir más
    "can_upload_documents": False,
    "can_view_documents": True,  # Solo leer existentes
    "can_search_documents": True,  # Solo buscar existentes
    "can_use_chat": False,
    "can_use_agents": False,
}
```

## 🚨 Códigos de Error HTTP

- **402 Payment Required** - Suscripción expirada, puede reactivar
- **403 Forbidden** - Límite de plan alcanzado, debe actualizar
- **401 Unauthorized** - No autenticado

## 🔧 Endpoints de Desarrollo

```python
# Resetear onboarding (desarrollo)
POST /api/v1/auth/reset-onboarding

# Eliminar usuario completamente (desarrollo)  
DELETE /api/v1/auth/dev/delete-user

# Ver estado de suscripción
GET /api/v1/stripe/subscription
```

## 📊 Ventajas de esta Arquitectura

### ✅ **Ventajas**
- **Consistencia de datos** - Siempre sincronizado con Stripe
- **Menos duplicación** - No mantenemos copias de datos de Clerk/Stripe
- **Escalabilidad** - Verificaciones en tiempo real
- **Flexibilidad** - Fácil cambiar permisos sin migrar datos

### ⚠️ **Consideraciones**
- **Latencia** - Llamadas adicionales a Stripe (se mitiga con cache local)
- **Dependencia externa** - Requiere conectividad con Stripe

## 🔮 Siguientes Pasos

1. **Webhooks de Stripe** - Para updates automáticos de estado
2. **Cache Redis** - Para reducir llamadas a Stripe API
3. **Métricas de uso** - Para límites mensuales dinámicos
4. **Planes personalizados** - Para Enterprise con límites específicos

## 🧪 Testing

```bash
# Listar usuarios
python scripts/clean_dev_data.py --list

# Resetear onboarding específico  
python scripts/clean_dev_data.py --reset-onboarding usuario@ejemplo.com

# Eliminar usuario para testing
python scripts/clean_dev_data.py --delete-user usuario@ejemplo.com
```

---

**Principio clave**: Mantener nuestra DB como "single source of truth" solo para lógica de negocio, mientras obtenemos datos de perfil y facturación directamente de sus fuentes oficiales (Clerk y Stripe).