# 🔄 Procedimientos de Rollback - NexusDocs360 PRE

## 🚨 Cuándo Hacer Rollback

### Criterios Críticos (Rollback Inmediato)
- ❌ Error rate > 10% sostenido por 5 minutos
- ❌ Servicios core no responden (API, Frontend)
- ❌ Pérdida de datos o corrupción de DB
- ❌ Vulnerabilidad de seguridad crítica
- ❌ Loop de reinicios en servicios

### Criterios No-Críticos (Evaluar)
- ⚠️ Performance degradado pero funcional
- ⚠️ Features específicas con errores
- ⚠️ Problemas cosméticos en UI
- ⚠️ Servicios secundarios con intermitencias

## 📋 Preparación Pre-Rollback

```bash
# 1. Notificar al equipo
echo "🚨 INICIANDO ROLLBACK PRE - $(date)" | \
  curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"🚨 ROLLBACK INICIADO EN PRE"}' \
  $SLACK_WEBHOOK_URL

# 2. Capturar estado actual
gcloud logging read "resource.type=cloud_run_revision AND timestamp>=\"$(date -u -d '1 hour ago' '+%Y-%m-%dT%H:%M:%S')\"" \
  --format=json > rollback_logs_$(date +%Y%m%d_%H%M%S).json

# 3. Identificar versiones actuales
for service in api frontend langchain langroid storage; do
  echo "=== $service ==="
  gcloud run services describe nexus-${service}-pre \
    --region=${GCP_REGION} \
    --format="value(spec.template.metadata.name)"
done > current_versions.txt
```

## 🔄 Procedimiento de Rollback Rápido

### Opción 1: Rollback de Tráfico (Más Rápido)

```bash
#!/bin/bash
# rollback-traffic-pre.sh

set -e
REGION="europe-west1"
PROJECT_ID="nexusdocs360-pre"

echo "🔄 Iniciando rollback de tráfico..."

# 1. API Backend
PREVIOUS_API=$(gcloud run revisions list \
  --service=nexus-api-pre \
  --region=$REGION \
  --format="value(name)" \
  --limit=2 | tail -1)

gcloud run services update-traffic nexus-api-pre \
  --to-revisions=$PREVIOUS_API=100 \
  --region=$REGION

# 2. Frontend
PREVIOUS_FRONTEND=$(gcloud run revisions list \
  --service=nexus-frontend-pre \
  --region=$REGION \
  --format="value(name)" \
  --limit=2 | tail -1)

gcloud run services update-traffic nexus-frontend-pre \
  --to-revisions=$PREVIOUS_FRONTEND=100 \
  --region=$REGION

# 3. Microservicios
for service in langchain langroid storage; do
  PREVIOUS=$(gcloud run revisions list \
    --service=nexus-${service}-pre \
    --region=$REGION \
    --format="value(name)" \
    --limit=2 | tail -1)
  
  gcloud run services update-traffic nexus-${service}-pre \
    --to-revisions=$PREVIOUS=100 \
    --region=$REGION
done

echo "✅ Rollback de tráfico completado"
```

### Opción 2: Rollback por Tags (Con Imágenes)

```bash
#!/bin/bash
# rollback-images-pre.sh

set -e
REGION="europe-west1"
PROJECT_ID="nexusdocs360-pre"
ROLLBACK_TAG="v1.0.0-pre-stable"  # Tag estable conocido

echo "🔄 Iniciando rollback a tag: $ROLLBACK_TAG"

# Función para rollback de servicio
rollback_service() {
  local SERVICE=$1
  local IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/nexusdocs360-pre/${SERVICE}:${ROLLBACK_TAG}"
  
  echo "Rolling back $SERVICE to $ROLLBACK_TAG..."
  
  gcloud run deploy nexus-${SERVICE}-pre \
    --image=$IMAGE \
    --region=$REGION \
    --platform=managed
}

# Rollback de todos los servicios
rollback_service "api"
rollback_service "frontend"
rollback_service "langchain"
rollback_service "langroid"
rollback_service "storage"

echo "✅ Rollback por imágenes completado"
```

