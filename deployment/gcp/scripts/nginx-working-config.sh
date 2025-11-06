#!/bin/bash
# Aplicar la configuración de nginx que sabemos que funciona

set -e

echo "🔧 Aplicando configuración de nginx que funciona"
echo "=============================================="
echo ""

# Verificar que existen los certificados
echo "1️⃣ Verificando certificados SSL..."
if [ ! -d "/etc/letsencrypt/live/pre.nexusdocs360.app" ]; then
    echo "❌ No se encontraron certificados SSL"
    echo "Ejecuta primero el script de instalación de certificados"
    exit 1
fi
echo "✅ Certificados encontrados"

# Crear la configuración que funcionaba anteriormente
echo ""
echo "2️⃣ Creando configuración nginx..."
sudo tee /etc/nginx/sites-available/nexusdocs360 > /dev/null <<'EOF'
# HTTP to HTTPS redirect
server {
    listen 80;
    server_name pre.nexusdocs360.app pre-api.nexusdocs360.app;
    return 301 https://$host$request_uri;
}

# Frontend HTTPS
server {
    listen 443 ssl http2;
    server_name pre.nexusdocs360.app;

    ssl_certificate /etc/letsencrypt/live/pre.nexusdocs360.app/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pre.nexusdocs360.app/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass https://nexus-frontend-pre-300252412370.europe-west1.run.app;
        proxy_http_version 1.1;
        proxy_set_header Host nexus-frontend-pre-300252412370.europe-west1.run.app;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_ssl_server_name on;
    }
}

# API HTTPS
server {
    listen 443 ssl http2;
    server_name pre-api.nexusdocs360.app;

    ssl_certificate /etc/letsencrypt/live/pre.nexusdocs360.app/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pre.nexusdocs360.app/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass https://nexus-backend-pre-300252412370.europe-west1.run.app;
        proxy_http_version 1.1;
        proxy_set_header Host nexus-backend-pre-300252412370.europe-west1.run.app;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Authorization $http_authorization;
        proxy_ssl_server_name on;
        proxy_buffering off;
        client_max_body_size 100M;
    }
}
EOF

# Habilitar el sitio
echo ""
echo "3️⃣ Habilitando el sitio..."
sudo rm -f /etc/nginx/sites-enabled/*
sudo ln -sf /etc/nginx/sites-available/nexusdocs360 /etc/nginx/sites-enabled/

# Probar la configuración
echo ""
echo "4️⃣ Probando configuración..."
if sudo nginx -t; then
    echo "✅ Configuración válida"
else
    echo "❌ Error en la configuración"
    exit 1
fi

# Recargar nginx
echo ""
echo "5️⃣ Recargando nginx..."
sudo systemctl reload nginx

# Verificar que nginx está funcionando
echo ""
echo "6️⃣ Estado de nginx..."
sudo systemctl status nginx --no-pager | grep "Active:"

# Probar las URLs directamente
echo ""
echo "7️⃣ Probando acceso directo a Cloud Run..."
echo ""
echo "Backend directo:"
curl -s -o /dev/null -w "Status: %{http_code}\n" https://nexus-backend-pre-300252412370.europe-west1.run.app/health

echo ""
echo "Frontend directo:"
curl -s -o /dev/null -w "Status: %{http_code}\n" https://nexus-frontend-pre-300252412370.europe-west1.run.app/

# Probar a través de nginx
echo ""
echo "8️⃣ Probando a través de nginx..."
echo ""
echo "API Health:"
response=$(curl -s -w "\n[Status: %{http_code}]" https://pre-api.nexusdocs360.app/health)
echo "$response"

echo ""
echo "Frontend:"
curl -s -o /dev/null -w "Status: %{http_code}\n" https://pre.nexusdocs360.app/

# Verificar logs
echo ""
echo "9️⃣ Últimos errores en logs de nginx:"
sudo tail -5 /var/log/nginx/error.log 2>/dev/null || echo "No hay errores recientes"

echo ""
echo "✅ Configuración aplicada"
echo ""
echo "Si sigue sin funcionar, verifica:"
echo "1. Que los servicios de Cloud Run estén activos"
echo "2. Que el firewall permita tráfico HTTPS (puerto 443)"
echo "3. Que los DNS apunten a la IP correcta del servidor nginx"