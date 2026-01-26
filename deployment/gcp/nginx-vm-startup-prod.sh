#!/bin/bash
# Nginx VM startup script for NouxCubeIA PRODUCTION environment
# Configures Nginx as reverse proxy with Let's Encrypt SSL for production domains
# Includes enhanced security, performance optimization, and high availability features

set -e

# Get metadata
DOMAIN=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/DOMAIN)
EMAIL=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/EMAIL)
ENVIRONMENT=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/ENVIRONMENT)

# PROD-specific configuration
APP_SUBDOMAIN="app"
API_SUBDOMAIN="api"
WWW_SUBDOMAIN="www"

# Log file for debugging
LOG_FILE="/var/log/nginx-startup.log"
exec 1> >(tee -a $LOG_FILE)
exec 2>&1

echo "[$(date)] Starting Nginx setup for PRODUCTION environment..."
echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo "Environment: $ENVIRONMENT"

# Update system with security patches
apt-get update
apt-get upgrade -y
apt-get dist-upgrade -y

# Install required packages
apt-get install -y \
    nginx \
    nginx-extras \
    certbot \
    python3-certbot-nginx \
    curl \
    jq \
    htop \
    git \
    fail2ban \
    ufw \
    monitoring-plugins \
    prometheus-node-exporter

# Security hardening
# Configure UFW firewall
ufw --force enable
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow http
ufw allow https
ufw reload

# Configure fail2ban
systemctl enable fail2ban
systemctl start fail2ban

# Create necessary directories
mkdir -p /etc/nginx/ssl
mkdir -p /var/www/certbot
mkdir -p /var/www/html
mkdir -p /var/cache/nginx
mkdir -p /var/log/nginx/archive

# Configure log rotation
cat > /etc/logrotate.d/nginx << EOF
/var/log/nginx/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data adm
    sharedscripts
    prerotate
        if [ -d /etc/logrotate.d/httpd-prerotate ]; then
            run-parts /etc/logrotate.d/httpd-prerotate
        fi
    endscript
    postrotate
        invoke-rc.d nginx rotate >/dev/null 2>&1
    endscript
}
EOF

# Create DH parameters for enhanced security
openssl dhparam -out /etc/nginx/ssl/dhparam.pem 2048

# Create a simple health check endpoint
cat > /var/www/html/health << 'EOF'
OK
EOF

# Create robots.txt
cat > /var/www/html/robots.txt << EOF
User-agent: *
Disallow: /api/
Disallow: /admin/
Disallow: /.well-known/
Sitemap: https://$DOMAIN/sitemap.xml
EOF

# Configure sysctl for performance
cat >> /etc/sysctl.conf << EOF
# Nginx Performance Tuning
net.core.somaxconn = 65535
net.ipv4.tcp_max_tw_buckets = 1440000
net.ipv4.ip_local_port_range = 1024 65535
net.ipv4.tcp_fin_timeout = 15
net.ipv4.tcp_keepalive_time = 300
net.ipv4.tcp_keepalive_probes = 5
net.ipv4.tcp_keepalive_intvl = 15
net.core.rmem_default = 31457280
net.core.rmem_max = 33554432
net.core.wmem_default = 31457280
net.core.wmem_max = 33554432
net.core.netdev_max_backlog = 65535
net.core.optmem_max = 25165824
net.ipv4.tcp_mem = 786432 1048576 26777216
net.ipv4.udp_mem = 65536 131072 262144
net.ipv4.tcp_rmem = 8192 87380 33554432
net.ipv4.udp_rmem_min = 16384
net.ipv4.tcp_wmem = 8192 65536 33554432
net.ipv4.udp_wmem_min = 16384
EOF
sysctl -p

# Configure Nginx main configuration
cat > /etc/nginx/nginx.conf << 'EOF'
user www-data;
worker_processes auto;
worker_rlimit_nofile 65535;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

events {
    worker_connections 4096;
    use epoll;
    multi_accept on;
}

