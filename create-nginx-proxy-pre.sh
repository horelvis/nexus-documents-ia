#!/bin/bash
# Create Nginx proxy instance for PRE environment

set -e

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
ZONE="europe-west1-b"
VPC_NAME="nexus-vpc-pre"
SUBNET_NAME="nexus-subnet-pre"
DOMAIN="nexusdocs360.com"
SSL_EMAIL="admin@nexusdocs360.com"

echo "🔒 Creating Nginx reverse proxy for PRE environment"
echo "================================================="
echo ""

# Set project
gcloud config set project $PROJECT_ID

# 1. Reserve static IP
echo "📍 Reserving static IP for Nginx..."
gcloud compute addresses create nexus-nginx-ip-pre \
    --region=$REGION \
    --project=$PROJECT_ID 2>/dev/null || echo "Static IP already exists"

NGINX_IP=$(gcloud compute addresses describe nexus-nginx-ip-pre \
    --region=$REGION \
    --format="value(address)" \
    --project=$PROJECT_ID)

echo "✅ Nginx IP: $NGINX_IP"

# 2. Create storage bucket for scripts if not exists
echo "🪣 Creating scripts bucket..."
gsutil mb -p $PROJECT_ID gs://nexusdocs360-pre-scripts/ 2>/dev/null || echo "Scripts bucket already exists"

# 3. Create Nginx startup script
echo "📝 Creating Nginx startup script..."
cat > /tmp/nginx-vm-startup-pre.sh << 'EOF'
#!/bin/bash
# Nginx VM startup script for PRE environment

# Get metadata
DOMAIN=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/DOMAIN)
EMAIL=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/EMAIL)
ENVIRONMENT=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/ENVIRONMENT)

# Update system
apt-get update
apt-get upgrade -y

# Install required packages
apt-get install -y nginx certbot python3-certbot-nginx curl software-properties-common

# Get Cloud Run service URLs
BACKEND_URL=$(gcloud run services describe nexus-backend-pre --region=europe-west1 --format='value(status.url)')
FRONTEND_URL=$(gcloud run services describe nexus-frontend-pre --region=europe-west1 --format='value(status.url)' 2>/dev/null || echo "")