## 🗄️ Rollback de Base de Datos

### Identificar Punto de Restauración

```bash
# Listar backups disponibles
gcloud sql backups list --instance=nexus-db-pre \
  --format="table(id,windowStartTime,status)"

# Obtener detalles de un backup específico
gcloud sql backups describe BACKUP_ID \
  --instance=nexus-db-pre
```

### Procedimiento de Restauración

```bash
#!/bin/bash
# rollback-database-pre.sh

set -e
INSTANCE="nexus-db-pre"
BACKUP_ID="$1"  # Pasar como parámetro

if [ -z "$BACKUP_ID" ]; then
  echo "❌ Error: Especifica BACKUP_ID"
  echo "Uso: ./rollback-database-pre.sh BACKUP_ID"
  exit 1
fi

echo "⚠️  ADVERTENCIA: Esto restaurará la base de datos al estado del backup"
read -p "¿Continuar? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
  echo "Rollback cancelado"
  exit 0
fi

# 1. Detener servicios que escriben a DB
echo "🛑 Deteniendo servicios..."
gcloud run services update nexus-api-pre \
  --region=europe-west1 \
  --min-instances=0 \
  --max-instances=0

# 2. Crear backup actual antes de restaurar
echo "💾 Creando backup de seguridad actual..."
gcloud sql backups create \
  --instance=$INSTANCE \
  --description="Pre-rollback backup $(date +%Y%m%d_%H%M%S)"

# 3. Restaurar desde backup
echo "🔄 Restaurando desde backup $BACKUP_ID..."
gcloud sql backups restore $BACKUP_ID \
  --restore-instance=$INSTANCE \
  --quiet

# 4. Reiniciar servicios
echo "▶️ Reiniciando servicios..."
gcloud run services update nexus-api-pre \
  --region=europe-west1 \
  --min-instances=1 \
  --max-instances=2

echo "✅ Restauración de DB completada"
```

## 🔄 Rollback de Configuración

### Secrets y Variables de Entorno

```bash
#!/bin/bash
# rollback-config-pre.sh

# Restaurar versión anterior de secrets
restore_secret() {
  local SECRET_NAME=$1
  local VERSION=${2:-2}  # Por defecto, versión anterior
  
  echo "Restaurando $SECRET_NAME a versión $VERSION..."
  
  # Obtener valor de versión anterior
  VALUE=$(gcloud secrets versions access $VERSION --secret=$SECRET_NAME)
  
  # Crear nueva versión con valor anterior
  echo -n "$VALUE" | gcloud secrets versions add $SECRET_NAME --data-file=-
}

# Restaurar secrets críticos
restore_secret "feature-flags-pre"
restore_secret "microservices-api-key-pre"

# Forzar re-deploy para aplicar cambios
gcloud run services update nexus-api-pre \
  --region=europe-west1 \
  --update-env-vars="FORCE_REFRESH=$(date +%s)"
```

## 📊 Validación Post-Rollback

### Script de Validación Automática

