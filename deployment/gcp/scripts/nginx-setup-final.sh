#!/bin/bash
# Script completo de configuración de nginx con certificados SSL

set -e

echo "🚀 Configuración Completa de Nginx para NexusDocs360"
echo "=================================================="
echo ""

# Variables
EMAIL="admin@nexusdocs360.app"
DOMAIN="pre.nexusdocs360.app"
API_DOMAIN="pre-api.nexusdocs360.app"
FRONTEND_URL="https://nexus-frontend-pre-300252412370.europe-west1.run.app"
BACKEND_URL="https://nexus-backend-pre-300252412370.europe-west1.run.app"

# Paso 1: Instalar nginx y certbot si no están instalados
echo "1️⃣ Verificando instalación de nginx y certbot..."
if ! command -v nginx &> /dev/null; then
    echo "Instalando nginx..."
    sudo apt-get update
    sudo apt-get install -y nginx
fi

if ! command -v certbot &> /dev/null; then
    echo "Instalando certbot..."
    sudo apt-get install -y certbot python3-certbot-nginx
fi

# Paso 2: Crear directorio para validación de Let's Encrypt
echo ""
echo "2️⃣ Creando directorio para validación de certificados..."
sudo mkdir -p /var/www/certbot
sudo chown www-data:www-data /var/www/certbot

# Paso 3: Crear configuración inicial HTTP para obtener certificados
echo ""
echo "3️⃣ Creando configuración inicial HTTP para Let's Encrypt..."
sudo tee /etc/nginx/sites-available/nexusdocs360 > /dev/null <<EOF
# Configuración temporal para obtener certificados
server {
    listen 80;
    server_name ${DOMAIN} ${API_DOMAIN};
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 404;
    }
}
EOF