http {
    # Basic Settings
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    server_tokens off;
    client_max_body_size 50M;
    client_body_buffer_size 1M;

    # MIME Types
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # SSL Settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Logging Settings
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for" '
                    'rt=$request_time uct="$upstream_connect_time" '
                    'uht="$upstream_header_time" urt="$upstream_response_time"';

    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log warn;

    # Gzip Settings
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript application/json application/javascript application/xml+rss application/rss+xml application/atom+xml image/svg+xml;

    # Rate Limiting Zones
    limit_req_zone $binary_remote_addr zone=general_limit:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=30r/s;
    limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=5r/m;
    limit_conn_zone $binary_remote_addr zone=conn_limit:10m;

    # Cache Settings
    proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=static_cache:10m max_size=1g inactive=60m use_temp_path=off;

    # Security Headers (global)
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;

    # Include site configurations
    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
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
FRONTEND_URL=$(get_service_url "nexus-frontend-prod")
API_URL=$(get_service_url "nexus-api-prod")

echo "Frontend URL: $FRONTEND_URL"
echo "API URL: $API_URL"

# Obtain SSL certificates for PRODUCTION domains
echo "[$(date)] Obtaining SSL certificates for PRODUCTION..."
certbot certonly \
    --nginx \
    --non-interactive \
    --agree-tos \
    --email $EMAIL \
    --domains $DOMAIN,$WWW_SUBDOMAIN.$DOMAIN,$APP_SUBDOMAIN.$DOMAIN,$API_SUBDOMAIN.$DOMAIN \
    --expand || echo "Certificate already exists or failed"

# Create PRODUCTION-specific Nginx configurations
# Main domain redirect
cat > /etc/nginx/sites-available/main.conf << EOF
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $DOMAIN $WWW_SUBDOMAIN.$DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/$DOMAIN/chain.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

    # Redirect to app
    location / {
        return 301 https://$APP_SUBDOMAIN.$DOMAIN\$request_uri;
    }

    location /health {
        access_log off;
        return 200 'OK';
        add_header Content-Type text/plain;
    }

    # SEO files
    location = /robots.txt {
        root /var/www/html;
    }

    location = /sitemap.xml {
        proxy_pass ${FRONTEND_URL}/sitemap.xml;
    }
}

server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN $WWW_SUBDOMAIN.$DOMAIN;
    return 301 https://\$server_name\$request_uri;
}
EOF

