# 🚀 Guía Completa de Despliegue PRE en GCP - NexusDocs360

## 📋 Índice
1. [Visión General](#visión-general)
2. [Prerequisitos](#prerequisitos)
3. [Arquitectura PRE](#arquitectura-pre)
4. [Paso a Paso del Despliegue](#paso-a-paso-del-despliegue)
5. [Validación](#validación)
6. [Monitoreo](#monitoreo)
7. [Troubleshooting](#troubleshooting)
8. [Rollback](#rollback)

## 🎯 Visión General

El ambiente PRE (Pre-Producción) es una réplica exacta de producción con recursos reducidos, diseñado para:
- Validar cambios antes de producción
- Realizar pruebas de integración completas
- Entrenar usuarios en un ambiente realista
- Probar nuevas características de IA

### Características del Ambiente PRE
- **Recursos**: 50% de capacidad de producción
- **Datos**: Copia anonimizada de producción
- **Acceso**: Restringido a equipo interno
- **URL**: `pre-app.nexusdocs360.com` / `pre-api.nexusdocs360.com`

## ✅ Prerequisitos

### 1. Herramientas Requeridas
```bash
# Verificar instalación
gcloud version          # Google Cloud SDK 450.0.0+
docker --version        # Docker 24.0+
kubectl version         # Kubernetes 1.28+
terraform --version     # Terraform 1.5+ (opcional)
node --version          # Node.js 18+
python --version        # Python 3.9+
```

### 2. Permisos GCP Necesarios
- Project Editor o roles específicos:
  - `roles/compute.admin`
  - `roles/cloudsql.admin`
  - `roles/redis.admin`
  - `roles/storage.admin`
  - `roles/cloudrun.admin`
  - `roles/secretmanager.admin`
  - `roles/iam.serviceAccountAdmin`

### 3. Configuración Inicial
```bash
# Autenticación
gcloud auth login
gcloud auth application-default login

# Crear proyecto PRE si no existe
gcloud projects create nexusdocs360-pre \
  --name="NexusDocs360 PRE" \
  --organization=YOUR_ORG_ID

# Configurar proyecto
gcloud config set project nexusdocs360-pre

# Habilitar billing
gcloud beta billing projects link nexusdocs360-pre \
  --billing-account=YOUR_BILLING_ACCOUNT_ID
```

## 🏗️ Arquitectura PRE

```
┌─────────────────────────────────────────────────────────────┐
│                        Internet                              │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
              ┌───────────────┐
              │  Cloud DNS    │
              │ *.nexusdocs360│
              └───────┬───────┘
                      │
                      ▼
         ┌────────────────────────┐
         │   Nginx Proxy (VM)     │
         │   - SSL Termination    │
         │   - Load Balancing     │
         │   - Rate Limiting      │
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
                ▼                     ▼                     ▼
        ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
        │ PostgreSQL  │      │    Redis    │      │   Qdrant    │
        │ Cloud SQL   │      │ Memorystore │      │     VM      │
        └─────────────┘      └─────────────┘      └─────────────┘
                                      │
                              ┌───────┴────────┐
                              │                │
                      ┌───────▼─────┐  ┌───────▼─────┐
                      │  LangChain  │  │  Langroid   │
                      │  Service    │  │  Service    │
                      └─────────────┘  └─────────────┘
```

## 📝 Paso a Paso del Despliegue

### Paso 1: Preparación del Entorno
```bash
# 1.1 Clonar repositorio
git clone https://github.com/nexusdocs360/nexusdocs360.git
cd nexusdocs360

# 1.2 Crear rama develop para PRE
git checkout -b develop
git push -u origin develop

# 1.3 Configurar variables de entorno
cd deployment/gcp
cp .env.pre .env
nano .env  # Revisar y ajustar valores

# 1.4 Cargar configuración
source load-env.sh
```

### Paso 2: Crear Infraestructura Base
```bash
# 2.1 Usar script automatizado para habilitar APIs
./scripts/enable-apis.sh

# 2.2 Ejecutar script de infraestructura PRE
./deploy-infrastructure.sh pre

# Este script crea automáticamente:
# - VPC y subnets
# - Cloud NAT
# - Cloud SQL PostgreSQL
# - Redis Memorystore
# - Qdrant VM
# - Nginx Proxy VM
# - Buckets de almacenamiento
# - Artifact Registry
```

### Paso 3: Configurar Secrets
```bash
# 3.1 Ejecutar script de secrets
./scripts/setup-secrets-pre.sh

# 3.2 Actualizar secrets críticos
gcloud secrets versions add clerk-secret-pre --data-file=- <<< "YOUR_CLERK_SECRET"
gcloud secrets versions add clerk-publishable-key-pre --data-file=- <<< "YOUR_CLERK_PUB_KEY"
gcloud secrets versions add openai-api-key-pre --data-file=- <<< "YOUR_OPENAI_KEY"
gcloud secrets versions add stripe-secret-pre --data-file=- <<< "YOUR_STRIPE_TEST_KEY"
```

### Paso 4: Configurar CI/CD con GitHub

#### 4.1 Conectar GitHub con Cloud Build
```bash
# Opción 1: Desde la consola web (RECOMENDADO)
echo "1. Ir a: https://console.cloud.google.com/cloud-build/triggers/connect"
echo "2. Seleccionar GitHub"
echo "3. Autorizar Cloud Build"
echo "4. Seleccionar tu repositorio: nexusdocs360/nexusdocs360"
echo "5. Hacer clic en 'Connect'"

# Opción 2: Usando el script automatizado
./setup-triggers.sh tu-usuario/nexusdocs360 pre
```

#### 4.2 Verificar Triggers Creados
```bash
# Listar triggers
gcloud builds triggers list --project=nexusdocs360-pre

# Deberías ver:
# - deploy-pre-on-push (automático en push a develop)
# - validate-pr (validación de PRs)
# - deploy-pre-manual (despliegue manual)
```

### Paso 5: Primer Despliegue Automático

#### 5.1 Preparar el Código
```bash
# Asegurarse de estar en develop
git checkout develop

# Agregar archivos de configuración
git add deployment/gcp/cloudbuild-trigger-pre.yaml
git add deployment/gcp/.env.pre
git commit -m "feat: add PRE deployment configuration"

# Push para activar el despliegue automático
git push origin develop
```

#### 5.2 Monitorear el Build
```bash
# Ver el build en progreso
echo "Ver build en: https://console.cloud.google.com/cloud-build/builds?project=nexusdocs360-pre"

# O desde CLI
gcloud builds list --ongoing --project=nexusdocs360-pre

# Ver logs del build
gcloud builds log [BUILD_ID] --project=nexusdocs360-pre
```

#### 5.3 Qué hace el Build Automático
El trigger de Cloud Build automáticamente:
1. **Compila el código** (sin incluir fuentes)
2. **Crea imágenes Docker** optimizadas
3. **Ejecuta tests** y validaciones
4. **Despliega a Cloud Run** con configuración PRE
5. **Ejecuta migraciones** de base de datos
6. **Valida el despliegue** con smoke tests

### Paso 6: Configurar DNS

#### 6.1 Obtener IP del Nginx Proxy
```bash
# La IP fue creada por el script de infraestructura
NGINX_IP=$(gcloud compute addresses describe nexus-nginx-ip-pre \
  --region=${GCP_REGION} --format="value(address)")

echo "IP del Nginx Proxy: $NGINX_IP"
echo "Usar esta IP para configurar DNS"
```

#### 6.2 Configurar Registros DNS
En tu proveedor de DNS, crear los siguientes registros A:
```
pre.nexusdocs360.com         → [NGINX_IP]
pre-app.nexusdocs360.com     → [NGINX_IP]
pre-api.nexusdocs360.com     → [NGINX_IP]
```

#### 6.3 Verificar Propagación DNS
```bash
# Esperar 5-30 minutos para propagación
nslookup pre-app.nexusdocs360.com
dig pre-api.nexusdocs360.com

# Verificar certificados SSL (se generan automáticamente)
curl -I https://pre-app.nexusdocs360.com
```

### Paso 7: Validación Automática

#### 7.1 Ejecutar Script de Validación
```bash
# Validar que todo esté funcionando
./scripts/validate-pre.sh

# Este script verifica:
# - Infraestructura creada correctamente
# - Servicios Cloud Run desplegados
# - Health checks respondiendo
# - DNS resolviendo correctamente
# - SSL funcionando
```

#### 7.2 Validación Manual
```bash
# Verificar endpoints
curl https://pre-app.nexusdocs360.com/health
curl https://pre-api.nexusdocs360.com/health

# Abrir en navegador
open https://pre-app.nexusdocs360.com
```

## ✅ Validación

### 1. Health Checks
```bash
# Frontend
curl https://pre-app.nexusdocs360.com/api/health

# API
curl https://pre-api.nexusdocs360.com/health

# Microservicios
for service in langchain langroid storage; do
  echo "Checking $service..."
  curl https://pre-api.nexusdocs360.com/api/v1/$service/health
done
```

### 2. Pruebas Funcionales
```bash
# Ejecutar suite de pruebas
cd tests
./run-e2e-tests.sh --env=pre

# Pruebas de IA
python test_ai_features.py --env=pre
```

### 3. Pruebas de Carga
```bash
# Usar k6 para pruebas de carga
k6 run --env ENV=pre tests/load/api-stress-test.js
```

### 4. Checklist de Validación
- [ ] Todos los servicios responden a health checks
- [ ] Login funciona correctamente
- [ ] Upload de documentos exitoso
- [ ] Búsqueda semántica retorna resultados
- [ ] Chat con IA responde correctamente
- [ ] Firmas digitales se procesan
- [ ] Analytics muestra datos
- [ ] Logs se están generando
- [ ] Alertas configuradas

## 📊 Monitoreo

### 1. Configurar Dashboards
```bash
# Importar dashboards predefinidos
gcloud monitoring dashboards create --config-from-file=monitoring/dashboard-pre.yaml
```

### 2. Configurar Alertas
```bash
# Crear políticas de alerta
gcloud alpha monitoring policies create --policy-from-file=monitoring/alerts-pre.yaml
```

### 3. Logs Centralizados
```bash
# Ver logs en tiempo real
gcloud logging tail "resource.type=cloud_run_revision AND resource.labels.service_name=~'nexus-.*-pre'" --format=json
```

## 🔧 Troubleshooting

### Problema: Servicios no se comunican
```bash
# Verificar VPC connector
gcloud compute networks vpc-access connectors describe nexus-connector-pre \
  --region=${GCP_REGION}

# Verificar reglas de firewall
gcloud compute firewall-rules list --filter="network:nexus-vpc-pre"
```

### Problema: Base de datos no conecta
```bash
# Verificar IP privada de Cloud SQL
gcloud sql instances describe nexus-db-pre --format="value(ipAddresses[0].ipAddress)"

# Verificar secrets
gcloud secrets versions access latest --secret=database-url-pre
```

### Problema: IA no responde
```bash
# Verificar logs de servicios IA
gcloud logging read "resource.labels.service_name=nexus-langchain-pre" --limit=50

# Verificar cuotas de API
gcloud compute project-info describe --project=${GCP_PROJECT_ID}
```

## 🔄 Rollback

### Procedimiento de Rollback Rápido
```bash
# 1. Identificar última versión estable
gcloud run revisions list --service=nexus-api-pre --region=${GCP_REGION}

# 2. Redirigir tráfico a versión anterior
gcloud run services update-traffic nexus-api-pre \
  --to-revisions=nexus-api-pre-00005-abc=100 \
  --region=${GCP_REGION}

# 3. Repetir para todos los servicios
for service in frontend langchain langroid; do
  gcloud run services update-traffic nexus-${service}-pre \
    --to-revisions=LATEST-1=100 \
    --region=${GCP_REGION}
done
```

### Backup y Restauración
```bash
# Backup de base de datos
gcloud sql backups create --instance=nexus-db-pre

# Restaurar desde backup
gcloud sql backups restore BACKUP_ID --restore-instance=nexus-db-pre
```

## 📈 Promoción a Producción

Una vez validado en PRE:

```bash
# 1. Merge a main
git checkout main
git merge develop
git push origin main

# 2. Crear tag de versión para activar deploy a PROD
git tag v1.0.0
git push origin v1.0.0

# El tag automáticamente:
# - Activa el trigger de producción
# - Construye imágenes optimizadas
# - Ejecuta validaciones de seguridad
# - Despliega con estrategia Blue-Green
# - Realiza rollback automático si hay errores

# 3. Monitorear deploy
echo "Ver build PROD: https://console.cloud.google.com/cloud-build/builds?project=nexusdocs360-prod"
```

## 🎯 Conclusión

El ambiente PRE está ahora completamente desplegado y listo para pruebas. Recuerda:
- Monitorear constantemente los dashboards
- Ejecutar pruebas completas antes de promover a producción
- Documentar cualquier issue encontrado
- Mantener sincronizados los secrets entre ambientes

---

*NexusDocs360 - Donde la IA Transforma Documentos en Decisiones*