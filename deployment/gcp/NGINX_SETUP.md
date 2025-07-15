# Nginx Setup for NexusDocs360 PRE Environment

## Overview
This document describes the nginx proxy setup for the PRE environment, which handles SSL termination and routing for:
- `pre.nexusdocs360.com` - Redirects to app
- `pre.nexusdocs360.com` - Frontend application  
- `pre-api.nexusdocs360.com` - Backend API

## Scripts

### 1. Main Startup Script
**File**: `nginx-vm-startup-pre.sh`

This is the main script that runs when the VM starts. It:
1. Installs nginx and certbot
2. Creates HTTP configuration for certificate generation
3. Obtains SSL certificates from Let's Encrypt
4. Configures HTTPS with proper SSL settings
5. Sets up automatic certificate renewal

### 2. Quick Fix Script
**File**: `scripts/nginx-quick-fix.sh`

Use this to fix common configuration issues without reinstalling:
```bash
# Basic fix
sudo ./nginx-quick-fix.sh

# Fix with cleanup of old configs
sudo ./nginx-quick-fix.sh --clean
```

### 3. Clean Reinstall Script
**File**: `scripts/nginx-clean-reinstall.sh`

Use this when you need to start completely fresh:
```bash
sudo ./nginx-clean-reinstall.sh
```

This will:
- Backup existing configurations
- Remove all site configurations
- Create a basic HTTP setup
- Prepare for SSL certificate generation

## Common Issues and Solutions

### Issue 1: "invalid condition "$request_method""
**Cause**: Escaped variables in nginx configuration
**Fix**: 
```bash
sudo sed -i 's/\\$request_method/$request_method/g' /etc/nginx/sites-*/api-pre.conf
```

### Issue 2: "invalid number of arguments in proxy_pass"
**Cause**: Empty Cloud Run URLs
**Fix**:
```bash
# Use localhost as placeholder
sudo sed -i 's|proxy_pass ;|proxy_pass http://localhost:3000;|g' /etc/nginx/sites-*/app-pre.conf
sudo sed -i 's|proxy_pass ;|proxy_pass http://localhost:8000;|g' /etc/nginx/sites-*/api-pre.conf

# After Cloud Run deployment
sudo /usr/local/bin/update-cloudrun-urls.sh
```

### Issue 3: Conflicting site configurations
**Fix**: Clean and reinstall
```bash
sudo ./scripts/nginx-clean-reinstall.sh
```

## Deployment Flow

### For New VM Setup
1. VM starts with startup script automatically
2. Script configures nginx with HTTP first
3. Obtains SSL certificates
4. Configures HTTPS
5. Uses localhost URLs until Cloud Run services are deployed

### For Existing VM with Issues
1. SSH into the VM:
   ```bash
   gcloud compute ssh nginx-proxy-pre --zone=europe-west1-b
   ```

2. Apply quick fix:
   ```bash
   sudo /tmp/nginx-quick-fix.sh
   ```

3. Or do clean reinstall:
   ```bash
   sudo /tmp/nginx-clean-reinstall.sh
   ```

### After Cloud Run Deployment
Update nginx with actual Cloud Run URLs:
```bash
sudo /usr/local/bin/update-cloudrun-urls.sh
```

## Monitoring

Check nginx health:
```bash
sudo /usr/local/bin/check-nginx-health.sh
```

View logs:
```bash
# Startup log
sudo tail -f /var/log/nginx-startup.log

# Access logs
sudo tail -f /var/log/nginx/pre-app-access.log
sudo tail -f /var/log/nginx/pre-api-access.log

# Error logs
sudo tail -f /var/log/nginx/error.log
```

## SSL Certificate Management

Certificates are automatically renewed via systemd timer. To manually renew:
```bash
sudo certbot renew
sudo systemctl reload nginx
```

Check certificate status:
```bash
sudo certbot certificates
```

## Important Notes

1. **Order matters**: Always configure HTTP first, then obtain certificates, then configure HTTPS
2. **Cloud Run URLs**: The script uses localhost as default if Cloud Run services aren't deployed yet
3. **Certificate domains**: All three subdomains (pre, pre, pre-api) share the same certificate
4. **Cleanup**: Always remove old configurations before applying new ones to avoid conflicts