#!/bin/bash
# Configure Nginx for PRE environment
# Run this script on the Nginx server

set -e

# Configuration
DOMAIN="nexusdocs360.app"
EMAIL="admin@nexusdocs360.app"
NGINX_IP="34.78.30.77"

echo "🔧 Configuring Nginx for PRE environment"
echo "📋 Domain: $DOMAIN"
echo "📧 Email: $EMAIL"
echo ""

# Check if running as root or with sudo
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root or with sudo" 
   exit 1
fi

# Install required packages
echo "1️⃣ Installing required packages..."
apt-get update
apt-get install -y nginx certbot python3-certbot-nginx

# Create Nginx configuration
echo "2️⃣ Creating Nginx configuration..."
cat > /etc/nginx/sites-available/nexusdocs360-pre <<'EOF'
# HTTP to HTTPS redirect
server {
    listen 80;
    server_name pre.nexusdocs360.app pre-api.nexusdocs360.app;
    
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    location / {
        return 301 https://$host$request_uri;
    }
}

# Frontend - pre.nexusdocs360.app
server {
    listen 443 ssl http2;
    server_name pre.nexusdocs360.app;
    
    # SSL will be configured by Certbot
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    location / {
        # Placeholder - will be updated after Cloud Run deployment
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# API - pre-api.nexusdocs360.app
server {
    listen 443 ssl http2;
    server_name pre-api.nexusdocs360.app;
    
    # SSL will be configured by Certbot
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # CORS headers for API
    add_header Access-Control-Allow-Origin "https://pre.nexusdocs360.app" always;
    add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, Content-Type" always;
    
    location / {
        # Placeholder - will be updated after Cloud Run deployment
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Increased timeout for API
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
        proxy_read_timeout 300;
    }
}
EOF

# Enable site
echo "3️⃣ Enabling site..."
ln -sf /etc/nginx/sites-available/nexusdocs360-pre /etc/nginx/sites-enabled/

# Remove default site if exists
rm -f /etc/nginx/sites-enabled/default

# Test configuration
echo "4️⃣ Testing Nginx configuration..."
nginx -t

# Reload Nginx
echo "5️⃣ Reloading Nginx..."
systemctl reload nginx

# Generate SSL certificates
echo "6️⃣ Generating SSL certificates..."
certbot --nginx \
    -d pre.nexusdocs360.app \
    -d pre-api.nexusdocs360.app \
    --non-interactive \
    --agree-tos \
    --email $EMAIL \
    --redirect

# Create update script
echo "7️⃣ Creating Cloud Run URL update script..."
cat > /usr/local/bin/update-cloudrun-urls.sh <<'SCRIPT'
#!/bin/bash
# Update Nginx with Cloud Run URLs

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"

# Get Cloud Run URLs
echo "Getting Cloud Run URLs..."
BACKEND_URL=$(gcloud run services describe nexus-backend-pre --region=$REGION --project=$PROJECT_ID --format='value(status.url)' 2>/dev/null)
FRONTEND_URL=$(gcloud run services describe nexus-frontend-pre --region=$REGION --project=$PROJECT_ID --format='value(status.url)' 2>/dev/null)

if [ -z "$BACKEND_URL" ] || [ -z "$FRONTEND_URL" ]; then
    echo "❌ Could not get Cloud Run URLs. Make sure services are deployed."
    exit 1
fi

echo "Backend URL: $BACKEND_URL"
echo "Frontend URL: $FRONTEND_URL"

# Update Nginx configuration
echo "Updating Nginx configuration..."
sed -i "s|proxy_pass http://localhost:3000;|proxy_pass $FRONTEND_URL;|g" /etc/nginx/sites-available/nexusdocs360-pre
sed -i "s|proxy_pass http://localhost:8000;|proxy_pass $BACKEND_URL;|g" /etc/nginx/sites-available/nexusdocs360-pre

# Also update if already has Cloud Run URLs
sed -i "s|proxy_pass https://nexus-frontend-pre-.*.run.app;|proxy_pass $FRONTEND_URL;|g" /etc/nginx/sites-available/nexusdocs360-pre
sed -i "s|proxy_pass https://nexus-backend-pre-.*.run.app;|proxy_pass $BACKEND_URL;|g" /etc/nginx/sites-available/nexusdocs360-pre

# Test and reload
nginx -t && systemctl reload nginx
echo "✅ Nginx configuration updated!"
SCRIPT

chmod +x /usr/local/bin/update-cloudrun-urls.sh

echo ""
echo "✅ Nginx configuration complete!"
echo ""
echo "📋 Next steps:"
echo "1. Verify DNS is pointing to: $NGINX_IP"
echo "2. Deploy Cloud Run services"
echo "3. Run: sudo /usr/local/bin/update-cloudrun-urls.sh"
echo ""
echo "🌐 Your sites will be available at:"
echo "   - https://pre.nexusdocs360.app"
echo "   - https://pre-api.nexusdocs360.app"