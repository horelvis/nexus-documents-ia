#!/bin/bash
# Setup nginx with SSL certificates

set -e

echo "🔧 Setting up Nginx with SSL"
echo "==========================="
echo ""

# Configuration
DOMAIN="nexusdocs360.app"
EMAIL="admin@nexusdocs360.app"
FRONTEND_URL="https://nexus-frontend-pre-300252412370.europe-west1.run.app"
BACKEND_URL="https://nexus-backend-pre-300252412370.europe-west1.run.app"

# First, create HTTP configurations for certbot
echo "1️⃣ Creating initial HTTP configurations..."

# Frontend HTTP config
sudo tee /etc/nginx/sites-available/pre.${DOMAIN} > /dev/null <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name pre.${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://\$server_name\$request_uri;
    }
}
EOF

# API HTTP config
sudo tee /etc/nginx/sites-available/pre-api.${DOMAIN} > /dev/null <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name pre-api.${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://\$server_name\$request_uri;
    }
}
EOF

# Enable sites
echo ""
echo "2️⃣ Enabling sites..."
sudo ln -sf /etc/nginx/sites-available/pre.${DOMAIN} /etc/nginx/sites-enabled/
sudo ln -sf /etc/nginx/sites-available/pre-api.${DOMAIN} /etc/nginx/sites-enabled/

# Remove old configuration
sudo rm -f /etc/nginx/sites-enabled/nexusdocs360-pre

# Test and reload
sudo nginx -t
sudo systemctl reload nginx

# Get SSL certificates
echo ""
echo "3️⃣ Obtaining SSL certificates..."
sudo certbot certonly --nginx \
    -d pre.${DOMAIN} \
    -d pre-api.${DOMAIN} \
    --non-interactive \
    --agree-tos \
    --email $EMAIL \
    --keep-until-expiring

# Now create full HTTPS configurations
echo ""
echo "4️⃣ Creating HTTPS configurations..."

# Frontend HTTPS config
sudo tee /etc/nginx/sites-available/pre.${DOMAIN} > /dev/null <<EOF
# Redirect HTTP to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name pre.${DOMAIN};
    return 301 https://\$server_name\$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name pre.${DOMAIN};

    ssl_certificate /etc/letsencrypt/live/pre.${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pre.${DOMAIN}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # Proxy to Cloud Run
    location / {
        proxy_pass ${FRONTEND_URL};
        proxy_http_version 1.1;
        proxy_set_header Host pre.${DOMAIN};
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Disable IPv6 upstream
        resolver 8.8.8.8 8.8.4.4 valid=300s;
        resolver_timeout 5s;
    }
}
EOF

# API HTTPS config
sudo tee /etc/nginx/sites-available/pre-api.${DOMAIN} > /dev/null <<EOF
# Redirect HTTP to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name pre-api.${DOMAIN};
    return 301 https://\$server_name\$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name pre-api.${DOMAIN};

    ssl_certificate /etc/letsencrypt/live/pre-api.${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pre-api.${DOMAIN}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # Proxy to Cloud Run
    location / {
        proxy_pass ${BACKEND_URL};
        proxy_http_version 1.1;
        proxy_set_header Host pre-api.${DOMAIN};
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Authorization \$http_authorization;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Disable IPv6 upstream
        resolver 8.8.8.8 8.8.4.4 valid=300s;
        resolver_timeout 5s;
        
        # CORS headers
        add_header 'Access-Control-Allow-Origin' 'https://pre.${DOMAIN}' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type, X-Requested-With' always;
        add_header 'Access-Control-Allow-Credentials' 'true' always;
        
        if (\$request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' 'https://pre.${DOMAIN}' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type, X-Requested-With' always;
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
        }
    }
}
EOF

# Test and reload
echo ""
echo "5️⃣ Testing and reloading nginx..."
sudo nginx -t
sudo systemctl reload nginx

# Test endpoints
echo ""
echo "6️⃣ Testing endpoints..."
sleep 5

echo "Frontend:"
curl -I https://pre.${DOMAIN} 2>&1 | head -5

echo ""
echo "API Health:"
curl -s https://pre-api.${DOMAIN}/health

echo ""
echo "✅ Nginx setup complete!"
echo ""
echo "Services available at:"
echo "- Frontend: https://pre.${DOMAIN}"
echo "- API: https://pre-api.${DOMAIN}"