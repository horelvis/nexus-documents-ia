#!/bin/bash
# Nginx VM startup script for NexusDocs360 PRE environment
# Configures Nginx as reverse proxy with Let's Encrypt SSL for PRE subdomains

set -e

# Get metadata
DOMAIN=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/DOMAIN)
EMAIL=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/EMAIL)
ENVIRONMENT=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/ENVIRONMENT)

# PRE-specific configuration
APP_SUBDOMAIN="pre-app"
API_SUBDOMAIN="pre-api"
PRE_SUBDOMAIN="pre"

# Log file for debugging
LOG_FILE="/var/log/nginx-startup.log"
exec 1> >(tee -a $LOG_FILE)
exec 2>&1

echo "[$(date)] Starting Nginx setup for PRE environment..."
echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo "Environment: $ENVIRONMENT"

# Update system
apt-get update
apt-get upgrade -y

# Install required packages
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

# Create a simple health check endpoint
cat > /var/www/html/health << 'EOF'
OK
EOF

# Create default Nginx configuration for initial setup
cat > /etc/nginx/sites-available/default << EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    # Health check endpoint
    location /health {
        access_log off;
        return 200 'OK';
        add_header Content-Type text/plain;
    }

    # ACME challenge for Let's Encrypt
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Redirect all other traffic to HTTPS
    location / {
        return 301 https://\$host\$request_uri;
    }
}
EOF

# Start Nginx with basic configuration
systemctl enable nginx
systemctl start nginx

# Function to get Cloud Run service URL
get_service_url() {
    local SERVICE_NAME=$1
    local PROJECT_ID=$(gcloud config get-value project)
    local REGION="europe-west1"
    
    gcloud run services describe $SERVICE_NAME \
        --region=$REGION \
        --project=$PROJECT_ID \
        --format="value(status.url)" 2>/dev/null || echo ""
}

# Wait for Cloud Run services to be available
echo "[$(date)] Waiting for Cloud Run services..."
sleep 30

# Get service URLs
FRONTEND_URL=$(get_service_url "nexus-frontend-pre")
API_URL=$(get_service_url "nexus-api-pre")

echo "Frontend URL: $FRONTEND_URL"
echo "API URL: $API_URL"

# Obtain SSL certificates for PRE subdomains
echo "[$(date)] Obtaining SSL certificates for PRE..."
certbot certonly \
    --nginx \
    --non-interactive \
    --agree-tos \
    --email $EMAIL \
    --domains $PRE_SUBDOMAIN.$DOMAIN,$APP_SUBDOMAIN.$DOMAIN,$API_SUBDOMAIN.$DOMAIN \
    --expand || echo "Certificate already exists or failed"

# Create PRE-specific Nginx configurations
# Main PRE landing page
cat > /etc/nginx/sites-available/pre.conf << EOF
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
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
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

server {
    listen 80;
    listen [::]:80;
    server_name $PRE_SUBDOMAIN.$DOMAIN;
    return 301 https://\$server_name\$request_uri;
}
EOF

# Frontend application configuration
cat > /etc/nginx/sites-available/app-pre.conf << EOF
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
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' https://$API_SUBDOMAIN.$DOMAIN; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:;" always;
    add_header X-Environment "PRE" always;

    # Logging
    access_log /var/log/nginx/pre-app-access.log;
    error_log /var/log/nginx/pre-app-error.log;

    # Proxy settings
    proxy_http_version 1.1;
    proxy_set_header Upgrade \$http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_set_header X-Environment "PRE";
    proxy_cache_bypass \$http_upgrade;
    proxy_buffering off;

    # Timeouts for PRE environment (more lenient for testing)
    proxy_connect_timeout 60s;
    proxy_send_timeout 120s;
    proxy_read_timeout 120s;

    location / {
        proxy_pass ${FRONTEND_URL};
        
        # WebSocket support
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$http_connection;
    }

    location /health {
        access_log off;
        return 200 'Frontend OK';
        add_header Content-Type text/plain;
    }
}

server {
    listen 80;
    listen [::]:80;
    server_name $APP_SUBDOMAIN.$DOMAIN;
    return 301 https://\$server_name\$request_uri;
}
EOF

