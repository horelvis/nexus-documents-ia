# Nginx with Certbot for SSL certificate generation
FROM nginx:alpine

# Install certbot and dependencies
RUN apk add --no-cache \
    certbot \
    certbot-nginx \
    openssl \
    bash \
    curl

# Create necessary directories
RUN mkdir -p /var/www/certbot /etc/letsencrypt

# Copy nginx configuration
COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/conf.d/ /etc/nginx/templates/

# Install envsubst for template processing
RUN apk add --no-cache gettext

# Copy scripts
COPY nginx/scripts/ssl-renewal.sh /usr/local/bin/ssl-renewal.sh
COPY nginx/scripts/process-templates.sh /usr/local/bin/process-templates.sh
COPY nginx/scripts/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /usr/local/bin/ssl-renewal.sh /usr/local/bin/process-templates.sh /docker-entrypoint.sh

# Create cron job for certificate renewal
RUN echo "0 0,12 * * * /usr/local/bin/ssl-renewal.sh >> /var/log/cron.log 2>&1" | crontab -

# Expose ports
EXPOSE 80 443

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost/nginx-health || exit 1

# Custom entrypoint to handle SSL setup
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]