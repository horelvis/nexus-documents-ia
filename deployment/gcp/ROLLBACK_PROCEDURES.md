# 🔄 Procedimientos de Rollback - NexusDocs360

## 📋 Índice
1. [Visión General](#visión-general)
2. [Tipos de Rollback](#tipos-de-rollback)
3. [Rollback de Cloud Run](#rollback-de-cloud-run)
4. [Rollback de Base de Datos](#rollback-de-base-de-datos)
5. [Rollback Completo](#rollback-completo)
6. [Automatización](#automatización)

## 🎯 Visión General

Este documento describe los procedimientos para revertir cambios en caso de problemas en cualquier ambiente (PRE o PROD).

### Principios de Rollback
- **Velocidad**: Revertir rápidamente para minimizar impacto
- **Seguridad**: Verificar antes de ejecutar
- **Documentación**: Registrar causa y acciones tomadas
- **Comunicación**: Notificar a stakeholders

## 🔀 Tipos de Rollback

### 1. Rollback de Aplicación (más común)
- Revertir servicios Cloud Run a versión anterior
- No afecta base de datos
- Tiempo: 2-5 minutos

### 2. Rollback de Base de Datos
- Revertir migraciones de Alembic
- Puede requerir restauración de backup
- Tiempo: 15-30 minutos

### 3. Rollback Completo
- Revertir aplicación + base de datos
- Escenario más complejo
- Tiempo: 30-60 minutos

## 🚀 Rollback de Cloud Run

### Identificar Versión Estable
```bash
# Configurar proyecto (PRE o PROD)
PROJECT_ID="nexusdocs360-pre"  # o nexusdocs360-prod
gcloud config set project $PROJECT_ID

# Listar revisiones de cada servicio
gcloud run revisions list --service=nexus-api --region=europe-west1
gcloud run revisions list --service=nexus-frontend --region=europe-west1
gcloud run revisions list --service=nexus-storage --region=europe-west1
gcloud run revisions list --service=nexus-langchain --region=europe-west1
```

### Rollback Rápido (Un Servicio)
```bash
# Revertir API a revisión anterior
gcloud run services update-traffic nexus-api \
  --region=europe-west1 \
  --to-revisions=nexus-api-00042-abc=100

# Revertir Frontend
gcloud run services update-traffic nexus-frontend \
  --region=europe-west1 \
  --to-revisions=nexus-frontend-00041-xyz=100
```

### Rollback Coordinado (Todos los Servicios)
```bash
#!/bin/bash
# Script: emergency-rollback.sh

REGION="europe-west1"
API_REVISION="nexus-api-00042-abc"
FRONTEND_REVISION="nexus-frontend-00041-xyz"
STORAGE_REVISION="nexus-storage-00040-def"
LANGCHAIN_REVISION="nexus-langchain-00039-ghi"

echo "🔄 Iniciando rollback de emergencia..."

# Rollback de servicios
gcloud run services update-traffic nexus-api \
  --region=$REGION --to-revisions=$API_REVISION=100

gcloud run services update-traffic nexus-frontend \
  --region=$REGION --to-revisions=$FRONTEND_REVISION=100

gcloud run services update-traffic nexus-storage \
  --region=$REGION --to-revisions=$STORAGE_REVISION=100

gcloud run services update-traffic nexus-langchain \
  --region=$REGION --to-revisions=$LANGCHAIN_REVISION=100

echo "✅ Rollback completado"
```

## 🗄️ Rollback de Base de Datos

### Verificar Estado Actual
```bash
# Conectar a la base de datos
gcloud sql connect nexus-db-instance --user=postgres --database=nexusdb

# En psql, verificar versión de Alembic
SELECT * FROM alembic_version;
```

### Revertir Migración
```bash
# Obtener la imagen de la API con Alembic
docker pull gcr.io/$PROJECT_ID/nexus-api:stable

# Ejecutar rollback
docker run --rm \
  -e DATABASE_URL="postgresql://user:pass@host/db" \
  gcr.io/$PROJECT_ID/nexus-api:stable \
  alembic downgrade -1
```

### Restaurar desde Backup
```bash
# Listar backups disponibles
gcloud sql backups list --instance=nexus-db-instance

# Restaurar backup específico
gcloud sql backups restore BACKUP_ID \
  --restore-instance=nexus-db-instance \
  --backup-instance=nexus-db-instance
```

## 🔧 Rollback Completo

### Paso 1: Detener Tráfico
```bash
# Configurar servicio en modo mantenimiento
gcloud run services update nexus-frontend \
  --region=europe-west1 \
  --set-env-vars=MAINTENANCE_MODE=true
```

### Paso 2: Rollback de Base de Datos
```bash
# Seguir procedimiento de rollback de BD
# Ver sección anterior
```

### Paso 3: Rollback de Servicios
```bash
# Ejecutar script de rollback coordinado
./emergency-rollback.sh
```

### Paso 4: Verificación
```bash
# Verificar salud de servicios
curl https://api.nexusdocs360.com/health
curl https://app.nexusdocs360.com

# Verificar logs
gcloud logging read "resource.type=cloud_run_revision" \
  --limit=50 --format=json
```

### Paso 5: Reactivar Tráfico
```bash
# Quitar modo mantenimiento
gcloud run services update nexus-frontend \
  --region=europe-west1 \
  --remove-env-vars=MAINTENANCE_MODE
```

## 🤖 Automatización

### Trigger de Rollback Automático
```yaml
# cloudbuild-rollback.yaml
steps:
  - name: 'gcr.io/cloud-builders/gcloud'
    id: 'rollback-services'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        # Obtener última versión estable conocida
        STABLE_TAG=$(gcloud container images list-tags \
          gcr.io/${PROJECT_ID}/nexus-api \
          --filter="tags:stable" \
          --format="get(tags[0])")
        
        # Rollback todos los servicios
        gcloud run deploy nexus-api \
          --image=gcr.io/${PROJECT_ID}/nexus-api:${STABLE_TAG} \
          --region=${_REGION}
        
        # Repetir para otros servicios...
```

### Monitoreo de Rollback
```bash
# Configurar alerta para rollback automático
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="High Error Rate - Auto Rollback" \
  --condition-display-name="Error rate > 10%" \
  --condition-expression='
    resource.type="cloud_run_revision" AND
    metric.type="run.googleapis.com/request_count" AND
    metric.label.response_code_class="5xx"
  '
```

## 📊 Checklist Post-Rollback

- [ ] Servicios respondiendo correctamente
- [ ] Base de datos consistente
- [ ] Logs sin errores críticos
- [ ] Métricas de performance normales
- [ ] Usuarios pueden autenticarse
- [ ] Funciones core operativas
- [ ] Notificar equipo del rollback
- [ ] Documentar causa raíz
- [ ] Planificar fix permanente

## 🚨 Contactos de Emergencia

### Equipo DevOps
- On-call: +34 XXX XXX XXX
- Email: devops@nexusdocs360.com
- Slack: #emergency-response

### Escalación
1. DevOps Engineer de guardia
2. Lead DevOps
3. CTO

## 📝 Template de Reporte

```markdown
## Reporte de Rollback

**Fecha/Hora**: YYYY-MM-DD HH:MM UTC
**Ambiente**: PRE/PROD
**Servicios Afectados**: 
**Duración del Incidente**: 
**Impacto en Usuarios**: 

### Causa Raíz
[Descripción del problema]

### Acciones Tomadas
1. [Acción 1]
2. [Acción 2]

### Resolución
[Cómo se resolvió]

### Lecciones Aprendidas
[Qué mejorar]
```