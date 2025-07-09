# 🚀 Guía de Despliegue - NexusDocs360 en GCP

## 📋 Índice
1. [Visión General](#visión-general)
2. [Prerrequisitos](#prerrequisitos)
3. [Configuración Inicial](#configuración-inicial)
4. [Despliegue Ambiente PRE](#despliegue-ambiente-pre)
5. [Despliegue Ambiente PROD](#despliegue-ambiente-prod)
6. [CI/CD con Cloud Build](#cicd-con-cloud-build)
7. [Validación](#validación)
8. [Troubleshooting](#troubleshooting)

## 🎯 Visión General

NexusDocs360 utiliza una arquitectura de microservicios en GCP con dos ambientes:
- **PRE (Pre-producción)**: Para pruebas y validación
- **PROD (Producción)**: Ambiente productivo con alta disponibilidad

### Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                        Internet                              │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
              ┌───────────────┐
              │  Cloud DNS    │
              └───────┬───────┘
                      │
                      ▼
         ┌────────────────────────┐
         │   Nginx Proxy (VM)     │
         │   - SSL Termination    │
         │   - Load Balancing     │
         └────────────┬───────────┘
                      │
      ┌───────────────┴────────────────┐
      │                                │
      ▼                                ▼
┌─────────────┐                ┌──────────────┐
│  Frontend   │                │   Backend    │
│ Cloud Run   │                │  Cloud Run   │
│ (Next.js)   │                │  (FastAPI)   │
└─────────────┘                └──────┬───────┘
                                      │
                ┌─────────────────────┼─────────────────────┐
                │                     │                     │
           ┌────▼────┐          ┌────▼────┐          ┌────▼────┐
           │Cloud SQL│          │  Redis  │          │ Qdrant  │
           │PostgreSQL│         │MemoryDB │          │ Vector  │
           └─────────┘          └─────────┘          └─────────┘
```

## ✅ Prerrequisitos

### Herramientas Requeridas
```bash
# Verificar instalación
gcloud --version          # Google Cloud SDK 450.0.0+
docker --version          # Docker 24.0+
node --version           # Node.js 18+
python --version         # Python 3.9+
git --version            # Git 2.x+
```

### Permisos GCP Necesarios
- Project Editor o roles específicos:
  - `roles/cloudsql.admin`
  - `roles/redis.admin`
  - `roles/storage.admin`
  - `roles/cloudrun.admin`
  - `roles/secretmanager.admin`
  - `roles/iam.serviceAccountAdmin`

## 🔧 Configuración Inicial

### 1. Clonar Repositorio
```bash
git clone https://github.com/nexusdocs360/nexusdocs360.git
cd nexusdocs360
```

### 2. Autenticación GCP
```bash
gcloud auth login
gcloud auth application-default login
```

### 3. Crear Proyectos GCP
```bash
# Crear proyecto PRE
gcloud projects create nexusdocs360-pre --name="NexusDocs360 PRE"

# Crear proyecto PROD
gcloud projects create nexusdocs360-prod --name="NexusDocs360 PROD"

# Listar proyectos
gcloud projects list
```

### 4. Configurar Billing
```bash
# Obtener billing account ID
gcloud beta billing accounts list

# Asociar billing a proyectos
BILLING_ACCOUNT_ID="XXXXXX-XXXXXX-XXXXXX"
gcloud beta billing projects link nexusdocs360-pre --billing-account=$BILLING_ACCOUNT_ID
gcloud beta billing projects link nexusdocs360-prod --billing-account=$BILLING_ACCOUNT_ID
```

## 🏗️ Despliegue Ambiente PRE

### 1. Configurar Proyecto PRE
```bash
cd deployment/gcp
gcloud config set project nexusdocs360-pre
```

### 2. Habilitar APIs
```bash
./scripts/enable-apis.sh
```

### 3. Configurar Secretos
```bash
# Ejecutar script de configuración
./scripts/setup-secrets-pre.sh

# Actualizar secretos desde archivo .env del backend
./scripts/update-secrets-from-env.sh

# O manualmente si prefieres:
# echo -n "tu_clerk_secret" | gcloud secrets versions add clerk-secret-pre --data-file=-
# echo -n "tu_clerk_publishable_key" | gcloud secrets versions add clerk-publishable-key-pre --data-file=-
# echo -n "tu_stripe_secret" | gcloud secrets versions add stripe-secret-pre --data-file=-
# echo -n "tu_openai_key" | gcloud secrets versions add openai-api-key-pre --data-file=-
```

### 4. Desplegar Infraestructura
```bash
# Ejecutar script de despliegue
./scripts/deploy-infrastructure-pre.sh
```

### 5. Configurar DNS
```bash
# Obtener IP del Nginx
NGINX_IP=$(gcloud compute addresses describe nexus-nginx-ip-pre \
  --region=europe-west1 --format="value(address)")
echo "IP para DNS: $NGINX_IP"
```

Configurar en tu proveedor DNS:
- `pre.nexusdocs360.com` → `[NGINX_IP]`
- `pre-app.nexusdocs360.com` → `[NGINX_IP]`
- `pre-api.nexusdocs360.com` → `[NGINX_IP]`

## 🚀 Despliegue Ambiente PROD

### 1. Configurar Proyecto PROD
```bash
gcloud config set project nexusdocs360-prod
```

### 2. Seguir Mismos Pasos
Repetir pasos 2-5 del ambiente PRE usando:
- Script: `./scripts/setup-secrets-prod.sh`
- Script: `./scripts/deploy-infrastructure-prod.sh`
- Dominios sin prefijo "pre"

## 📦 CI/CD con Cloud Build

### 1. Conectar GitHub con Cloud Build

#### Desde la Consola Web:
1. Ir a [Cloud Build Triggers](https://console.cloud.google.com/cloud-build/triggers)
2. Click **"Connect Repository"**
3. Seleccionar **GitHub**
4. Autorizar Cloud Build
5. Seleccionar tu repositorio

### 2. Crear Service Account para Builds
```bash
# PRE environment
gcloud config set project nexusdocs360-pre

# Crear service account
gcloud iam service-accounts create cloud-build-deployer \
  --display-name="Cloud Build Deployer PRE"

# Asignar permisos
PROJECT_ID=nexusdocs360-pre
BUILD_SA=cloud-build-deployer@${PROJECT_ID}.iam.gserviceaccount.com

for role in \
  roles/run.admin \
  roles/iam.serviceAccountUser \
  roles/storage.admin \
  roles/secretmanager.secretAccessor \
  roles/artifactregistry.admin
do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${BUILD_SA}" \
    --role="$role"
done
```

### 3. Configurar Triggers Automáticos
```bash
# Ejecutar script de configuración
./setup-triggers.sh tu-usuario/nexusdocs360
```

### 4. Flujo de Trabajo Git

```bash
# Desarrollo en feature branch
git checkout -b feature/nueva-funcionalidad
git add .
git commit -m "feat: nueva funcionalidad"
git push origin feature/nueva-funcionalidad

# Crear PR a develop en GitHub
# Cloud Build valida automáticamente

# Merge a develop = Deploy automático a PRE

# Deploy a PROD (desde main)
git checkout main
git merge develop
git tag v1.0.0
git push origin main --tags
# Deploy automático a PROD
```

## ✅ Validación

### PRE Environment
```bash
cd deployment/gcp
./scripts/validate-pre.sh
```

### PROD Environment
```bash
./scripts/validate-prod.sh
```

### Checklist de Validación
- [ ] Nginx VM está corriendo
- [ ] Cloud SQL PostgreSQL accesible
- [ ] Redis Memorystore operativo
- [ ] Qdrant vector database funcionando
- [ ] Cloud Run services desplegados
- [ ] DNS resuelve correctamente
- [ ] SSL certificados activos
- [ ] API responde en `/docs`
- [ ] Frontend carga correctamente
- [ ] Autenticación Clerk funciona
- [ ] Uploads a GCS funcionan

## 🚨 Troubleshooting

### Build Falla
```bash
# Ver logs del build
gcloud builds log BUILD_ID --project=nexusdocs360-pre

# Ver triggers
gcloud builds triggers list --project=nexusdocs360-pre
```

### Secretos no Encontrados
```bash
# Listar secretos
gcloud secrets list

# Verificar acceso
gcloud secrets get-iam-policy SECRET_NAME
```

### Service No Responde
```bash
# Ver logs de Cloud Run
gcloud run services logs read nexus-api --region=europe-west1

# Describir servicio
gcloud run services describe nexus-api --region=europe-west1
```

### DNS/SSL Issues
```bash
# Verificar DNS
nslookup pre-app.nexusdocs360.com

# Verificar certificado
curl -v https://pre-api.nexusdocs360.com/health
```

## 📊 Monitoreo

- **Builds**: https://console.cloud.google.com/cloud-build/builds
- **PRE**: https://console.cloud.google.com/monitoring?project=nexusdocs360-pre
- **PROD**: https://console.cloud.google.com/monitoring?project=nexusdocs360-prod

## 🔄 Procedimientos de Rollback

Ver [ROLLBACK_PROCEDURES.md](./ROLLBACK_PROCEDURES.md) para instrucciones detalladas.

## 📚 Referencias Adicionales

- [Monitoreo y Alertas](./monitoring/README.md)
- [Cloud Build Documentation](https://cloud.google.com/build/docs)
- [Cloud Run Best Practices](https://cloud.google.com/run/docs/best-practices)