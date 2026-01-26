#!/bin/bash
# Nginx VM startup script for NouxCubeIA PRE environment
# Complete setup: nginx installation, HTTP config, SSL certificates, HTTPS config

set -e

# Log file for debugging
LOG_FILE="/var/log/nginx-startup.log"
exec 1> >(tee -a $LOG_FILE)
exec 2>&1

echo "[$(date)] Starting Nginx setup for PRE environment..."

# Get metadata from GCP
DOMAIN=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/DOMAIN || echo "nexusdocs360.com")
EMAIL=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/EMAIL || echo "admin@nexusdocs360.com")
ENVIRONMENT=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/ENVIRONMENT || echo "pre")

# Configuration
APP_SUBDOMAIN="pre"
API_SUBDOMAIN="pre-api"
PRE_SUBDOMAIN="pre"
PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"

echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo "Environment: $ENVIRONMENT"

# Update system
apt-get update
apt-get upgrade -y

# Install required packages
echo "[$(date)] Installing required packages..."
apt-get install -y \
    nginx \
    certbot \
    python3-certbot-nginx \
    curl \
    jq \
    htop \
    git

# Create necessary directories
mkdir -p /etc/nginx/ssl
mkdir -p /var/www/certbot
mkdir -p /var/www/html

# Clean up any existing configurations
echo "[$(date)] Cleaning up existing configurations..."
rm -f /etc/nginx/sites-enabled/*
rm -f /etc/nginx/sites-available/default

# Configure Nginx custom settings
cat > /etc/nginx/conf.d/custom.conf << 'EOF'
# Rate limiting zones
limit_req_zone $binary_remote_addr zone=pre_api_limit:10m rate=100r/s;

# Custom log format
log_format detailed '$remote_addr - $remote_user [$time_local] '
                   '"$request" $status $body_bytes_sent '
                   '"$http_referer" "$http_user_agent" '
                   '$request_time $upstream_response_time';

# Increase client body size for file uploads
client_max_body_size 100M;
client_body_buffer_size 10M;
EOF

# Function to get Cloud Run service URL
get_service_url() {
    local SERVICE_NAME=$1
    local URL=$(gcloud run services describe $SERVICE_NAME \
        --region=$REGION \
        --project=$PROJECT_ID \
        --format="value(status.url)" 2>/dev/null || echo "")
    echo "$URL"
}

# Get Cloud Run URLs (might be empty initially)
echo "[$(date)] Getting Cloud Run service URLs..."
FRONTEND_URL=$(get_service_url "nexus-frontend-${ENVIRONMENT}")
API_URL=$(get_service_url "nexus-api-${ENVIRONMENT}")

# Use defaults if services not deployed yet
FRONTEND_URL=${FRONTEND_URL:-"http://localhost:3000"}
API_URL=${API_URL:-"http://localhost:8000"}

echo "Frontend URL: $FRONTEND_URL"
echo "API URL: $API_URL"

# STEP 1: Create HTTP-only configuration for Certbot
echo "[$(date)] Creating HTTP configuration for certificate generation..."

cat > /etc/nginx/sites-available/pre-http.conf << EOF
# HTTP configuration for all PRE subdomains
server {
    listen 80;
    listen [::]:80;
    server_name $PRE_SUBDOMAIN.$DOMAIN $APP_SUBDOMAIN.$DOMAIN $API_SUBDOMAIN.$DOMAIN;

    # ACME challenge for Let's Encrypt
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Basic response
    location / {
        return 200 'Nginx is ready. SSL certificate generation in progress...';
        add_header Content-Type text/plain;
    }

    # Health check
    location /health {
        access_log off;
        return 200 'OK';
        add_header Content-Type text/plain;
    }
}
EOF

# Enable HTTP configuration
ln -sf /etc/nginx/sites-available/pre-http.conf /etc/nginx/sites-enabled/

# Test and start nginx
echo "[$(date)] Starting nginx with HTTP configuration..."
nginx -t
systemctl enable nginx
systemctl start nginx || systemctl reload nginx

# STEP 2: Obtain SSL certificates
echo "[$(date)] Obtaining SSL certificates..."
certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --non-interactive \
    --agree-tos \
    --email $EMAIL \
    --domains $PRE_SUBDOMAIN.$DOMAIN,$APP_SUBDOMAIN.$DOMAIN,$API_SUBDOMAIN.$DOMAIN \
    --expand

if [ $? -ne 0 ]; then
    echo "[$(date)] Failed to obtain SSL certificates. Continuing with HTTP only..."
    exit 0
fi

# STEP 3: Create HTTPS configurations after certificates are obtained
echo "[$(date)] Creating HTTPS configurations..."

# Remove ALL existing configurations to start fresh
echo "[$(date)] Removing all existing site configurations..."
rm -f /etc/nginx/sites-enabled/*
rm -f /etc/nginx/sites-available/pre-http.conf
rm -f /etc/nginx/sites-available/pre.conf
rm -f /etc/nginx/sites-available/app-pre.conf
rm -f /etc/nginx/sites-available/api-pre.conf

# Main PRE landing page (redirects to app)
cat > /etc/nginx/sites-available/pre.conf << EOF
# HTTPS redirect for main PRE subdomain
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $PRE_SUBDOMAIN.$DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$PRE_SUBDOMAIN.$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$PRE_SUBDOMAIN.$DOMAIN/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/$PRE_SUBDOMAIN.$DOMAIN/chain.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Environment "PRE" always;

    # Redirect to app
    location / {
        return 301 https://$APP_SUBDOMAIN.$DOMAIN\$request_uri;
    }

    location /health {
        access_log off;
        return 200 'OK';
        add_header Content-Type text/plain;
    }
}

# HTTP to HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    server_name $PRE_SUBDOMAIN.$DOMAIN;
    return 301 https://\$server_name\$request_uri;
}
EOF

# Frontend application configuration
cat > /etc/nginx/sites-available/app-pre.conf << EOF
# Frontend application
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $APP_SUBDOMAIN.$DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$PRE_SUBDOMAIN.$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$PRE_SUBDOMAIN.$DOMAIN/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/$PRE_SUBDOMAIN.$DOMAIN/chain.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Environment "PRE" always;

    # Logging
    access_log /var/log/nginx/pre-app-access.log;
    error_log /var/log/nginx/pre-app-error.log;

    # Proxy timeouts
    proxy_connect_timeout 60s;
    proxy_send_timeout 120s;
    proxy_read_timeout 120s;

    location / {
        proxy_pass $FRONTEND_URL;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Environment "PRE";
        proxy_cache_bypass \$http_upgrade;
        proxy_buffering off;
    }

    location /health {
        access_log off;
        return 200 'Frontend OK';
        add_header Content-Type text/plain;
    }
}

# HTTP to HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    server_name $APP_SUBDOMAIN.$DOMAIN;
    return 301 https://\$server_name\$request_uri;
}
EOF

# API configuration
cat > /etc/nginx/sites-available/api-pre.conf << EOF
# API backend
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $API_SUBDOMAIN.$DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$PRE_SUBDOMAIN.$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$PRE_SUBDOMAIN.$DOMAIN/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/$PRE_SUBDOMAIN.$DOMAIN/chain.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Environment "PRE" always;

    # CORS headers
    add_header Access-Control-Allow-Origin "https://$APP_SUBDOMAIN.$DOMAIN" always;
    add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-Requested-With" always;
    add_header Access-Control-Allow-Credentials "true" always;

    # Logging
    access_log /var/log/nginx/pre-api-access.log detailed;
    error_log /var/log/nginx/pre-api-error.log;

    # Rate limiting
    limit_req zone=pre_api_limit burst=50 nodelay;

    # Proxy timeouts
    proxy_connect_timeout 60s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;

    # Handle preflight requests
    location / {
        if ($request_method = 'OPTIONS') {
            add_header Access-Control-Allow-Origin "https://$APP_SUBDOMAIN.$DOMAIN" always;
            add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
            add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-Requested-With" always;
            add_header Access-Control-Max-Age 3600;
            add_header Content-Type text/plain;
            add_header Content-Length 0;
            return 204;
        }

        proxy_pass $API_URL;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Environment "PRE";
        proxy_buffering off;
    }

    # Health check endpoint
    location /health {
        access_log off;
        proxy_pass $API_URL/health;
    }

    # WebSocket endpoint
    location /ws {
        proxy_pass $API_URL/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }
}

# HTTP to HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    server_name $API_SUBDOMAIN.$DOMAIN;
    return 301 https://\$server_name\$request_uri;
}
EOF

# Enable all HTTPS sites
ln -sf /etc/nginx/sites-available/pre.conf /etc/nginx/sites-enabled/
ln -sf /etc/nginx/sites-available/app-pre.conf /etc/nginx/sites-enabled/
ln -sf /etc/nginx/sites-available/api-pre.conf /etc/nginx/sites-enabled/

# Test configuration
echo "[$(date)] Testing HTTPS configuration..."
nginx -t

if [ $? -eq 0 ]; then
    echo "[$(date)] Reloading nginx with HTTPS configuration..."
    systemctl reload nginx
else
    echo "[$(date)] Configuration test failed. Check logs."
    exit 1
fi

# STEP 4: Create utility scripts

# Create Cloud Run URL update script
cat > /usr/local/bin/update-cloudrun-urls.sh << 'SCRIPT'
#!/bin/bash
# Update Nginx with Cloud Run URLs

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
ENVIRONMENT="pre"

echo "Getting Cloud Run URLs..."
BACKEND_URL=$(gcloud run services describe nexus-api-${ENVIRONMENT} --region=$REGION --project=$PROJECT_ID --format='value(status.url)' 2>/dev/null)
FRONTEND_URL=$(gcloud run services describe nexus-frontend-${ENVIRONMENT} --region=$REGION --project=$PROJECT_ID --format='value(status.url)' 2>/dev/null)

if [ -z "$BACKEND_URL" ] || [ -z "$FRONTEND_URL" ]; then
    echo "❌ Could not get Cloud Run URLs. Make sure services are deployed."
    exit 1
fi

echo "Backend URL: $BACKEND_URL"
echo "Frontend URL: $FRONTEND_URL"

# Update nginx configurations
for config in /etc/nginx/sites-available/app-pre.conf; do
    if [ -f "$config" ]; then
        sed -i "s|proxy_pass http://localhost:3000;|proxy_pass $FRONTEND_URL;|g" $config
        sed -i "s|proxy_pass https://nexus-frontend-${ENVIRONMENT}-.*.run.app;|proxy_pass $FRONTEND_URL;|g" $config
    fi
done

for config in /etc/nginx/sites-available/api-pre.conf; do
    if [ -f "$config" ]; then
        sed -i "s|proxy_pass http://localhost:8000;|proxy_pass $BACKEND_URL;|g" $config
        sed -i "s|proxy_pass https://nexus-api-${ENVIRONMENT}-.*.run.app;|proxy_pass $BACKEND_URL;|g" $config
    fi
done

# Test and reload
nginx -t && systemctl reload nginx
echo "✅ Nginx configuration updated with Cloud Run URLs!"
SCRIPT

chmod +x /usr/local/bin/update-cloudrun-urls.sh

# Create health check script
cat > /usr/local/bin/check-nginx-health.sh << 'SCRIPT'
#!/bin/bash
# Check Nginx and backend health

DOMAIN="nexusdocs360.com"

check_service() {
    local name=$1
    local url=$2
    local expected=$3
    
    response=$(curl -s -o /dev/null -w "%{http_code}" $url)
    if [ "$response" = "$expected" ]; then
        echo "[OK] $name is healthy"
    else
        echo "[FAIL] $name returned $response (expected $expected)"
    fi
}

echo "=== PRE Environment Health Check ==="
check_service "Nginx" "http://localhost/health" "200"
check_service "Frontend" "https://pre.$DOMAIN/health" "200"
check_service "API" "https://pre-api.$DOMAIN/health" "200"
SCRIPT

chmod +x /usr/local/bin/check-nginx-health.sh

# STEP 5: Set up automatic certificate renewal
echo "[$(date)] Setting up certificate renewal..."

cat > /etc/systemd/system/certbot-renewal.service << EOF
[Unit]
Description=Certbot Renewal
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/certbot renew --quiet --nginx
ExecStartPost=/bin/systemctl reload nginx
EOF

cat > /etc/systemd/system/certbot-renewal.timer << EOF
[Unit]
Description=Run Certbot twice daily
After=network.target

[Timer]
OnCalendar=*-*-* 00,12:00:00
RandomizedDelaySec=3600
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl enable certbot-renewal.timer
systemctl start certbot-renewal.timer

# Add health check to crontab
(crontab -l 2>/dev/null || true; echo "*/5 * * * * /usr/local/bin/check-nginx-health.sh >> /var/log/nginx-health.log 2>&1") | crontab -

# Final summary
echo ""
echo "[$(date)] ✅ Nginx setup complete for PRE environment!"
echo ""
echo "Configured domains:"
echo "  - https://$PRE_SUBDOMAIN.$DOMAIN (redirects to app)"
echo "  - https://$APP_SUBDOMAIN.$DOMAIN (frontend)"
echo "  - https://$API_SUBDOMAIN.$DOMAIN (API)"
echo ""
echo "Cloud Run URLs:"
echo "  - Frontend: $FRONTEND_URL"
echo "  - API: $API_URL"
echo ""
if [[ "$FRONTEND_URL" == "http://localhost:3000" ]] || [[ "$API_URL" == "http://localhost:8000" ]]; then
    echo "⚠️  Using default localhost URLs. After deploying to Cloud Run, run:"
    echo "   /usr/local/bin/update-cloudrun-urls.sh"
fi
echo ""
echo "Logs: /var/log/nginx-startup.log"
echo "Health check: /usr/local/bin/check-nginx-health.sh"