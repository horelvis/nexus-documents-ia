# 🚀 Quick Start - Despliegue Rápido NexusDocs360

Esta guía te permite desplegar rápidamente en 30 minutos.

## 📋 Pre-requisitos Rápidos

```bash
# Verificar herramientas
gcloud --version  # Debe estar instalado
docker --version  # Debe estar instalado
```

## 🏃‍♂️ Despliegue Express PRE (15 minutos)

### 1. Setup Inicial (5 min)

```bash
# Clonar y configurar
git clone https://github.com/nexusdocs360/nexusdocs360.git
cd nexusdocs360/deployment/gcp

# Login GCP
gcloud auth login
gcloud auth application-default login

# Crear proyecto PRE
gcloud projects create nexusdocs360-pre --name="NexusDocs360 PRE"
gcloud config set project nexusdocs360-pre

# Asociar billing (reemplaza BILLING_ID)
gcloud beta billing projects link nexusdocs360-pre \
  --billing-account=XXXXXX-XXXXXX-XXXXXX
```

### 2. Configuración Rápida (2 min)

```bash
# Copiar configuración
cp .env.pre .env

# Habilitar APIs
./scripts/enable-apis.sh

# Setup secrets básicos
./scripts/setup-secrets-pre.sh
```

### 3. Actualizar Secrets Críticos (3 min)

```bash
# Solo los mínimos necesarios para empezar
echo -n "sk-..." | gcloud secrets versions add openai-api-key-pre --data-file=-
echo -n "sk_test_..." | gcloud secrets versions add clerk-secret-pre --data-file=-
echo -n "pk_test_..." | gcloud secrets versions add clerk-publishable-key-pre --data-file=-
```

### 4. Desplegar Infraestructura (5 min)

```bash
# Un comando para todo
./deploy-infrastructure.sh pre
```

### 5. Obtener IP y Configurar DNS

```bash
# Obtener IP
NGINX_IP=$(gcloud compute addresses describe nexus-nginx-ip-pre \
  --region=europe-west1 --format="value(address)")
echo "IP para DNS: $NGINX_IP"

# Agregar en tu proveedor DNS:
# pre.nexusdocs360.com → [NGINX_IP]
# pre-app.nexusdocs360.com → [NGINX_IP]
# pre-api.nexusdocs360.com → [NGINX_IP]
```

### 6. Configurar CI/CD con GitHub

```bash
# Conectar GitHub (hazlo desde la consola web)
echo "Ir a: https://console.cloud.google.com/cloud-build/triggers/connect"
echo "Conectar tu repositorio GitHub"

# Configurar triggers
./setup-triggers.sh tu-usuario/nexusdocs360 pre
```

### 7. Primer Deploy Automático

```bash
# Push a develop activa el deploy
git checkout develop
git push origin develop

# Ver progreso del build
echo "https://console.cloud.google.com/cloud-build/builds?project=nexusdocs360-pre"
```

### 8. Verificar

```bash
# Esperar 5 minutos para DNS y certificados
sleep 300

# Verificar
curl https://pre-app.nexusdocs360.com/health
curl https://pre-api.nexusdocs360.com/health
```

## ✅ Checklist Rápido PRE

- [ ] Proyecto creado y billing asociado
- [ ] APIs habilitadas
- [ ] Secrets configurados (mínimo: OpenAI, Clerk)
- [ ] Infraestructura desplegada
- [ ] DNS configurado con IP de Nginx
- [ ] Aplicaciones desplegadas
- [ ] Health checks respondiendo

## 🚨 Troubleshooting Rápido

### Error: APIs no habilitadas
```bash
./scripts/enable-apis.sh
```

### Error: Secrets no encontrados
```bash
# Verificar secrets
gcloud secrets list

# Crear el que falta
echo -n "valor" | gcloud secrets versions add nombre-secret --data-file=-
```

### Error: DNS no resuelve
```bash
# Verificar propagación (puede tardar 5-30 min)
nslookup pre-app.nexusdocs360.com 8.8.8.8
```

### Error: Certificados SSL
```bash
# SSH a Nginx y revisar
gcloud compute ssh nginx-proxy-pre --zone=europe-west1-b
sudo certbot renew --nginx
```

## 📊 Monitoreo Básico

```bash
# Ver logs
gcloud logging read "severity>=ERROR" --limit=50

# Ver servicios
gcloud run services list --region=europe-west1

# Dashboard
echo "https://console.cloud.google.com/monitoring?project=nexusdocs360-pre"
```

## 🎯 Siguiente Paso: PROD

Una vez PRE funcione correctamente:

1. Probar todas las funcionalidades en PRE
2. Configurar triggers para PROD:
   ```bash
   ./setup-triggers.sh tu-usuario/nexusdocs360 prod
   ```
3. Deploy con tag:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

## 💡 Tips para Acelerar

1. **Paralelizar**: Mientras se crea infraestructura, actualiza DNS
2. **Minimal Secrets**: Solo configura los esenciales al inicio
3. **Skip Monitoring**: Configúralo después si tienes prisa
4. **Use Defaults**: No cambies configuraciones a menos que sea necesario

---

**¿Problemas?** Revisa `DEPLOYMENT_STEP_BY_STEP.md` para detalles completos.