# Create Nginx configuration
cat > /etc/nginx/sites-available/nexusdocs360-pre << NGINX_CONF
# PRE environment configuration
upstream backend {
    server ${BACKEND_URL#https://};
}

server {
    listen 80;
    server_name pre.${DOMAIN} pre-api.${DOMAIN} pre-app.${DOMAIN};

    # Force HTTPS
    location / {
        return 301 https://\$host\$request_uri;
    }

    # Let's Encrypt verification
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
}

server {
    listen 443 ssl http2;
    server_name pre-api.${DOMAIN};

    ssl_certificate /etc/letsencrypt/live/pre.${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pre.${DOMAIN}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # API proxy
    location / {
        proxy_pass https://backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
        client_max_body_size 100M;
    }
}

server {
    listen 443 ssl http2;
    server_name pre.${DOMAIN} pre-app.${DOMAIN};

    ssl_certificate /etc/letsencrypt/live/pre.${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pre.${DOMAIN}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Frontend proxy (if available)
    location / {
        if [ -n "$FRONTEND_URL" ]; then
            proxy_pass $FRONTEND_URL;
            proxy_http_version 1.1;
            proxy_set_header Host \$http_host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
        else
            # Temporary landing page
            root /var/www/html;
            try_files \$uri \$uri/ =404;
        fi
    }
}
NGINX_CONF

# Enable site
ln -sf /etc/nginx/sites-available/nexusdocs360-pre /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Create temporary index page
mkdir -p /var/www/html
cat > /var/www/html/index.html << HTML
<!DOCTYPE html>
<html>
<head>
    <title>NouxCubeIA PRE Environment</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
        .status { color: green; }
    </style>
</head>
<body>
    <h1>NouxCubeIA PRE Environment</h1>
    <p class="status">✅ Nginx proxy is running</p>
    <p>Backend API: <a href="https://pre-api.${DOMAIN}">https://pre-api.${DOMAIN}</a></p>
</body>
</html>
HTML

# Test and reload Nginx
nginx -t
systemctl reload nginx

# Get SSL certificates
certbot --nginx -d pre.${DOMAIN} -d pre-api.${DOMAIN} -d pre-app.${DOMAIN} \
    --non-interactive --agree-tos --email ${EMAIL} || echo "SSL cert generation failed"

# Setup auto-renewal
echo "0 0,12 * * * root certbot renew --quiet" > /etc/cron.d/certbot-renew

# Setup monitoring
cat > /usr/local/bin/update-upstream.sh << 'SCRIPT'
#!/bin/bash
# Update upstream URLs periodically
BACKEND_URL=$(gcloud run services describe nexus-backend-pre --region=europe-west1 --format='value(status.url)' 2>/dev/null || echo "")
FRONTEND_URL=$(gcloud run services describe nexus-frontend-pre --region=europe-west1 --format='value(status.url)' 2>/dev/null || echo "")

if [ -n "$BACKEND_URL" ]; then
    sed -i "s|server .*;|server ${BACKEND_URL#https://};|" /etc/nginx/sites-available/nexusdocs360-pre
    nginx -s reload
fi
SCRIPT

chmod +x /usr/local/bin/update-upstream.sh
echo "*/5 * * * * root /usr/local/bin/update-upstream.sh" > /etc/cron.d/update-upstream

echo "Nginx setup complete!"
EOF

# 4. Upload startup script to GCS
echo "📤 Uploading startup script to GCS..."
gsutil cp /tmp/nginx-vm-startup-pre.sh gs://nexusdocs360-pre-scripts/

# 5. Create Nginx instance
echo "🖥️  Creating Nginx VM instance..."
gcloud compute instances create nginx-proxy-pre \
    --machine-type=e2-small \
    --zone=$ZONE \
    --network-interface=address=$NGINX_IP,subnet=$SUBNET_NAME \
    --boot-disk-size=10GB \
    --boot-disk-type=pd-standard \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --tags=nginx-proxy-pre \
    --metadata=startup-script-url=gs://nexusdocs360-pre-scripts/nginx-vm-startup-pre.sh,DOMAIN=$DOMAIN,EMAIL=$SSL_EMAIL,ENVIRONMENT=pre \
    --project=$PROJECT_ID

# 6. Create firewall rules
echo "🔥 Creating firewall rules..."
gcloud compute firewall-rules create allow-nginx-http-pre \
    --network=$VPC_NAME \
    --allow=tcp:80,tcp:443 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=nginx-proxy-pre \
    --project=$PROJECT_ID 2>/dev/null || echo "Firewall rule already exists"

# Allow SSH for management
gcloud compute firewall-rules create allow-ssh-nginx-pre \
    --network=$VPC_NAME \
    --allow=tcp:22 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=nginx-proxy-pre \
    --project=$PROJECT_ID 2>/dev/null || echo "SSH firewall rule already exists"

# 7. Wait for instance to be ready
echo "⏳ Waiting for Nginx instance to be ready..."
sleep 30

echo ""
echo "✅ Nginx proxy setup complete!"
echo ""
echo "📊 Nginx Proxy Details:"
echo "   - Instance: nginx-proxy-pre"
echo "   - External IP: $NGINX_IP"
echo "   - Zone: $ZONE"
echo ""
echo "🌐 DNS Configuration Required:"
echo "   - A record: pre.$DOMAIN → $NGINX_IP"
echo "   - A record: pre-app.$DOMAIN → $NGINX_IP"
echo "   - A record: pre-api.$DOMAIN → $NGINX_IP"
echo ""
echo "📝 Access URLs (after DNS propagation):"
echo "   - Frontend: https://pre.$DOMAIN"
echo "   - API: https://pre-api.$DOMAIN"
echo ""
echo "⚠️  Note: SSL certificates will be generated automatically on first access"