#!/bin/bash
# Setup Nginx with SSL for PRE environment
# Usage: ./nginx-ssl-setup.sh

set -e

# Configuration
DOMAIN="nexusdocs360.app"
ENVIRONMENT="pre"
EMAIL="admin@nexusdocs360.app"
NGINX_IP=$(curl -s ifconfig.me)

echo "🔧 Setting up Nginx with SSL for $ENVIRONMENT environment"
echo "📋 Domain: $DOMAIN"
echo "🌐 IP: $NGINX_IP"
echo ""

# Function to create nginx config
create_nginx_config() {
    local config_file=$1
    local has_ssl=$2
    
    if [ "$has_ssl" = "true" ]; then
        # Full configuration with SSL
        cat > "$config_file" << EOF
# HTTP to HTTPS redirect
server {
    listen 80;
    server_name ${ENVIRONMENT}.${DOMAIN} ${ENVIRONMENT}-api.${DOMAIN};
    return 301 https://\$host\$request_uri;
}

# Frontend - ${ENVIRONMENT}.${DOMAIN}
server {
    listen 443 ssl http2;
    server_name ${ENVIRONMENT}.${DOMAIN};
    
    ssl_certificate /etc/letsencrypt/live/${ENVIRONMENT}.${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${ENVIRONMENT}.${DOMAIN}/privkey.pem;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# API - ${ENVIRONMENT}-api.${DOMAIN}
server {
    listen 443 ssl http2;
    server_name ${ENVIRONMENT}-api.${DOMAIN};
    
    ssl_certificate /etc/letsencrypt/live/${ENVIRONMENT}.${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${ENVIRONMENT}.${DOMAIN}/privkey.pem;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # CORS headers
    add_header Access-Control-Allow-Origin "https://${ENVIRONMENT}.${DOMAIN}" always;
    add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, Content-Type" always;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Increased timeout for API
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
        proxy_read_timeout 300;
    }
}
EOF
    else
        # HTTP only configuration for Certbot
        cat > "$config_file" << EOF
# HTTP configuration for Certbot
server {
    listen 80;
    server_name ${ENVIRONMENT}.${DOMAIN} ${ENVIRONMENT}-api.${DOMAIN};
    
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    location / {
        return 200 "Setting up SSL...\n";
        add_header Content-Type text/plain;
    }
}
EOF
    fi
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root or with sudo" 
   exit 1
fi

# Install nginx if not installed
if ! command -v nginx &> /dev/null; then
    echo "📦 Installing nginx..."
    apt-get update
    apt-get install -y nginx
fi

# Install certbot if not installed
if ! command -v certbot &> /dev/null; then
    echo "📦 Installing certbot..."
    apt-get install -y certbot python3-certbot-nginx
fi

# Create required directories
echo "📁 Creating directories..."
mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled /var/www/html

# Remove any conflicting configurations
echo "🧹 Cleaning up old configurations..."
rm -f /etc/nginx/sites-enabled/default
rm -f /etc/nginx/sites-enabled/api-pre.conf
rm -f /etc/nginx/sites-enabled/frontend-pre.conf

# Create HTTP configuration first
echo "📝 Creating HTTP configuration..."
CONFIG_FILE="/etc/nginx/sites-available/nexusdocs360-${ENVIRONMENT}"
create_nginx_config "$CONFIG_FILE" "false"

# Enable the site
ln -sf "$CONFIG_FILE" "/etc/nginx/sites-enabled/"

# Test nginx configuration
echo "🔍 Testing nginx configuration..."
nginx -t

# Reload nginx
echo "🔄 Reloading nginx..."
systemctl reload nginx

# Generate SSL certificates
echo "🔐 Generating SSL certificates..."
certbot certonly --webroot \
    -w /var/www/html \
    -d ${ENVIRONMENT}.${DOMAIN} \
    -d ${ENVIRONMENT}-api.${DOMAIN} \
    --email $EMAIL \
    --agree-tos \
    --no-eff-email \
    --non-interactive

# Update configuration with SSL
echo "📝 Updating configuration with SSL..."
create_nginx_config "$CONFIG_FILE" "true"

# Test nginx configuration again
echo "🔍 Testing nginx configuration with SSL..."
nginx -t

# Reload nginx with SSL
echo "🔄 Reloading nginx with SSL..."
systemctl reload nginx

# Create update script
echo "📝 Creating Cloud Run URL update script..."
cat > /usr/local/bin/update-cloudrun-urls.sh << 'SCRIPT'
#!/bin/bash
# Update Nginx with Cloud Run URLs

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
ENVIRONMENT="pre"
CONFIG_FILE="/etc/nginx/sites-available/nexusdocs360-${ENVIRONMENT}"

# Get Cloud Run URLs
echo "Getting Cloud Run URLs..."
BACKEND_URL=$(gcloud run services describe nexus-backend-${ENVIRONMENT} --region=$REGION --project=$PROJECT_ID --format='value(status.url)' 2>/dev/null)
FRONTEND_URL=$(gcloud run services describe nexus-frontend-${ENVIRONMENT} --region=$REGION --project=$PROJECT_ID --format='value(status.url)' 2>/dev/null)

if [ -z "$BACKEND_URL" ] || [ -z "$FRONTEND_URL" ]; then
    echo "❌ Could not get Cloud Run URLs. Make sure services are deployed."
    exit 1
fi

echo "Backend URL: $BACKEND_URL"
echo "Frontend URL: $FRONTEND_URL"

# Update nginx configuration
echo "Updating nginx configuration..."
sed -i "s|proxy_pass http://localhost:3000;|proxy_pass $FRONTEND_URL;|g" $CONFIG_FILE
sed -i "s|proxy_pass http://localhost:8000;|proxy_pass $BACKEND_URL;|g" $CONFIG_FILE

# Also update if already has Cloud Run URLs
sed -i "s|proxy_pass https://nexus-frontend-${ENVIRONMENT}-.*.run.app;|proxy_pass $FRONTEND_URL;|g" $CONFIG_FILE
sed -i "s|proxy_pass https://nexus-backend-${ENVIRONMENT}-.*.run.app;|proxy_pass $BACKEND_URL;|g" $CONFIG_FILE

# Test and reload
nginx -t && systemctl reload nginx
echo "✅ Nginx configuration updated!"
SCRIPT

chmod +x /usr/local/bin/update-cloudrun-urls.sh

echo ""
echo "✅ Nginx SSL setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Deploy your applications to Cloud Run"
echo "2. Run: /usr/local/bin/update-cloudrun-urls.sh"
echo ""
echo "🌐 Your sites will be available at:"
echo "   - https://${ENVIRONMENT}.${DOMAIN}"
echo "   - https://${ENVIRONMENT}-api.${DOMAIN}"
echo ""
echo "🔐 SSL certificates will auto-renew via cron"
echo "📊 Check nginx logs: tail -f /var/log/nginx/error.log"