# API configuration
cat > /etc/nginx/sites-available/api-pre.conf << EOF
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
    add_header Referrer-Policy "no-referrer" always;
    add_header X-Environment "PRE" always;

    # CORS headers for PRE
    add_header Access-Control-Allow-Origin "https://$APP_SUBDOMAIN.$DOMAIN" always;
    add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-Requested-With" always;
    add_header Access-Control-Allow-Credentials "true" always;

    # Logging with detailed format for debugging
    log_format detailed '\$remote_addr - \$remote_user [\$time_local] '
                       '"\$request" \$status \$body_bytes_sent '
                       '"\$http_referer" "\$http_user_agent" '
                       '\$request_time \$upstream_response_time';
    
    access_log /var/log/nginx/pre-api-access.log detailed;
    error_log /var/log/nginx/pre-api-error.log debug;

    # Rate limiting for PRE (more permissive for testing)
    limit_req_zone \$binary_remote_addr zone=pre_api_limit:10m rate=100r/s;
    limit_req zone=pre_api_limit burst=50 nodelay;

    # Proxy settings
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_set_header X-Environment "PRE";
    proxy_buffering off;

    # Increased timeouts for AI operations in PRE
    proxy_connect_timeout 60s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;

    # API endpoints
    location / {
        # Handle preflight requests
        if (\$request_method = 'OPTIONS') {
            add_header Access-Control-Allow-Origin "https://$APP_SUBDOMAIN.$DOMAIN" always;
            add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
            add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-Requested-With" always;
            add_header Access-Control-Max-Age 3600;
            add_header Content-Type text/plain;
            add_header Content-Length 0;
            return 204;
        }

        proxy_pass ${API_URL};
    }

    # Health check endpoint
    location /health {
        access_log off;
        proxy_pass ${API_URL}/health;
    }

    # WebSocket endpoint for real-time features
    location /ws {
        proxy_pass ${API_URL}/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }

    # File upload configuration for PRE (larger limits for testing)
    client_max_body_size 100M;
    client_body_buffer_size 10M;
}

server {
    listen 80;
    listen [::]:80;
    server_name $API_SUBDOMAIN.$DOMAIN;
    return 301 https://\$server_name\$request_uri;
}
EOF

# Enable the sites
ln -sf /etc/nginx/sites-available/pre.conf /etc/nginx/sites-enabled/
ln -sf /etc/nginx/sites-available/app-pre.conf /etc/nginx/sites-enabled/
ln -sf /etc/nginx/sites-available/api-pre.conf /etc/nginx/sites-enabled/

# Remove default site
rm -f /etc/nginx/sites-enabled/default

# Test configuration
nginx -t

# Reload Nginx
systemctl reload nginx

# Set up automatic certificate renewal
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

# Create monitoring script
cat > /usr/local/bin/check-nginx-health.sh << 'EOF'
#!/bin/bash
# Check Nginx and backend health

check_service() {
    local name=$1
    local url=$2
    local expected=$3
    
    response=$(curl -s -o /dev/null -w "%{http_code}" $url)
    if [ "$response" = "$expected" ]; then
        echo "[OK] $name is healthy"
    else
        echo "[FAIL] $name returned $response (expected $expected)"
        systemctl status nginx
    fi
}

echo "=== PRE Environment Health Check ==="
check_service "Nginx" "http://localhost/health" "200"
check_service "Frontend" "https://pre-app.$DOMAIN/health" "200"
check_service "API" "https://pre-api.$DOMAIN/health" "200"
EOF

chmod +x /usr/local/bin/check-nginx-health.sh

# Add to crontab for monitoring
(crontab -l 2>/dev/null; echo "*/5 * * * * /usr/local/bin/check-nginx-health.sh >> /var/log/nginx-health.log 2>&1") | crontab -

echo "[$(date)] Nginx setup complete for PRE environment!"
echo "Configured domains:"
echo "  - https://$PRE_SUBDOMAIN.$DOMAIN"
echo "  - https://$APP_SUBDOMAIN.$DOMAIN" 
echo "  - https://$API_SUBDOMAIN.$DOMAIN"