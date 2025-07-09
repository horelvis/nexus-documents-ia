#!/bin/bash
# SSL Certificate Renewal Script

DOMAIN=${DOMAIN:-nexusdocs.com}
EMAIL=${EMAIL:-admin@nexusdocs.com}

echo "[$(date)] Starting SSL renewal check for $DOMAIN"

# Check if renewal is needed (certbot handles this automatically)
certbot renew --quiet --no-self-upgrade

# Check if renewal was successful
if [ $? -eq 0 ]; then
    echo "[$(date)] SSL renewal check completed successfully"
    
    # Check if nginx needs to be reloaded
    if [ -f /var/run/nginx.pid ]; then
        # Get current certificate modification time
        CERT_TIME=$(stat -c %Y /etc/letsencrypt/live/$DOMAIN/fullchain.pem 2>/dev/null || echo 0)
        CURRENT_TIME=$(date +%s)
        TIME_DIFF=$((CURRENT_TIME - CERT_TIME))
        
        # If certificate was modified in the last 5 minutes, reload nginx
        if [ $TIME_DIFF -lt 300 ]; then
            echo "[$(date)] Certificate was renewed, reloading Nginx..."
            nginx -s reload
        fi
    fi
else
    echo "[$(date)] SSL renewal check failed!"
fi