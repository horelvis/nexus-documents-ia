#!/bin/bash
# Setup Nginx Proxy VM with SSL certificates
# This script configures nginx to proxy requests to Cloud Run services

set -e

echo "🔧 Setting up Nginx Proxy"
echo "========================"
echo ""

# Configuration
DOMAIN="nexusdocs360.app"
FRONTEND_SUBDOMAIN="pre"
API_SUBDOMAIN="pre-api"
EMAIL="admin@nexusdocs360.app"

# Cloud Run URLs (update these with your actual URLs)
FRONTEND_URL="https://nexus-frontend-pre-300252412370.europe-west1.run.app"
BACKEND_URL="https://nexus-backend-pre-300252412370.europe-west1.run.app"

echo "Domain configuration:"
echo "- Frontend: ${FRONTEND_SUBDOMAIN}.${DOMAIN}"
echo "- API: ${API_SUBDOMAIN}.${DOMAIN}"
echo ""

# Install required packages
echo "1️⃣ Installing required packages..."
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx

# Stop nginx for initial setup
sudo systemctl stop nginx || true

# Create nginx configuration
echo ""
echo "2️⃣ Creating nginx configuration..."

# Create frontend configuration
sudo tee /etc/nginx/sites-available/${FRONTEND_SUBDOMAIN}.${DOMAIN} > /dev/null <<EOF
server {
    listen 80;
    server_name ${FRONTEND_SUBDOMAIN}.${DOMAIN};

    location / {
        proxy_pass ${FRONTEND_URL};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_cache off;
    }
}
EOF

# Create API configuration
sudo tee /etc/nginx/sites-available/${API_SUBDOMAIN}.${DOMAIN} > /dev/null <<EOF
server {
    listen 80;
    server_name ${API_SUBDOMAIN}.${DOMAIN};

    location / {
        proxy_pass ${BACKEND_URL};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Authorization \$http_authorization;
        proxy_buffering off;
        proxy_request_buffering off;
        
        # CORS headers for API
        add_header 'Access-Control-Allow-Origin' 'https://${FRONTEND_SUBDOMAIN}.${DOMAIN}' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type, X-Requested-With' always;
        add_header 'Access-Control-Allow-Credentials' 'true' always;
        
        if (\$request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' 'https://${FRONTEND_SUBDOMAIN}.${DOMAIN}' always;
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

# Enable sites
echo ""
echo "3️⃣ Enabling sites..."
sudo ln -sf /etc/nginx/sites-available/${FRONTEND_SUBDOMAIN}.${DOMAIN} /etc/nginx/sites-enabled/
sudo ln -sf /etc/nginx/sites-available/${API_SUBDOMAIN}.${DOMAIN} /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test configuration
echo ""
echo "4️⃣ Testing nginx configuration..."
sudo nginx -t

# Start nginx
echo ""
echo "5️⃣ Starting nginx..."
sudo systemctl start nginx
sudo systemctl enable nginx

# Obtain SSL certificates
echo ""
echo "6️⃣ Obtaining SSL certificates..."
echo "Make sure DNS records are pointing to this server's IP address!"
echo ""
read -p "Press Enter when DNS is ready, or Ctrl+C to cancel..."

# Get certificates
sudo certbot --nginx \
    -d ${FRONTEND_SUBDOMAIN}.${DOMAIN} \
    -d ${API_SUBDOMAIN}.${DOMAIN} \
    --non-interactive \
    --agree-tos \
    --email $EMAIL \
    --redirect

# Setup auto-renewal
echo ""
echo "7️⃣ Setting up auto-renewal..."
(crontab -l 2>/dev/null; echo "0 0,12 * * * /usr/bin/certbot renew --quiet") | crontab -

# Final test
echo ""
echo "8️⃣ Final configuration test..."
sudo nginx -t
sudo systemctl reload nginx

echo ""
echo "✅ Nginx proxy setup complete!"
echo ""
echo "Your services are now available at:"
echo "- Frontend: https://${FRONTEND_SUBDOMAIN}.${DOMAIN}"
echo "- API: https://${API_SUBDOMAIN}.${DOMAIN}"
echo ""
echo "SSL certificates will auto-renew via cron"
echo ""
echo "To check nginx status: sudo systemctl status nginx"
echo "To check nginx logs: sudo tail -f /var/log/nginx/error.log"