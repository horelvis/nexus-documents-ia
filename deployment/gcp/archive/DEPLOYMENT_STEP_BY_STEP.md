# 🚀 Guía Paso a Paso - Despliegue NexusDocs360 en GCP

## 📋 Tabla de Contenidos
1. [Preparación Inicial](#1-preparación-inicial)
2. [Configuración de GCP](#2-configuración-de-gcp)
3. [Despliegue de Ambiente PRE](#3-despliegue-ambiente-pre)
4. [Despliegue de Ambiente PROD](#4-despliegue-ambiente-prod)
5. [Verificación y Testing](#5-verificación-y-testing)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Preparación Inicial

### 1.1 Requisitos Previos

```bash
# Verificar herramientas instaladas
gcloud --version          # Google Cloud SDK 450.0.0+
docker --version          # Docker 24.0+
node --version           # Node.js 18+
python --version         # Python 3.9+
git --version            # Git 2.x+
```

### 1.2 Clonar Repositorio

```bash
# Clonar el proyecto
git clone https://github.com/nexusdocs360/nexusdocs360.git
cd nexusdocs360

# Verificar estructura
ls -la
# Deberías ver:
# backend/
# frontend/
# deployment/
# microservices/
```

### 1.3 Instalar Dependencias Locales

```bash
# Backend dependencies
cd backend
pip install -r requirements.txt
cd ..

# Frontend dependencies
cd frontend
npm install
cd ..
```

---

## 2. Configuración de GCP

### 2.1 Crear Cuenta y Proyectos

```bash
# Login en GCP
gcloud auth login

# Crear organización (si no existe)
gcloud organizations list

# Crear proyectos
gcloud projects create nexusdocs360-pre --name="NexusDocs360 PRE"
gcloud projects create nexusdocs360-prod --name="NexusDocs360 PROD"

# Listar proyectos creados
gcloud projects list
```

### 2.2 Configurar Billing

```bash
# Obtener billing account ID
gcloud beta billing accounts list

# Asociar billing a proyectos
BILLING_ACCOUNT_ID="XXXXXX-XXXXXX-XXXXXX"
gcloud beta billing projects link nexusdocs360-pre --billing-account=$BILLING_ACCOUNT_ID
gcloud beta billing projects link nexusdocs360-prod --billing-account=$BILLING_ACCOUNT_ID
```

### 2.3 Habilitar APIs Necesarias

```bash
# Para PRE
gcloud config set project nexusdocs360-pre
./deployment/gcp/scripts/enable-apis.sh

# Para PROD
gcloud config set project nexusdocs360-prod
./deployment/gcp/scripts/enable-apis.sh
```

Si no existe el script, crear y ejecutar:

```bash
#!/bin/bash
# enable-apis.sh
gcloud services enable \
  compute.googleapis.com \
  container.googleapis.com \
  cloudbuild.googleapis.com \
  cloudrun.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  cloudtrace.googleapis.com \
  storage.googleapis.com \
  dns.googleapis.com \
  certificatemanager.googleapis.com
```

---

## 3. Despliegue Ambiente PRE

### 3.1 Preparar Repositorio Git

```bash
# Crear estructura de branches
git checkout -b develop
git push -u origin develop

# Configurar branch protection en GitHub
echo "Ir a: Settings > Branches > Add rule"
echo "Branch: develop"
echo "Protecciones: Require status checks"
```

### 3.2 Configurar Variables de Entorno

```bash
cd deployment/gcp

# Copiar y editar configuración PRE
cp .env.pre .env
nano .env

# Contenido de .env para PRE:
```

```env
# Environment
ENVIRONMENT=pre
GCP_PROJECT_ID=nexusdocs360-pre
GCP_REGION=europe-west1
GCP_ZONE=europe-west1-b

# Domain Configuration
DOMAIN=nexusdocs360.com
APP_SUBDOMAIN=pre-app
API_SUBDOMAIN=pre-api
WWW_SUBDOMAIN=pre

# Email for SSL certificates
SSL_EMAIL=admin@nexusdocs360.com

# Resource Sizing
DB_TIER=db-f1-micro
REDIS_SIZE=1
VM_TYPE=e2-small
```

### 3.3 Configurar Secrets

```bash
# Configurar proyecto PRE
gcloud config set project nexusdocs360-pre

# Ejecutar script de secrets
cd deployment/gcp
./scripts/setup-secrets-pre.sh

# Actualizar secrets importantes manualmente
gcloud secrets versions add openai-api-key-pre --data-file=- <<< "sk-..."
gcloud secrets versions add anthropic-api-key-pre --data-file=- <<< "sk-ant-..."
gcloud secrets versions add clerk-secret-pre --data-file=- <<< "sk_test_..."
gcloud secrets versions add clerk-publishable-key-pre --data-file=- <<< "pk_test_..."
gcloud secrets versions add stripe-secret-pre --data-file=- <<< "sk_test_..."
gcloud secrets versions add sendgrid-api-key-pre --data-file=- <<< "SG...."
```

### 3.4 Desplegar Infraestructura PRE

```bash
# Desde deployment/gcp
./deploy-infrastructure.sh pre

# O si ya configuraste .env con proyecto PRE:
./deploy-infrastructure.sh
```

**Esto creará:**
- VPC y subnets
- Cloud SQL PostgreSQL (micro)
- Redis (1GB)
- Qdrant VM
- Nginx proxy VM
- Buckets de almacenamiento
- Artifact Registry

### 3.5 Configurar DNS para PRE

```bash
# Obtener IP del Nginx
NGINX_IP=$(gcloud compute addresses describe nexus-nginx-ip-pre \
  --region=europe-west1 \
  --format="value(address)")

echo "Nginx PRE IP: $NGINX_IP"
```

**En tu proveedor DNS, crear:**
- A record: `pre.nexusdocs360.com` → `NGINX_IP`
- A record: `pre-app.nexusdocs360.com` → `NGINX_IP`
- A record: `pre-api.nexusdocs360.com` → `NGINX_IP`

### 3.5 Configurar CI/CD con GitHub

```bash
# Conectar GitHub con Cloud Build
# Opción 1: Desde la consola web (recomendado)
echo "Ir a: https://console.cloud.google.com/cloud-build/triggers/connect"
echo "Seleccionar tu repositorio GitHub y autorizar"

# Opción 2: Usar el script
cd deployment/gcp
./setup-triggers.sh tu-usuario/nexusdocs360 pre
```

### 3.6 Primer Despliegue Automático

```bash
# Hacer push a develop para activar deploy automático
git checkout develop
git push origin develop

# Ver el build en progreso
echo "Ver build: https://console.cloud.google.com/cloud-build/builds?project=nexusdocs360-pre"
```

### 3.7 Verificar Despliegue PRE

```bash
# Verificar servicios Cloud Run
gcloud run services list --region=europe-west1

# Verificar health checks
curl https://pre-app.nexusdocs360.com/health
curl https://pre-api.nexusdocs360.com/health

# Ver logs
gcloud logging read "resource.type=cloud_run_revision" --limit=50
```

### 3.9 Configurar Monitoreo PRE

```bash
cd deployment/gcp/monitoring
./setup-monitoring-pre.sh

# Acceder a dashboards
echo "Dashboards: https://console.cloud.google.com/monitoring/dashboards?project=nexusdocs360-pre"
```

---

## 4. Despliegue Ambiente PROD

### 4.1 Pre-requisitos para PROD

⚠️ **IMPORTANTE:** Antes de desplegar PROD:
- ✅ PRE debe estar funcionando correctamente
- ✅ Todas las pruebas deben pasar en PRE
- ✅ Backup de cualquier dato importante
- ✅ Plan de rollback preparado

### 4.2 Configurar Variables PROD

```bash
cd deployment/gcp

# Copiar y editar configuración PROD
cp .env.prod .env
nano .env
```

```env
# Environment
ENVIRONMENT=prod
GCP_PROJECT_ID=nexusdocs360-prod
GCP_REGION=europe-west1
GCP_ZONE=europe-west1-b

# Domain Configuration
DOMAIN=nexusdocs360.com
APP_SUBDOMAIN=app
API_SUBDOMAIN=api
WWW_SUBDOMAIN=www

# Email for SSL certificates
SSL_EMAIL=admin@nexusdocs360.com

# Resource Sizing (PROD)
DB_TIER=db-n1-standard-2
REDIS_SIZE=5
VM_TYPE=e2-standard-2
```

### 4.3 Configurar Secrets PROD

```bash
# Configurar proyecto PROD
gcloud config set project nexusdocs360-prod

# Ejecutar script de secrets
./scripts/setup-secrets-prod.sh

# Actualizar secrets importantes (PRODUCCIÓN)
gcloud secrets versions add openai-api-key-prod --data-file=- <<< "sk-..."
gcloud secrets versions add anthropic-api-key-prod --data-file=- <<< "sk-ant-..."
gcloud secrets versions add clerk-secret-prod --data-file=- <<< "sk_live_..."
gcloud secrets versions add clerk-publishable-key-prod --data-file=- <<< "pk_live_..."
gcloud secrets versions add stripe-secret-prod --data-file=- <<< "sk_live_..."
gcloud secrets versions add sendgrid-api-key-prod --data-file=- <<< "SG...."
```

### 4.4 Desplegar Infraestructura PROD

```bash
# Confirmar antes de proceder
echo "⚠️  Esto desplegará recursos de PRODUCCIÓN con costos asociados"
echo "Estimado: $700-1000/mes"
read -p "¿Continuar? (yes/no): " confirm

# Desplegar
./deploy-infrastructure.sh prod
```

**Esto creará:**
- VPC con múltiples subnets
- Cloud SQL con HA y réplicas
- Redis con HA (5GB)
- Cluster de Qdrant (3 nodos)
- Load Balancer con Nginx
- CDN para assets
- KMS para encriptación

### 4.5 Configurar DNS para PROD

```bash
# Obtener IP del Load Balancer
LB_IP=$(gcloud compute addresses describe nexus-lb-ip-prod \
  --global \
  --format="value(address)")

echo "Load Balancer PROD IP: $LB_IP"
```

**En tu proveedor DNS, crear:**
- A record: `nexusdocs360.com` → `LB_IP`
- A record: `www.nexusdocs360.com` → `LB_IP`
- A record: `app.nexusdocs360.com` → `LB_IP`
- A record: `api.nexusdocs360.com` → `LB_IP`

### 4.6 Configurar CI/CD para PROD

```bash
# Configurar triggers para producción
cd deployment/gcp
./setup-triggers.sh tu-usuario/nexusdocs360 prod

# El deploy a PROD se activa con tags de versión
git checkout main
git merge develop
git tag v1.0.0
git push origin main --tags

# Ver el build
echo "Ver build: https://console.cloud.google.com/cloud-build/builds?project=nexusdocs360-prod"
```

### 4.7 Configurar SSL y Seguridad

```bash
# Verificar certificados SSL
echo | openssl s_client -servername nexusdocs360.com -connect nexusdocs360.com:443 2>/dev/null | openssl x509 -noout -dates

# Configurar Cloud Armor (DDoS protection)
gcloud compute security-policies create nexus-security-policy \
  --description="Security policy for NexusDocs360 PROD"

gcloud compute security-policies rules create 1000 \
  --security-policy=nexus-security-policy \
  --action=allow \
  --src-ip-ranges="0.0.0.0/0"
```

### 4.8 Configurar Monitoreo PROD

```bash
cd deployment/gcp/monitoring
./setup-monitoring-prod.sh

# Configurar alertas críticas
gcloud alpha monitoring channels create \
  --display-name="PagerDuty PROD" \
  --type=pagerduty \
  --channel-labels=service_key=$PAGERDUTY_KEY
```

---

## 5. Verificación y Testing

### 5.1 Checklist de Verificación PRE

```bash
# Ejecutar script de validación
./deployment/gcp/scripts/validate-pre.sh
```

**Verificar manualmente:**
- [ ] https://pre-app.nexusdocs360.com carga correctamente
- [ ] Login/registro funciona
- [ ] Upload de documentos exitoso
- [ ] Chat IA responde
- [ ] Búsqueda retorna resultados
- [ ] No hay errores en logs

### 5.2 Checklist de Verificación PROD

```bash
# Ejecutar script de validación
./deployment/gcp/scripts/validate-prod.sh
```

**Verificar manualmente:**
- [ ] https://app.nexusdocs360.com carga correctamente
- [ ] SSL válido y HSTS activo
- [ ] Performance < 2s carga inicial
- [ ] Todas las funcionalidades operativas
- [ ] Monitoreo activo
- [ ] Backups automáticos funcionando

### 5.3 Tests de Carga

```bash
# Instalar k6
brew install k6  # macOS
# o
sudo apt install k6  # Linux

# Ejecutar tests de carga en PRE primero
k6 run --vus 50 --duration 5m tests/load/api-test.js --env ENV=pre

# Si PRE pasa, ejecutar en PROD con menos carga
k6 run --vus 10 --duration 2m tests/load/api-test.js --env ENV=prod
```

---

## 6. Troubleshooting

### 6.1 Problemas Comunes

#### Build de Cloud Build falla
```bash
# Ver logs del build
gcloud builds log [BUILD_ID] --project=nexusdocs360-pre

# Problemas comunes:
# - Secrets no configurados
# - Permisos del service account
# - Errores en tests

# Verificar permisos
gcloud projects get-iam-policy nexusdocs360-pre
```

#### Trigger no se activa
```bash
# Verificar configuración del trigger
gcloud builds triggers describe deploy-pre-on-push --project=nexusdocs360-pre

# Verificar webhook de GitHub
echo "Ir a: GitHub > Settings > Webhooks"
echo "Debe existir webhook de Cloud Build"

# Re-conectar si es necesario
./setup-triggers.sh tu-usuario/nexusdocs360 pre
```

#### DNS no resuelve
```bash
# Verificar propagación DNS
nslookup pre-app.nexusdocs360.com
dig pre-app.nexusdocs360.com

# Esperar 5-30 minutos para propagación
```

#### Servicios no responden
```bash
# Verificar Cloud Run
gcloud run services describe nexus-api-pre --region=europe-west1

# Ver logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=nexus-api-pre" --limit=50

# Verificar conectividad VPC
gcloud compute networks vpc-access connectors describe nexus-connector-pre --region=europe-west1
```

#### Base de datos no conecta
```bash
# Verificar Cloud SQL
gcloud sql instances describe nexus-db-pre

# Verificar IP privada
gcloud sql instances describe nexus-db-pre --format="value(ipAddresses[0].ipAddress)"

# Probar conexión
gcloud sql connect nexus-db-pre --user=nexus_user_pre
```

#### Certificados SSL fallan
```bash
# SSH a Nginx VM
gcloud compute ssh nginx-proxy-pre --zone=europe-west1-b

# Verificar logs de certbot
sudo journalctl -u certbot
sudo cat /var/log/letsencrypt/letsencrypt.log

# Renovar manualmente
sudo certbot renew --nginx
```

### 6.2 Rollback de Emergencia

```bash
# PRE Environment
cd deployment/gcp
./scripts/rollback-traffic-pre.sh

# PROD Environment (requiere tag especial)
git tag rollback-$(date +%Y%m%d)
git push origin rollback-$(date +%Y%m%d)
# Esto activa el trigger de rollback automático
```

### 6.3 Contactos de Soporte

- **DevOps Lead**: devops@nexusdocs360.com
- **On-Call PRE**: pre-oncall@nexusdocs360.com
- **On-Call PROD**: oncall@nexusdocs360.com
- **Emergencias**: +34 XXX XXX XXX

---

## 📝 Notas Importantes

1. **Flujo Git → Deploy:**
   - `git push origin develop` → Deploy automático a PRE
   - `git tag vX.X.X && git push --tags` → Deploy a PROD
   - PRs a develop → Validación automática

2. **Costos Estimados:**
   - PRE: ~$200-250/mes
   - PROD: ~$700-1000/mes
   - Cloud Build: ~$0.003 por minuto de build

3. **Tiempos de Despliegue:**
   - Infraestructura: 30-45 minutos (solo primera vez)
   - Build + Deploy: 10-15 minutos por push
   - DNS: 5-30 minutos propagación

4. **Seguridad del Código:**
   - Código fuente NUNCA en las imágenes
   - Solo archivos compilados/minificados
   - Secrets en Secret Manager, nunca en código

5. **Backups:**
   - Automáticos antes de cada deploy
   - PRE: Diarios, retención 7 días
   - PROD: Cada 4 horas, retención 30 días

---

*Última actualización: [FECHA]*
*Versión: 1.0*