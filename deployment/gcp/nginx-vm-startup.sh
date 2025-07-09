#!/bin/bash
# Startup script for Nginx VM on GCP

# Update system
apt-get update
apt-get upgrade -y

# Install Docker and Docker Compose
apt-get install -y docker.io docker-compose git

# Enable Docker
systemctl start docker
systemctl enable docker

# Clone repository (or copy files)
mkdir -p /opt/nexus
cd /opt/nexus

# Create nginx directories
mkdir -p nginx/conf.d nginx/scripts certbot/conf certbot/www

# Create nginx.conf
cat > nginx/nginx.conf << 'EOF'
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    use epoll;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';
    
    access_log /var/log/nginx/access.log main;
    
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 100M;
    
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript 
               application/json application/javascript application/xml+rss 
               application/rss+xml application/atom+xml image/svg+xml;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=app_limit:10m rate=20r/s;
    
    # Upstream configuration for Cloud Run services
    upstream frontend {
        server ${FRONTEND_URL};
        keepalive 32;
    }
    
    upstream api {
        server ${API_URL};
        keepalive 32;
    }
    
    include /etc/nginx/conf.d/*.conf;
}
EOF

# Create default.conf for HTTP
cat > nginx/conf.d/default.conf << 'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} *.${DOMAIN};
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}
EOF

# Create app.conf for HTTPS frontend
cat > nginx/conf.d/app.conf << 'EOF'
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name app.${DOMAIN} www.${DOMAIN};
    
    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    
    limit_req zone=app_limit burst=20 nodelay;
    
    location / {
        proxy_pass https://frontend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

# Create api.conf for HTTPS API
cat > nginx/conf.d/api.conf << 'EOF'
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name api.${DOMAIN};
    
    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    
    limit_req zone=api_limit burst=30 nodelay;
    
    location / {
        proxy_pass https://api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
}
EOF

# Create docker-compose.yml for Nginx
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  nginx:
    image: nginx:alpine
    container_name: nexus-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./certbot/conf:/etc/letsencrypt:ro
      - ./certbot/www:/var/www/certbot:ro
    restart: unless-stopped
    command: "/bin/sh -c 'while :; do sleep 6h & wait $${!}; nginx -s reload; done & nginx -g \"daemon off;\"'"

  certbot:
    image: certbot/certbot
    container_name: nexus-certbot
    volumes:
      - ./certbot/conf:/etc/letsencrypt
      - ./certbot/www:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"
EOF

# Set environment variables
export DOMAIN="${DOMAIN:-nexusdocs.com}"
export EMAIL="${EMAIL:-admin@nexusdocs.com}"
export FRONTEND_URL="${FRONTEND_URL}"
export API_URL="${API_URL}"

# Replace variables in config files
find nginx/conf.d -name "*.conf" -exec sed -i "s/\${DOMAIN}/$DOMAIN/g" {} \;
find nginx/conf.d -name "*.conf" -exec sed -i "s/\${FRONTEND_URL}/$FRONTEND_URL/g" {} \;
find nginx/conf.d -name "*.conf" -exec sed -i "s/\${API_URL}/$API_URL/g" {} \;

# Initial setup - generate self-signed certificate
mkdir -p certbot/conf/live/$DOMAIN
openssl req -x509 -nodes -newkey rsa:4096 -days 1 \
    -keyout certbot/conf/live/$DOMAIN/privkey.pem \
    -out certbot/conf/live/$DOMAIN/fullchain.pem \
    -subj "/CN=$DOMAIN"

# Start Nginx
docker-compose up -d nginx

# Wait for Nginx to start
sleep 10

# Get Let's Encrypt certificate
docker-compose run --rm certbot certonly --webroot \
    --webroot-path=/var/www/certbot \
    --email $EMAIL \
    --agree-tos \
    --no-eff-email \
    --force-renewal \
    -d $DOMAIN \
    -d www.$DOMAIN \
    -d app.$DOMAIN \
    -d api.$DOMAIN

# Reload Nginx with new certificate
docker-compose exec nginx nginx -s reload

# Start Certbot container for auto-renewal
docker-compose up -d certbot

echo "Nginx proxy setup complete!"