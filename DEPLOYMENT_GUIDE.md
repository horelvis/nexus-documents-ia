# 🚀 Guía Paso a Paso - Deployments Separados

Esta guía usa las variables y configuración que ya tienes configuradas.

## 📋 Configuración Actual Detectada

✅ **Proyecto GCP**: `nexusdocs360-pre`  
✅ **Región**: `europe-west1`  
✅ **Base de datos**: `nexusdocs360-pre:europe-west1:nexusdocuments360db`  
✅ **GCS Bucket**: `nexus-docs-eu`  
✅ **Dominio**: `nexusdocs360.app`  

## 🎯 Paso 1: Preparar el Entorno

### 1.1 Verificar herramientas instaladas
```bash
# Verificar que tienes gcloud configurado
gcloud config list
gcloud auth list

# Verificar Docker
docker --version

# Configurar proyecto
gcloud config set project nexusdocs360-pre
gcloud config set compute/region europe-west1
```

### 1.2 Habilitar APIs necesarias
```bash
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable sqladmin.googleapis.com
gcloud services enable secretmanager.googleapis.com
```

## 🔐 Paso 2: Configurar Secrets en Google Cloud

### 2.1 Configurar variables de entorno
```bash
# Configurar variables de entorno con tus secrets (usa tus valores reales del archivo .env)
export CLERK_SECRET_KEY="your-clerk-secret-key"
export STRIPE_SECRET_KEY="your-stripe-secret-key"
export STRIPE_WEBHOOK_SECRET="your-stripe-webhook-secret"
export POSTGRES_PASSWORD="your-database-password"
export MICROSERVICES_API_KEY="your-microservices-api-key"
export MAIL_PASSWORD="your-gmail-app-password"

# O cargar desde el archivo .env del backend
source backend/.env
```

### 2.2 Ejecutar script de configuración
```bash
# Crear secrets usando el script (usa las variables de entorno)
./scripts/setup-secrets.sh
```

### 2.2 Subir credenciales de GCS
```bash
# Asegúrate de que tienes el archivo de credenciales
gcloud secrets create gcs-credentials --data-file=backend/credentials/nexusdocs360-pre-04252dae0146.json
```

## 🗄️ Paso 3: Configurar Base de Datos

### 3.1 Verificar instancia de Cloud SQL
```bash
# Verificar que existe la instancia
gcloud sql instances describe nexusdocuments360db

# Si no existe, crearla
gcloud sql instances create nexusdocuments360db \
    --database-version=POSTGRES_13 \
    --tier=db-f1-micro \
    --region=europe-west1
```

### 3.2 Crear base de datos
```bash
gcloud sql databases create nexusdocuments360db --instance=nexusdocuments360db
```

## 🔧 Paso 4: Actualizar Scripts con tu Configuración

### 4.1 Actualizar script de backend
```bash
# Editar el archivo scripts/deploy-backend.sh
sed -i 's/your-project-id/nexusdocs360-pre/g' scripts/deploy-backend.sh
sed -i 's/us-central1/europe-west1/g' scripts/deploy-backend.sh
sed -i 's/your-project:region:instance/nexusdocs360-pre:europe-west1:nexusdocuments360db/g' scripts/deploy-backend.sh
```

### 4.2 Actualizar script de frontend
```bash
# Editar el archivo scripts/deploy-frontend.sh
sed -i 's/your-project-id/nexusdocs360-pre/g' scripts/deploy-frontend.sh
sed -i 's/us-central1/europe-west1/g' scripts/deploy-frontend.sh
```

## 🚀 Paso 5: Deploy del Backend

### 5.1 Preparar variables de entorno
```bash
# Ir al directorio backend
cd backend

# Exportar variables necesarias
export PROJECT_ID="nexusdocs360-pre"
export REGION="europe-west1"
export DATABASE_URL="postgresql://your_user:password@/nexusdocuments360db?host=/cloudsql/nexusdocs360-pre:europe-west1:nexusdocuments360db"
```

