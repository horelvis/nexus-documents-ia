# 🚀 Nexus Document - Guía de Despliegue

Este documento describe cómo desplegar la aplicación Nexus Document en diferentes entornos.

## 📋 Requisitos Previos

- Docker y Docker Compose instalados
- Node.js 20+ (para desarrollo frontend)
- Python 3.11+ (para desarrollo backend)
- Credenciales GCS configuradas (para producción)

## 🛠️ Variables de Entorno

### Backend
Copiar y configurar archivo de entorno:
```bash
cp backend/.env.example backend/.env
```

Variables principales:
- `DATABASE_URL`: Conexión a PostgreSQL
- `GCS_PROJECT_ID`: ID del proyecto Google Cloud
- `GCS_BUCKET_NAME`: Nombre del bucket GCS
- `GCS_CREDENTIALS`: Ruta a credenciales GCS
- `TESTING`: true/false para modo testing

### Frontend
Copiar y configurar archivo de entorno:
```bash
cp frontend/.env.example frontend/.env
```

## 🐳 Opciones de Despliegue

### 1. Desarrollo Local

#### Backend
```bash
cd backend/docker
docker-compose up -d
```

Servicios incluidos:
- API FastAPI (puerto 8000)
- PostgreSQL (puerto 5432)
- Redis (puerto 6379)
- Qdrant (vectores, puerto 6333)
- GCS Mock (puerto 4443)

#### Frontend
```bash
cd frontend
npm install
npm run dev
```

Acceso: http://localhost:3000

### 2. Entorno de Testing

#### Backend con Tests
```bash
cd backend/docker
docker-compose -f docker-compose.test.yml up -d

# Ejecutar tests
docker-compose -f docker-compose.test.yml exec api pytest
```

#### Frontend con Tests
```bash
cd frontend
npm run test
npm run test:coverage
```

### 3. Producción Local/Remota

#### Backend - Build y Deploy
```bash
cd backend

# 1. Crear imagen
docker build -f docker/Dockerfile -t nexus-backend:latest .

# 2. Deploy con compose de producción
cd docker
docker-compose -f docker-compose.prod.yml up -d
```

#### Frontend - Build y Deploy
```bash
cd frontend

# 1. Build de producción
npm run build

# 2. Crear imagen Docker
docker build -t nexus-frontend:latest .

# 3. Ejecutar contenedor
docker run -p 3000:3000 \
  -e NODE_ENV=production \
  nexus-frontend:latest
```

### 4. Stack Completo (Recomendado)

#### Crear red compartida
```bash
docker network create nexus-network
```

#### Deploy Backend
```bash
cd backend/docker
docker-compose up -d
```

#### Deploy Frontend
```bash
cd frontend
docker build -t nexus-frontend .
docker run -p 3000:3000 \
  --network nexus-network \
  --name nexus-frontend \
  nexus-frontend
```

## 🔧 Comandos Útiles

### Verificar Estado de Servicios
```bash
# Backend
docker-compose ps
docker-compose logs api

# Frontend
docker logs nexus-frontend
```

### Reiniciar Servicios
```bash
# Backend
docker-compose restart api

# Frontend
docker restart nexus-frontend
```

### Acceso a Base de Datos
```bash
# Conectar a PostgreSQL
docker-compose exec db psql -U postgres -d nexus_db
```

### Limpiar Recursos
```bash
# Parar y limpiar backend
cd backend/docker
docker-compose down -v

# Parar frontend
docker stop nexus-frontend
docker rm nexus-frontend

# Limpiar red
docker network rm nexus-network
```

## 🌐 URLs de Acceso

### Desarrollo
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Docs API: http://localhost:8000/docs
- PostgreSQL: localhost:5432
- Redis: localhost:6379
- Qdrant: http://localhost:6333

### Producción
- Frontend: http://localhost:3000
- Backend API: http://localhost:80 (via Nginx)
- API Docs: http://localhost:80/docs

## 🐛 Troubleshooting

### Error de Conexión a Base de Datos
```bash
# Verificar estado de PostgreSQL
docker-compose exec db pg_isready -U postgres

# Recrear volumen si es necesario
docker-compose down -v
docker-compose up -d
```

### Error en GCS
```bash
# Verificar credenciales
ls -la backend/credentials/

# Para testing, usar modo mock
export TESTING=true
```

### Error de Puertos
```bash
# Verificar puertos en uso
lsof -i :8000
lsof -i :3000

# Cambiar puertos en docker-compose.yml si es necesario
```

## 📊 Monitoreo

### Health Checks
```bash
# Backend
curl http://localhost:8000/health

# Frontend
curl http://localhost:3000
```

### Logs en Tiempo Real
```bash
# Backend
docker-compose logs -f api

# Frontend
docker logs -f nexus-frontend
```

## 🔒 Seguridad en Producción

1. **Variables de Entorno**: Nunca commitear archivos `.env` con credenciales reales
2. **HTTPS**: Configurar SSL/TLS en Nginx para producción
3. **Firewall**: Limitar acceso a puertos de base de datos
4. **Credenciales**: Usar secretos de Docker/Kubernetes para credenciales sensibles

## 📝 Notas Adicionales

- El backend incluye mock de GCS para desarrollo sin credenciales reales
- Los tests usan una base de datos separada configurada automáticamente
- Para producción, configurar Nginx con SSL y balanceador de carga
- Considerar usar Docker Swarm o Kubernetes para alta disponibilidad