# Habilitar sitio y recargar nginx
echo ""
echo "4️⃣ Habilitando configuración temporal..."
sudo rm -f /etc/nginx/sites-enabled/default
sudo rm -f /etc/nginx/sites-enabled/*
sudo ln -sf /etc/nginx/sites-available/nexusdocs360 /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Paso 4: Obtener certificados SSL
echo ""
echo "5️⃣ Obteniendo certificados SSL de Let's Encrypt..."

if [ -d "/etc/letsencrypt/live/${DOMAIN}" ]; then
    echo "Los certificados ya existen. ¿Deseas renovarlos? (s/n)"
    read -r respuesta
    if [[ "$respuesta" == "s" || "$respuesta" == "S" ]]; then
        sudo certbot certonly --webroot \
            -w /var/www/certbot \
            -d ${DOMAIN} \
            -d ${API_DOMAIN} \
            --non-interactive \
            --agree-tos \
            --email ${EMAIL} \
            --force-renewal
    else
        echo "Usando certificados existentes..."
    fi
else
    sudo certbot certonly --webroot \
        -w /var/www/certbot \
        -d ${DOMAIN} \
        -d ${API_DOMAIN} \
        --non-interactive \
        --agree-tos \
        --email ${EMAIL}
fi

# Verificar que los certificados existen
if [ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]; then
    echo "❌ Error: No se pudieron obtener los certificados"
    exit 1
fi

echo "✅ Certificados obtenidos exitosamente"

# Paso 5: Crear configuración completa con HTTPS
echo ""
echo "6️⃣ Creando configuración completa con HTTPS..."
sudo tee /etc/nginx/sites-available/nexusdocs360 > /dev/null <<EOF
# Configuración para redirigir HTTP a HTTPS
server {
    listen 80;
    server_name ${DOMAIN} ${API_DOMAIN};
    return 301 https://\$server_name\$request_uri;
}

# Frontend
server {
    listen 443 ssl http2;
    server_name ${DOMAIN};

    # Certificados SSL
    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;

    # Configuración SSL moderna
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;

    # OCSP Stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    ssl_trusted_certificate /etc/letsencrypt/live/${DOMAIN}/chain.pem;

    # Configuración de sesión SSL
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;

    # Headers de seguridad
    add_header Strict-Transport-Security "max-age=63072000" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Logs
    access_log /var/log/nginx/${DOMAIN}.access.log;
    error_log /var/log/nginx/${DOMAIN}.error.log;

    # Tamaño máximo de carga
    client_max_body_size 10M;

    # Proxy al frontend
    location / {
        proxy_pass ${FRONTEND_URL};
        proxy_http_version 1.1;
        
        # Headers del proxy - IMPORTANTE: Cloud Run necesita el Host header correcto
        proxy_set_header Host nexus-frontend-pre-300252412370.europe-west1.run.app;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        
        # SSL para el backend
        proxy_ssl_server_name on;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Buffering
        proxy_buffering off;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
        proxy_busy_buffers_size 8k;
        
        # WebSocket support (si es necesario)
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# API Backend
server {
    listen 443 ssl http2;
    server_name ${API_DOMAIN};

    # Certificados SSL
    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;

    # Configuración SSL moderna
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;

    # OCSP Stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    ssl_trusted_certificate /etc/letsencrypt/live/${DOMAIN}/chain.pem;

    # Configuración de sesión SSL
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;

    # Headers de seguridad
    add_header Strict-Transport-Security "max-age=63072000" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # CORS headers (ajustar según necesidades)
    add_header Access-Control-Allow-Origin "https://${DOMAIN}" always;
    add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Origin, X-Requested-With, Content-Type, Accept, Authorization" always;
    add_header Access-Control-Allow-Credentials "true" always;

    # Logs
    access_log /var/log/nginx/${API_DOMAIN}.access.log;
    error_log /var/log/nginx/${API_DOMAIN}.error.log;

    # Tamaño máximo de carga para API
    client_max_body_size 50M;

    # Manejo de OPTIONS para CORS
    if (\$request_method = 'OPTIONS') {
        return 204;
    }

    # Proxy al backend
    location / {
        proxy_pass ${BACKEND_URL};
        proxy_http_version 1.1;
        
        # Headers del proxy - IMPORTANTE: Cloud Run necesita el Host header correcto
        proxy_set_header Host nexus-backend-pre-300252412370.europe-west1.run.app;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_set_header Authorization \$http_authorization;
        
        # SSL para el backend
        proxy_ssl_server_name on;
        
        # Timeouts (más largos para API)
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        
        # Buffering
        proxy_buffering off;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
        proxy_busy_buffers_size 8k;
        
        # Para APIs que usan streaming
        proxy_set_header Connection "";
        chunked_transfer_encoding on;
    }
}

# Configuración para renovación de certificados Let's Encrypt
server {
    listen 80;
    server_name ${DOMAIN} ${API_DOMAIN};
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}
EOF

# Paso 6: Probar configuración y recargar
echo ""
echo "7️⃣ Probando configuración final..."
if sudo nginx -t; then
    echo "✅ Configuración válida"
    sudo systemctl reload nginx
    echo "✅ Nginx recargado con éxito"
else
    echo "❌ Error en la configuración"
    exit 1
fi

# Paso 7: Configurar renovación automática
echo ""
echo "8️⃣ Configurando renovación automática de certificados..."
(crontab -l 2>/dev/null || true; echo "0 0,12 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'") | crontab -

# Paso 8: Verificar servicios
echo ""
echo "9️⃣ Verificando servicios..."
echo ""
echo "Frontend (https://${DOMAIN}):"
curl -s -o /dev/null -w "Status: %{http_code}\n" https://${DOMAIN}/

echo ""
echo "API (https://${API_DOMAIN}/health):"
curl -s https://${API_DOMAIN}/health || echo "No response"

echo ""
echo "✅ ¡Configuración completada exitosamente!"
echo ""
echo "Servicios disponibles en:"
echo "- Frontend: https://${DOMAIN}"
echo "- API: https://${API_DOMAIN}"
echo ""
echo "Los certificados se renovarán automáticamente cada 12 horas."