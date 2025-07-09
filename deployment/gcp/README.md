# 🚀 NexusDocs360 - Despliegue en Google Cloud Platform

## 📋 Descripción General

Este directorio contiene toda la configuración necesaria para desplegar NexusDocs360 en GCP.

### 🏗️ Arquitectura
- **Ambientes**: PRE (pre-producción) y PROD (producción)
- **CI/CD**: Cloud Build con despliegue automático
- **Servicios**: Cloud Run, Cloud SQL, Redis, Qdrant
- **Seguridad**: Código compilado, secretos en Secret Manager

## 📚 Documentación

### Para Empezar
1. **[DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)** - Guía completa de despliegue paso a paso
2. **[ROLLBACK_PROCEDURES.md](./ROLLBACK_PROCEDURES.md)** - Procedimientos de emergencia y rollback
3. **[monitoring/README.md](./monitoring/README.md)** - Configuración de monitoreo y alertas

### Estructura de Archivos
```
deployment/gcp/
├── README.md                          # Este archivo
├── DEPLOYMENT_GUIDE.md               # Guía principal de despliegue
├── ROLLBACK_PROCEDURES.md            # Procedimientos de rollback
│
├── cloudbuild-trigger-pre.yaml       # CI/CD para ambiente PRE
├── cloudbuild-trigger-prod.yaml      # CI/CD para ambiente PROD
├── cloudbuild-pr-validation.yaml     # Validación de Pull Requests
│
├── scripts/
│   ├── enable-apis.sh                # Habilitar APIs de GCP
│   ├── setup-secrets-pre.sh          # Configurar secretos PRE
│   ├── setup-secrets-prod.sh         # Configurar secretos PROD
│   ├── deploy-infrastructure-pre.sh  # Desplegar infra PRE
│   ├── deploy-infrastructure-prod.sh # Desplegar infra PROD
│   ├── validate-pre.sh               # Validar ambiente PRE
│   └── validate-prod.sh              # Validar ambiente PROD
│
├── monitoring/
│   ├── README.md                     # Guía de monitoreo
│   ├── dashboard-pre.yaml            # Dashboard PRE
│   ├── alerts-pre.yaml               # Alertas PRE
│   └── setup-monitoring-pre.sh       # Script de configuración
│
├── nginx/
│   ├── nginx-vm-startup-pre.sh       # Config Nginx PRE
│   └── nginx-vm-startup-prod.sh      # Config Nginx PROD
│
└── archive/                          # Documentación deprecada
```

## 🚀 Inicio Rápido

### 1. Prerrequisitos
```bash
# Verificar herramientas
gcloud --version  # Google Cloud SDK 450.0.0+
docker --version  # Docker 24.0+
node --version    # Node.js 18+
python --version  # Python 3.9+
```

### 2. Desplegar Ambiente PRE
```bash
# Autenticación
gcloud auth login

# Crear proyecto
gcloud projects create nexusdocs360-pre --name="NexusDocs360 PRE"

# Configurar y desplegar
cd deployment/gcp
gcloud config set project nexusdocs360-pre
./scripts/enable-apis.sh
./scripts/setup-secrets-pre.sh
./scripts/deploy-infrastructure-pre.sh
```

### 3. Configurar CI/CD
```bash
# Conectar GitHub con Cloud Build
# Ver: https://console.cloud.google.com/cloud-build/triggers/connect

# Configurar triggers
./setup-triggers.sh tu-usuario/nexusdocs360
```

## 🔧 Comandos Útiles

### Gestión de Secretos
```bash
# Listar secretos
gcloud secrets list

# Actualizar un secreto
echo -n "nuevo_valor" | gcloud secrets versions add NOMBRE_SECRETO --data-file=-
```

### Monitoreo
```bash
# Ver logs de un servicio
gcloud run services logs read nexus-api --region=europe-west1

# Ver estado de builds
gcloud builds list --limit=5
```

### Debugging
```bash
# Conectar a base de datos
gcloud sql connect nexus-db-instance --user=postgres

# Ver métricas de Cloud Run
gcloud run services describe nexus-api --region=europe-west1
```

## 🌳 Flujo de Trabajo Git

```
main (producción)
  └── develop (pre-producción)
       ├── feature/nueva-funcionalidad
       ├── bugfix/corrección
       └── hotfix/parche-urgente
```

### Despliegue Automático
- **Push a `develop`** → Deploy automático a PRE
- **Tag en `main`** → Deploy automático a PROD

```bash
# Deploy a PRE
git push origin develop

# Deploy a PROD
git tag v1.0.0
git push origin v1.0.0
```

## 🔒 Seguridad

El sistema está diseñado para proteger el código fuente:
- ✅ Solo se despliegan archivos compilados/minificados
- ✅ Python compilado a `.pyc` y empaquetado
- ✅ Frontend solo incluye bundle de producción
- ✅ Secretos gestionados con Secret Manager
- ✅ Escaneo de seguridad automático en CI/CD

## 📊 Enlaces Útiles

### Consolas GCP
- [Cloud Build](https://console.cloud.google.com/cloud-build/builds)
- [Cloud Run](https://console.cloud.google.com/run)
- [Secret Manager](https://console.cloud.google.com/security/secret-manager)
- [Monitoring](https://console.cloud.google.com/monitoring)

### Ambientes
- **PRE**: https://pre-app.nexusdocs360.com
- **PROD**: https://app.nexusdocs360.com

## 🚨 Soporte

### En caso de problemas:
1. Revisar [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md#troubleshooting)
2. Consultar logs en Cloud Console
3. Para emergencias: [ROLLBACK_PROCEDURES.md](./ROLLBACK_PROCEDURES.md)

### Contacto
- Email: devops@nexusdocs360.com
- Slack: #nexusdocs-devops