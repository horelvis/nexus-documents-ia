# 🚀 GitHub Actions Setup Guide - NexusDocs360

## 📋 Índice
1. [Visión General](#visión-general)
2. [Preparación](#preparación)
3. [Configuración de Secrets](#configuración-de-secrets)
4. [Configuración de Environments](#configuración-de-environments)
5. [Flujo de Trabajo](#flujo-de-trabajo)
6. [Verificación](#verificación)
7. [Troubleshooting](#troubleshooting)

## 🎯 Visión General

GitHub Actions reemplaza a Cloud Build para el CI/CD, ofreciendo:
- ✅ Control total del pipeline en tu repositorio
- ✅ Sin dependencia de servicios GCP para CI/CD
- ✅ Mejor integración con GitHub (PRs, issues, etc.)
- ✅ Logs y métricas directamente en GitHub

### Arquitectura del Flujo

```
[GitHub Repo] → [GitHub Actions] → [GCP Cloud Run]
     ↓                ↓                    ↓
   Push/Tag      Build & Test         Deploy Only
```

## 📝 Preparación

### 1. Crear Service Account en GCP

```bash
# Para PRE
gcloud config set project nexusdocs360-pre

# Crear service account
gcloud iam service-accounts create github-actions-sa \
  --display-name="GitHub Actions Service Account" \
  --description="Service account for GitHub Actions deployments"

# Asignar permisos necesarios
PROJECT_ID=nexusdocs360-pre
SA_EMAIL=github-actions-sa@${PROJECT_ID}.iam.gserviceaccount.com

# Permisos mínimos necesarios
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudsql.client"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/logging.logWriter"

# Crear y descargar key
gcloud iam service-accounts keys create github-actions-key-pre.json \
  --iam-account=${SA_EMAIL}

# IMPORTANTE: Guardar este archivo de forma segura, lo necesitarás para GitHub
```

### 2. Repetir para PROD

```bash
# Para PROD
gcloud config set project nexusdocs360-prod

# Crear service account
gcloud iam service-accounts create github-actions-sa \
  --display-name="GitHub Actions Service Account" \
  --description="Service account for GitHub Actions deployments"

# Asignar permisos (mismos que PRE)
PROJECT_ID=nexusdocs360-prod
SA_EMAIL=github-actions-sa@${PROJECT_ID}.iam.gserviceaccount.com

# ... (repetir los mismos comandos de permisos)

# Crear key para PROD
gcloud iam service-accounts keys create github-actions-key-prod.json \
  --iam-account=${SA_EMAIL}
```

## 🔐 Configuración de Secrets

### 1. Ir a GitHub Repository Settings

```
https://github.com/TU_USUARIO/nexusdocs360/settings/secrets/actions
```

### 2. Crear los siguientes Secrets

#### Secrets de Autenticación GCP

| Secret Name | Description | How to Get |
|------------|-------------|------------|
| `GCP_SA_KEY_PRE` | Service Account key para PRE | Contenido de `github-actions-key-pre.json` |
| `GCP_SA_KEY_PROD` | Service Account key para PROD | Contenido de `github-actions-key-prod.json` |

#### Proceso para agregar secrets:

1. Click en "New repository secret"
2. Name: `GCP_SA_KEY_PRE`
3. Value: Pegar todo el contenido del archivo JSON
4. Click "Add secret"
5. Repetir para `GCP_SA_KEY_PROD`

### 3. Verificar Secrets en GCP

Asegúrate de que estos secrets existan en Secret Manager de GCP:

```bash
# Para PRE
gcloud config set project nexusdocs360-pre
gcloud secrets list | grep -E "(database-url|redis-url|clerk|openai|anthropic|stripe|sendgrid)"

# Para PROD
gcloud config set project nexusdocs360-prod
gcloud secrets list | grep -E "(database-url|redis-url|clerk|openai|anthropic|stripe|sendgrid)"
```

## 🌍 Configuración de Environments

### 1. Crear Environment "pre-production"

1. Ir a: `Settings > Environments > New environment`
2. Name: `pre-production`
3. Configure:
   - ✅ Required reviewers: 0 (opcional para PRE)
   - ✅ Deployment branches: `develop`

### 2. Crear Environment "production"

1. Ir a: `Settings > Environments > New environment`
2. Name: `production`
3. Configure:
   - ✅ Required reviewers: 1-2 personas
   - ✅ Deployment branches: `main` + tags `v*`
   - ✅ Wait timer: 5 minutos (opcional)

### 3. Agregar Protection Rules

Para producción, agregar reglas de protección:
- Require approval from specific users
- Restrict deployment to specific branches/tags
- Add deployment delay if needed

## 🔄 Flujo de Trabajo

### 1. Desarrollo Normal

```bash
# Crear feature branch
git checkout -b feature/nueva-funcionalidad develop

# Hacer cambios y commit
git add .
git commit -m "feat: add new feature"

# Push y crear PR
git push origin feature/nueva-funcionalidad
# Crear PR en GitHub → develop
```

**Resultado**: Se ejecuta `pr-validation.yml` automáticamente

### 2. Deploy a PRE

```bash
# Merge PR a develop (desde GitHub)
# O push directo a develop
git checkout develop
git push origin develop
```

**Resultado**: Se ejecuta `deploy-pre.yml` automáticamente

### 3. Deploy a PROD

```bash
# Merge develop a main
git checkout main
git merge develop

# Crear tag de versión
git tag v1.0.0
git push origin main --tags
```

**Resultado**: Se ejecuta `deploy-prod.yml` automáticamente

## ✅ Verificación

### 1. Verificar Workflows

```bash
# Ver archivos de workflow
ls -la .github/workflows/
# Deberías ver:
# - deploy-pre.yml
# - deploy-prod.yml  
# - pr-validation.yml
```

### 2. Primer Test - PR Validation

```bash
# Crear branch de test
git checkout -b test/github-actions develop
echo "test" > test.txt
git add test.txt
git commit -m "test: GitHub Actions"
git push origin test/github-actions

# Crear PR en GitHub
# Ver que se ejecute pr-validation.yml
```

### 3. Test Deploy PRE

```bash
git checkout develop
git merge test/github-actions
git push origin develop

# Ver en GitHub Actions que se ejecute deploy-pre.yml
# URL: https://github.com/TU_USUARIO/nexusdocs360/actions
```

### 4. Verificar Deployment

```bash
# Esperar a que termine el deployment
# Verificar servicios
curl https://pre-api.nexusdocs360.com/health
curl https://pre-app.nexusdocs360.com/api/health
```

## 🔧 Troubleshooting

### Error: Authentication failed

```yaml
# Verificar que el secret esté bien configurado
# En el workflow debe ser:
credentials_json: ${{ secrets.GCP_SA_KEY_PRE }}
```

### Error: Permission denied

```bash
# Verificar permisos del service account
gcloud projects get-iam-policy nexusdocs360-pre \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:github-actions-sa@*"
```

### Error: Secret not found

```bash
# Verificar que los secrets existan en GCP
gcloud secrets list --project=nexusdocs360-pre

# Si falta alguno, crearlo:
echo -n "valor-del-secret" | gcloud secrets create nombre-del-secret --data-file=-
```

### Ver Logs de GitHub Actions

1. Ir a: `https://github.com/TU_USUARIO/nexusdocs360/actions`
2. Click en el workflow que falló
3. Click en el job específico
4. Expandir los pasos para ver logs detallados

### Rerun Failed Workflow

```bash
# Desde la UI de GitHub Actions
# Click en "Re-run all jobs" o "Re-run failed jobs"
```

## 📊 Monitoreo

### GitHub Actions Dashboard

- **URL**: `https://github.com/TU_USUARIO/nexusdocs360/actions`
- **Métricas**: Tiempo de build, tasa de éxito, uso de minutos

### Notifications

Configurar notificaciones en GitHub:
1. `Settings > Notifications`
2. Activar "Actions" para recibir emails

### Status Badge

Agregar badge al README:

```markdown
![Deploy PRE](https://github.com/TU_USUARIO/nexusdocs360/workflows/Deploy%20to%20PRE%20Environment/badge.svg?branch=develop)
![Deploy PROD](https://github.com/TU_USUARIO/nexusdocs360/workflows/Deploy%20to%20PRODUCTION/badge.svg?branch=main)
```

## 🚀 Próximos Pasos

1. **Eliminar Cloud Build Triggers** (opcional):
   ```bash
   # Listar triggers existentes
   gcloud builds triggers list --project=nexusdocs360-pre
   
   # Eliminar si ya no se necesitan
   gcloud builds triggers delete TRIGGER_NAME --project=nexusdocs360-pre
   ```

2. **Optimizar Workflows**:
   - Agregar cache de dependencias
   - Paralelizar jobs donde sea posible
   - Agregar más tests

3. **Seguridad Adicional**:
   - Rotar service account keys periódicamente
   - Usar OIDC en lugar de keys (más seguro)
   - Auditar accesos regularmente

## 📝 Resumen de Comandos

```bash
# Deploy a PRE
git push origin develop

# Deploy a PROD  
git tag v1.0.0
git push origin v1.0.0

# Ver builds
# https://github.com/TU_USUARIO/nexusdocs360/actions

# Ver logs en GCP
gcloud run services logs read nexus-api-pre --project=nexusdocs360-pre
```

---

*Con GitHub Actions tienes control total sobre tu CI/CD directamente desde GitHub* 🎉