### 5.2 Ejecutar deploy del backend
```bash
# Construir imagen
docker build -f Dockerfile.prod -t gcr.io/nexusdocs360-pre/nexus-backend:latest .

# Subir a Container Registry
docker push gcr.io/nexusdocs360-pre/nexus-backend:latest

# Deploy a Cloud Run
gcloud run deploy nexus-backend \
    --image gcr.io/nexusdocs360-pre/nexus-backend:latest \
    --platform managed \
    --region europe-west1 \
    --project nexusdocs360-pre \
    --allow-unauthenticated \
    --memory 1Gi \
    --cpu 2 \
    --concurrency 100 \
    --max-instances 10 \
    --min-instances 1 \
    --timeout 300 \
    --port 8000 \
    --add-cloudsql-instances nexusdocs360-pre:europe-west1:nexusdocuments360db \
    --set-env-vars "GCS_PROJECT_ID=nexusdocs360-pre,GCS_BUCKET_NAME=nexus-docs-eu,DEBUG=false" \
    --set-secrets "CLERK_SECRET_KEY=clerk-secret-key:latest,STRIPE_SECRET_KEY=stripe-secret-key:latest,POSTGRES_PASSWORD=postgres-password:latest,MICROSERVICES_API_KEY=microservices-api-key:latest,MAIL_PASSWORD=mail-password:latest" \
    --service-account nexus-backend@nexusdocs360-pre.iam.gserviceaccount.com
```

## 🎨 Paso 6: Deploy del Frontend

### 6.1 Obtener URL del backend
```bash
BACKEND_URL=$(gcloud run services describe nexus-backend \
    --platform managed \
    --region europe-west1 \
    --project nexusdocs360-pre \
    --format 'value(status.url)')

echo "Backend URL: $BACKEND_URL"
```

### 6.2 Ejecutar deploy del frontend
```bash
# Ir al directorio frontend
cd ../frontend

# Construir imagen con variables
docker build -f Dockerfile.prod -t gcr.io/nexusdocs360-pre/nexus-frontend:latest \
    --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="pk_test_ZGVlcC1yYWJiaXQtMjkuY2xlcmsuYWNjb3VudHMuZGV2JA" \
    --build-arg NEXT_PUBLIC_API_BASE_URL="$BACKEND_URL" \
    --build-arg NEXT_PUBLIC_FRONTEND_URL="https://pre.nexusdocs360.app" \
    --build-arg NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY="pk_test_51RitIlR8hZSzPrz7s9giSrKIVQOQrHkxnlDkpRvxFwlJwAayDMsbqlkoweIq164iInWmYsYGaRZ0Tkn7oTKW3d7c00bl16u2XR" \
    .

# Subir imagen
docker push gcr.io/nexusdocs360-pre/nexus-frontend:latest

# Deploy a Cloud Run
gcloud run deploy nexus-frontend \
    --image gcr.io/nexusdocs360-pre/nexus-frontend:latest \
    --platform managed \
    --region europe-west1 \
    --project nexusdocs360-pre \
    --allow-unauthenticated \
    --memory 512Mi \
    --cpu 1 \
    --concurrency 100 \
    --max-instances 5 \
    --min-instances 0 \
    --timeout 300 \
    --port 3000
```

## 🔗 Paso 7: Configurar Dominio (Opcional)

### 7.1 Mapear dominio custom
```bash
# Para el frontend
gcloud run domain-mappings create \
    --service nexus-frontend \
    --domain pre.nexusdocs360.app \
    --region europe-west1

# Para el backend  
gcloud run domain-mappings create \
    --service nexus-backend \
    --domain pre-api.nexusdocs360.app \
    --region europe-west1
```

## ✅ Paso 8: Verificar Deployment

### 8.1 Obtener URLs de los servicios
```bash
# URL del frontend
FRONTEND_URL=$(gcloud run services describe nexus-frontend \
    --platform managed \
    --region europe-west1 \
    --project nexusdocs360-pre \
    --format 'value(status.url)')

# URL del backend
BACKEND_URL=$(gcloud run services describe nexus-backend \
    --platform managed \
    --region europe-west1 \
    --project nexusdocs360-pre \
    --format 'value(status.url)')

echo "🎨 Frontend: $FRONTEND_URL"
echo "📚 Backend: $BACKEND_URL"
```

### 8.2 Probar los servicios
```bash
# Probar backend health
curl "$BACKEND_URL/health"

# Probar frontend (debería devolver HTML)
curl -I "$FRONTEND_URL"
```

## 🔄 Comandos Rápidos para Re-deployment

```bash
# Solo backend
cd backend && ./scripts/deploy-backend.sh

# Solo frontend  
cd frontend && ./scripts/deploy-frontend.sh

# Ambos
./scripts/deploy-all.sh
```

## 🐛 Troubleshooting

### Ver logs de los servicios
```bash
# Logs del backend
gcloud run services logs read nexus-backend --region europe-west1

# Logs del frontend
gcloud run services logs read nexus-frontend --region europe-west1
```

### Verificar secrets
```bash
gcloud secrets list
```

### Verificar permisos de servicio account
```bash
gcloud projects get-iam-policy nexusdocs360-pre
```