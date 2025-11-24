# 📚 Guía Completa de Despliegue - NexusDocs360

## 🎯 Configuración de Dominios

### Paso 1: Configurar Variables de Entorno

1. **Copiar archivo de configuración**:
```bash
cd deployment/gcp
cp .env.prod .env
```

2. **Editar el archivo `.env`**:
```bash
# Configuración de dominio
DOMAIN=tudominio.com              # Tu dominio principal
APP_SUBDOMAIN=app                 # Subdominio para la aplicación
API_SUBDOMAIN=api                 # Subdominio para la API
WWW_SUBDOMAIN=www                 # Subdominio www
SSL_EMAIL=admin@tudominio.com     # Email para Let's Encrypt

# Configuración GCP
GCP_PROJECT_ID=tu-proyecto-id     # ID de tu proyecto en GCP
GCP_REGION=europe-west1           # Región de despliegue
GCP_ZONE=europe-west1-b           # Zona específica
```

### Paso 2: URLs Generadas

Con la configuración anterior, el sistema generará automáticamente:
- **Frontend**: `https://app.tudominio.com`
- **API**: `https://api.tudominio.com`
- **Principal**: `https://tudominio.com`
- **WWW**: `https://www.tudominio.com` → redirige a app

## 🚀 Despliegue Rápido

### Flujo de tags para PRE

Para los despliegues del entorno PRE seguimos SemVer con sufijo `-pre.N` y utilizamos tags anotados. Así queda trazabilidad del build y los workflows `deploy-backend-pre` y `deploy-frontend-pre` se disparan automáticamente tanto con pushes a la rama `pre` como cuando llega un tag `v*.*.*-pre.*`.

1. Asegura que `develp-new` contenga los cambios aprobados para PRE y posiciona el HEAD en ese commit.
2. Crea el tag anotado con la versión correspondiente:
   ```bash
   git tag -a v1.4.0-pre.3 -m "PRE env release 1.4.0 pre.3"
   ```
3. Publica el tag para iniciar los despliegues:
   ```bash
   git push origin v1.4.0-pre.3
   ```
4. Supervisa las ejecuciones `Deploy Backend to PRE Environment` y `Deploy Frontend to PRE Environment` en GitHub Actions. Una vez que la versión esté validada en PRE, reutiliza la misma numeración sin el sufijo (`v1.4.0`) para Producción.

### Opción A: Script Automático (Recomendado)
```bash
# Desde la raíz del proyecto
./deploy-to-gcp.sh
```

### Opción B: Paso a Paso

1. **Cargar configuración**:
```bash
cd deployment/gcp
source load-env.sh
```

2. **Configurar secrets**:
```bash
./setup-secrets.sh
```

3. **Desplegar infraestructura**:
```bash
./deploy-infrastructure.sh
```

4. **Desplegar aplicaciones**:
```bash
cd ../..
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=_DOMAIN=$DOMAIN,_APP_SUBDOMAIN=$APP_SUBDOMAIN,_API_SUBDOMAIN=$API_SUBDOMAIN
```

## 🔧 Personalización de Dominios

### Cambiar Subdominios

Si necesitas usar subdominios diferentes:

```bash
# En .env
DOMAIN=empresa.com
APP_SUBDOMAIN=panel          # panel.empresa.com
API_SUBDOMAIN=backend        # backend.empresa.com
WWW_SUBDOMAIN=www            # www.empresa.com
```

### Múltiples Dominios

Para soportar múltiples dominios, edita `nginx/conf.d/default.conf`:

```nginx
server_name ${DOMAIN} *.${DOMAIN} otrodominio.com *.otrodominio.com;
```

### Dominio para Staging

Para ambiente de staging:

```bash
# .env.staging
DOMAIN=staging.tudominio.com
SSL_STAGING=true  # Usa certificados de prueba
```

## 📝 Configuración DNS

### Registros Necesarios

Configura estos registros DNS en tu proveedor:

| Tipo | Nombre | Valor | TTL |
|------|--------|-------|-----|
| A | @ | IP_DEL_NGINX | 300 |
| A | * | IP_DEL_NGINX | 300 |
| A | app | IP_DEL_NGINX | 300 |
| A | api | IP_DEL_NGINX | 300 |
| A | www | IP_DEL_NGINX | 300 |

### Obtener IP del Nginx
```bash
gcloud compute addresses describe nexus-nginx-ip \
  --region=$GCP_REGION \
  --format="value(address)"
```

## 🔒 SSL/TLS

### Generación Automática

El sistema genera automáticamente certificados SSL:
1. Nginx inicia con certificado temporal
2. Detecta propagación DNS
3. Solicita certificado a Let's Encrypt
4. Recarga con certificado válido

### Forzar Renovación
```bash
./deployment/gcp/manage-nginx.sh renew
```

### Verificar Estado SSL
```bash
./deployment/gcp/manage-nginx.sh status
```

## 🛠️ Gestión Post-Despliegue

### Comandos Útiles

```bash
# Ver logs del Nginx
./deployment/gcp/manage-nginx.sh logs

# Recargar configuración
./deployment/gcp/manage-nginx.sh reload

# SSH al servidor Nginx
./deployment/gcp/manage-nginx.sh ssh

# Reiniciar servicios
./deployment/gcp/manage-nginx.sh restart
```

### Actualizar Dominio

Si necesitas cambiar el dominio después del despliegue:

1. **Actualizar `.env`**:
```bash
cd deployment/gcp
nano .env  # Cambiar DOMAIN
source load-env.sh
```

2. **Actualizar Nginx VM**:
```bash
# SSH al servidor
./manage-nginx.sh ssh

# Dentro del servidor
cd /opt/nexus
export DOMAIN=nuevodominio.com
docker-compose down
docker-compose up -d
```

3. **Actualizar DNS** con la nueva configuración

## 🚨 Troubleshooting

### Problema: SSL no se genera
```bash
# Verificar logs de Certbot
./manage-nginx.sh ssh
docker logs nexus-certbot

# Forzar renovación
docker-compose run --rm certbot renew --force-renewal
```

### Problema: Dominio no resuelve
```bash
# Verificar propagación DNS
nslookup app.tudominio.com
dig app.tudominio.com

# Verificar configuración Nginx
./manage-nginx.sh ssh
docker exec nexus-nginx nginx -t
```

### Problema: CORS errors
Verificar que las variables de entorno coincidan:
- Frontend debe apuntar a: `https://${API_SUBDOMAIN}.${DOMAIN}`
- API debe permitir origen: `https://${APP_SUBDOMAIN}.${DOMAIN}`

## 📋 Checklist de Verificación

- [ ] Archivo `.env` configurado con tu dominio
- [ ] DNS apuntando a IP del Nginx
- [ ] Certificados SSL generados
- [ ] Frontend accesible en `https://app.tudominio.com`
- [ ] API accesible en `https://api.tudominio.com/docs`
- [ ] Redirección de HTTP a HTTPS funcionando
- [ ] CORS configurado correctamente
