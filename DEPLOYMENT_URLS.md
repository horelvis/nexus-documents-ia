# 🌐 URLs de Despliegue - Nexus Documents IA

## 🔗 Ambientes Disponibles

### 🧪 Desarrollo Local
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs (Swagger)**: http://localhost:8000/docs
- **Redoc**: http://localhost:8000/redoc
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **Qdrant**: http://localhost:6333
- **Langflow**: http://localhost:7860

### 🎯 Pre-Producción (Staging)
- **Frontend**: https://pre.nexusdocs360.app
- **Backend API**: https://api.pre.nexusdocs360.app
- **API Docs**: https://api.pre.nexusdocs360.app/docs

### 🚀 Producción
- **Frontend**: https://nexusdocs360.app (por confirmar)
- **Backend API**: https://api.nexusdocs360.app (por confirmar)
- **API Docs**: https://api.nexusdocs360.app/docs (por confirmar)

## 🐳 Servicios Docker (Desarrollo)

### Microservicios
| Servicio | Puerto | URL Local | Descripción |
|----------|--------|-----------|-------------|
| Main API | 8000 | http://localhost:8000 | API principal FastAPI |
| LangChain | 8001 | http://localhost:8001 | Procesamiento de documentos |
| Langroid | 8002 | http://localhost:8002 | Agentes IA avanzados |
| Storage | 8003 | http://localhost:8003 | Servicio de almacenamiento GCS |
| Ollama | 11434 | http://localhost:11434 | LLMs locales |
| Gotenberg | 3000 | http://gotenberg:3000 | Conversión de documentos |
| Langflow | 7860 | http://localhost:7860 | Constructor visual de agentes |

### Bases de Datos
| Servicio | Puerto | Conexión |
|----------|--------|----------|
| PostgreSQL | 5432 | postgresql://postgres:password@localhost:5432/nexus_db |
| Redis | 6379 | redis://localhost:6379 |
| Qdrant | 6333 | http://localhost:6333 |

## 🔧 Comandos Útiles

### Verificar Estado de Servicios

```bash
# Desarrollo local
curl http://localhost:8000/health
curl http://localhost:3000

# Pre-producción
curl https://api.pre.nexusdocs360.app/health
curl https://pre.nexusdocs360.app

# Verificar API docs
curl https://api.pre.nexusdocs360.app/docs
```

### Acceso a Logs

```bash
# Backend logs (desarrollo)
cd backend/docker
docker-compose logs -f api

# Frontend logs (desarrollo)
cd frontend
npm run dev

# Logs en GCP (pre-producción)
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=nexus-backend-staging" --limit 50
```

## 🔐 Variables de Entorno para Frontend

### Desarrollo (.env.local)
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...
```

### Pre-Producción (.env.staging)
```env
NEXT_PUBLIC_API_URL=https://api.pre.nexusdocs360.app
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...
```

### Producción (.env.production)
```env
NEXT_PUBLIC_API_URL=https://api.nexusdocs360.app
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_live_...
```

## 📊 Monitoreo

### Health Checks
- **Backend Health**: `/health`
- **Backend Ready**: `/ready`
- **Frontend Health**: `/api/health`

### Métricas
- **Prometheus**: `/metrics` (si está configurado)
- **OpenTelemetry**: Configurar en GCP

## 🚨 Troubleshooting

### No se puede acceder a pre.nexusdocs360.app
1. Verificar DNS apunta correctamente
2. Verificar certificado SSL válido
3. Revisar logs en Cloud Run
4. Verificar reglas de firewall

### Error de CORS
1. Verificar `BACKEND_CORS_ORIGINS` incluye el dominio
2. Revisar headers en respuesta
3. Verificar método HTTP permitido

### Error de conexión a base de datos
1. Verificar `DATABASE_URL` correcto
2. Verificar credenciales en Secret Manager
3. Revisar conectividad de red en GCP

## 📝 Notas

- El subdominio `pre` se usa para staging/pre-producción
- Los certificados SSL son gestionados automáticamente por Cloud Run
- Las URLs de producción están pendientes de confirmación
- Langflow solo está disponible en desarrollo local