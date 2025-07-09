#!/bin/bash
set -e

# Environment variables with defaults
DOMAIN=${DOMAIN:-nexusdocs.com}
APP_SUBDOMAIN=${APP_SUBDOMAIN:-app}
API_SUBDOMAIN=${API_SUBDOMAIN:-api}
WWW_SUBDOMAIN=${WWW_SUBDOMAIN:-www}
EMAIL=${SSL_EMAIL:-admin@$DOMAIN}
STAGING=${SSL_STAGING:-false}
FORCE_RENEWAL=${FORCE_RENEWAL:-false}

echo "Starting Nginx with SSL setup..."
echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo "Staging: $STAGING"

# Process configuration templates
/usr/local/bin/process-templates.sh

# Function to check if certificates exist
check_certificates() {
    if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ] && [ -f "/etc/letsencrypt/live/$DOMAIN/privkey.pem" ]; then
        return 0
    else
        return 1
    fi
}

# Function to generate self-signed certificate for initial setup
generate_self_signed() {
    echo "Generating self-signed certificate for initial setup..."
    mkdir -p /etc/letsencrypt/live/$DOMAIN
    openssl req -x509 -nodes -newkey rsa:4096 -days 1 \
        -keyout /etc/letsencrypt/live/$DOMAIN/privkey.pem \
        -out /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
        -subj "/CN=$DOMAIN"
    cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem /etc/letsencrypt/live/$DOMAIN/chain.pem
}

# Function to obtain Let's Encrypt certificate
obtain_certificate() {
    echo "Obtaining Let's Encrypt certificate..."
    
    # Certbot command with staging flag if needed
    CERTBOT_CMD="certbot certonly --webroot -w /var/www/certbot \
        --email $EMAIL \
        --agree-tos \
        --no-eff-email \
        --force-renewal \
        -d $DOMAIN \
        -d $WWW_SUBDOMAIN.$DOMAIN \
        -d $APP_SUBDOMAIN.$DOMAIN \
        -d $API_SUBDOMAIN.$DOMAIN"
    
    if [ "$STAGING" = "true" ]; then
        CERTBOT_CMD="$CERTBOT_CMD --staging"
    fi
    
    # Run certbot
    if $CERTBOT_CMD; then
        echo "Certificate obtained successfully!"
        return 0
    else
        echo "Failed to obtain certificate"
        return 1
    fi
}

# Check if we need to obtain certificates
if ! check_certificates || [ "$FORCE_RENEWAL" = "true" ]; then
    # Generate self-signed certificate first
    generate_self_signed
    
    # Start nginx with self-signed certificate
    echo "Starting Nginx with self-signed certificate..."
    nginx
    
    # Wait a bit for nginx to start
    sleep 5
    
    # Try to obtain real certificate
    if obtain_certificate; then
        echo "Reloading Nginx with new certificate..."
        nginx -s reload
    else
        echo "WARNING: Using self-signed certificate. Please check your DNS settings."
    fi
else
    echo "Certificates already exist, starting Nginx..."
    nginx
fi

# Start cron for automatic renewal
crond

# Keep the container running
tail -f /var/log/nginx/access.log /var/log/nginx/error.log