```bash
#!/bin/bash
# validate-rollback-pre.sh

set -e
REGION="europe-west1"
FAILED=0

echo "🔍 Validando rollback..."

# 1. Verificar servicios running
echo "Checking service status..."
for service in api frontend langchain langroid storage; do
  STATUS=$(gcloud run services describe nexus-${service}-pre \
    --region=$REGION \
    --format="value(status.conditions[0].status)")
  
  if [ "$STATUS" != "True" ]; then
    echo "❌ $service is not healthy"
    FAILED=$((FAILED + 1))
  else
    echo "✅ $service is running"
  fi
done

# 2. Health checks
echo -e "\nChecking health endpoints..."
API_URL="https://pre-api.nexusdocs360.com"
FRONTEND_URL="https://pre-app.nexusdocs360.com"

if ! curl -sf "$API_URL/health" > /dev/null; then
  echo "❌ API health check failed"
  FAILED=$((FAILED + 1))
else
  echo "✅ API is healthy"
fi

if ! curl -sf "$FRONTEND_URL" > /dev/null; then
  echo "❌ Frontend health check failed"
  FAILED=$((FAILED + 1))
else
  echo "✅ Frontend is accessible"
fi

# 3. Database connectivity
echo -e "\nChecking database..."
gcloud run jobs execute nexus-db-check-pre \
  --region=$REGION \
  --wait \
  --format="value(status.executionCount)" || {
    echo "❌ Database check failed"
    FAILED=$((FAILED + 1))
  }

# 4. Resumen
echo -e "\n📊 Resumen de Validación:"
if [ $FAILED -eq 0 ]; then
  echo "✅ Rollback exitoso - Todos los servicios operativos"
  
  # Notificar éxito
  curl -X POST -H 'Content-type: application/json' \
    --data '{"text":"✅ Rollback PRE completado exitosamente"}' \
    $SLACK_WEBHOOK_URL
else
  echo "❌ Rollback con problemas - $FAILED servicios con errores"
  
  # Notificar problemas
  curl -X POST -H 'Content-type: application/json' \
    --data "{\"text\":\"⚠️ Rollback PRE completado con $FAILED errores\"}" \
    $SLACK_WEBHOOK_URL
fi

exit $FAILED
```

## 🚑 Rollback de Emergencia

Para situaciones críticas donde los procedimientos normales fallan:

```bash
#!/bin/bash
# emergency-rollback-pre.sh

# 1. Detener TODO el tráfico
gcloud compute forwarding-rules delete nexus-nginx-pre --region=europe-west1 --quiet

# 2. Escalar a 0 todos los servicios
for service in api frontend langchain langroid storage; do
  gcloud run services update nexus-${service}-pre \
    --region=europe-west1 \
    --max-instances=0 &
done
wait

# 3. Restaurar desde terraform state (si disponible)
cd terraform/pre
terraform workspace select pre
terraform apply -target=module.cloud_run -auto-approve

# 4. O desplegar versión estable conocida manualmente
STABLE_TAG="v0.9.0-pre"
for service in api frontend langchain langroid storage; do
  gcloud run deploy nexus-${service}-pre \
    --image=europe-west1-docker.pkg.dev/nexusdocs360-pre/nexusdocs360-pre/${service}:${STABLE_TAG} \
    --region=europe-west1 &
done
wait
```

## 📝 Documentación Post-Rollback

### Template de Reporte

```markdown
# Reporte de Rollback - PRE Environment

**Fecha**: [FECHA]
**Hora Inicio**: [HORA]
**Hora Fin**: [HORA]
**Duración Total**: [MINUTOS]

## Razón del Rollback
- [ ] Error crítico en: [COMPONENTE]
- [ ] Performance degradado
- [ ] Falla de seguridad
- [ ] Otro: [DESCRIPCIÓN]

## Acciones Tomadas
1. [ACCIÓN 1]
2. [ACCIÓN 2]
3. [...]

## Servicios Afectados
- [ ] Frontend
- [ ] API Backend
- [ ] Base de Datos
- [ ] Microservicios IA
- [ ] Otros: [...]

## Impacto
- Usuarios afectados: [NÚMERO]
- Downtime: [MINUTOS]
- Datos perdidos: [SI/NO]

## Lecciones Aprendidas
- [LECCIÓN 1]
- [LECCIÓN 2]

## Acciones de Seguimiento
- [ ] [ACCIÓN 1] - Responsable: [NOMBRE]
- [ ] [ACCIÓN 2] - Responsable: [NOMBRE]

**Firmado por**: [NOMBRE]
**Rol**: [ROL]
```

## 🔒 Mejores Prácticas

1. **Siempre** hacer backup antes de rollback
2. **Notificar** al equipo inmediatamente
3. **Documentar** cada paso tomado
4. **Validar** después de cada cambio
5. **No hacer rollback parcial** sin coordinación
6. **Mantener** versiones estables taggeadas
7. **Practicar** rollbacks en horarios planificados

---

*Última actualización: [FECHA]*
*Contacto de emergencia: devops@nexusdocs360.com*