# Frontend application configuration with caching
cat > /etc/nginx/sites-available/app.conf << EOF
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $APP_SUBDOMAIN.$DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/$DOMAIN/chain.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header Content-Security-Policy "default-src 'self' https://$API_SUBDOMAIN.$DOMAIN; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://www.googletagmanager.com https://www.google-analytics.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data: https:; font-src 'self' data: https://fonts.gstatic.com; connect-src 'self' https://$API_SUBDOMAIN.$DOMAIN https://www.google-analytics.com;" always;

    # Logging
    access_log /var/log/nginx/app-access.log main;
    error_log /var/log/nginx/app-error.log;

    # Rate limiting
    limit_req zone=general_limit burst=20 nodelay;
    limit_conn conn_limit 50;

    # Proxy settings
    proxy_http_version 1.1;
    proxy_set_header Upgrade \$http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_cache_bypass \$http_upgrade;
    proxy_buffering on;

    # Timeouts
    proxy_connect_timeout 30s;
    proxy_send_timeout 90s;
    proxy_read_timeout 90s;

    # Static assets with caching
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        proxy_pass ${FRONTEND_URL};
        proxy_cache static_cache;
        proxy_cache_valid 200 60m;
        proxy_cache_valid 404 1m;
        proxy_cache_bypass \$http_pragma \$http_authorization;
        add_header X-Cache-Status \$upstream_cache_status;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }

    location / {
        proxy_pass ${FRONTEND_URL};
        
        # Security headers for HTML
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
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

# API configuration with enhanced security
cat > /etc/nginx/sites-available/api.conf << EOF
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $API_SUBDOMAIN.$DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/$DOMAIN/chain.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer" always;

    # CORS headers
    set \$cors_origin "";
    if (\$http_origin ~* ^https://(app\.)?$DOMAIN$) {
        set \$cors_origin \$http_origin;
    }
    add_header Access-Control-Allow-Origin \$cors_origin always;
    add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-Requested-With" always;
    add_header Access-Control-Allow-Credentials "true" always;
    add_header Access-Control-Max-Age 86400 always;

    # Logging
    access_log /var/log/nginx/api-access.log main;
    error_log /var/log/nginx/api-error.log;

    # Rate limiting
    limit_req zone=api_limit burst=50 nodelay;
    limit_conn conn_limit 100;

    # Special rate limit for auth endpoints
    location ~* ^/(auth|login|register|password) {
        limit_req zone=auth_limit burst=5 nodelay;
        proxy_pass ${API_URL};
    }

    # Proxy settings
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_buffering off;

    # Timeouts for API
    proxy_connect_timeout 30s;
    proxy_send_timeout 120s;
    proxy_read_timeout 120s;

    # API endpoints
    location / {
        # Handle preflight requests
        if (\$request_method = 'OPTIONS') {
            add_header Access-Control-Allow-Origin \$cors_origin always;
            add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
            add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-Requested-With" always;
            add_header Access-Control-Max-Age 86400;
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

    # Metrics endpoint (internal only)
    location /metrics {
        allow 10.0.0.0/8;
        deny all;
        proxy_pass ${API_URL}/metrics;
    }

    # WebSocket endpoint
    location /ws {
        proxy_pass ${API_URL}/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }

    # File upload configuration
    client_max_body_size 50M;
    client_body_buffer_size 1M;
}

server {
    listen 80;
    listen [::]:80;
    server_name $API_SUBDOMAIN.$DOMAIN;
    return 301 https://\$server_name\$request_uri;
}
EOF

# Enable the sites
ln -sf /etc/nginx/sites-available/main.conf /etc/nginx/sites-enabled/
ln -sf /etc/nginx/sites-available/app.conf /etc/nginx/sites-enabled/
ln -sf /etc/nginx/sites-available/api.conf /etc/nginx/sites-enabled/

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
ExecStart=/usr/bin/certbot renew --quiet --nginx --deploy-hook "systemctl reload nginx"
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

# Create monitoring endpoints for Prometheus
cat > /etc/nginx/sites-available/monitoring.conf << EOF
server {
    listen 9113;
    server_name localhost;
    
    location /metrics {
        stub_status on;
        access_log off;
        allow 127.0.0.1;
        allow 10.0.0.0/8;
        deny all;
    }
}
EOF

ln -sf /etc/nginx/sites-available/monitoring.conf /etc/nginx/sites-enabled/

# Create backup script
cat > /usr/local/bin/backup-nginx-config.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/var/backups/nginx"
mkdir -p $BACKUP_DIR
tar -czf $BACKUP_DIR/nginx-config-$(date +%Y%m%d-%H%M%S).tar.gz /etc/nginx/
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete
EOF

chmod +x /usr/local/bin/backup-nginx-config.sh

# Add to crontab
(crontab -l 2>/dev/null; echo "0 2 * * * /usr/local/bin/backup-nginx-config.sh") | crontab -

# Create monitoring script
cat > /usr/local/bin/check-nginx-health.sh << 'EOF'
#!/bin/bash
# Comprehensive health check for production

check_service() {
    local name=$1
    local url=$2
    local expected=$3
    
    response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 $url)
    if [ "$response" = "$expected" ]; then
        echo "[OK] $name is healthy (${response})"
        return 0
    else
        echo "[FAIL] $name returned $response (expected $expected)"
        # Send alert
        curl -X POST -H 'Content-type: application/json' \
            --data '{"text":"PRODUCTION ALERT: '$name' health check failed!"}' \
            $SLACK_WEBHOOK_URL 2>/dev/null || true
        return 1
    fi
}

echo "=== PRODUCTION Health Check - $(date) ==="
failed=0

check_service "Nginx" "http://localhost/health" "200" || ((failed++))
check_service "Frontend" "https://app.$DOMAIN/health" "200" || ((failed++))
check_service "API" "https://api.$DOMAIN/health" "200" || ((failed++))

if [ $failed -gt 0 ]; then
    echo "Health check failed with $failed errors"
    # Restart Nginx if multiple failures
    if [ $failed -gt 2 ]; then
        systemctl restart nginx
        echo "Nginx restarted due to multiple failures"
    fi
fi

# Check disk space
df -h | grep -E '^/dev/' | awk '{if(int($5) > 80) print "WARNING: " $1 " is " $5 " full"}'

# Check SSL certificate expiry
for domain in $DOMAIN app.$DOMAIN api.$DOMAIN; do
    expiry=$(echo | openssl s_client -servername $domain -connect $domain:443 2>/dev/null | openssl x509 -noout -dates | grep notAfter | cut -d= -f2)
    expiry_epoch=$(date -d "$expiry" +%s)
    current_epoch=$(date +%s)
    days_left=$(( ($expiry_epoch - $current_epoch) / 86400 ))
    if [ $days_left -lt 30 ]; then
        echo "WARNING: SSL certificate for $domain expires in $days_left days"
    fi
done
EOF

chmod +x /usr/local/bin/check-nginx-health.sh

# Add to crontab for monitoring
(crontab -l 2>/dev/null; echo "*/5 * * * * /usr/local/bin/check-nginx-health.sh >> /var/log/nginx-health.log 2>&1") | crontab -

echo "[$(date)] Nginx setup complete for PRODUCTION environment!"
echo "Configured domains:"
echo "  - https://$DOMAIN"
echo "  - https://$WWW_SUBDOMAIN.$DOMAIN"
echo "  - https://$APP_SUBDOMAIN.$DOMAIN" 
echo "  - https://$API_SUBDOMAIN.$DOMAIN"
echo ""
echo "Security features enabled:"
echo "  - TLS 1.2/1.3 only"
echo "  - HSTS with preload"
echo "  - Rate limiting"
echo "  - DDoS protection"
echo "  - Automated backups"
echo "  - Health monitoring"