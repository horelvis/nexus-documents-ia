# PRE Environment Deployment Guide - NexusDocs360

This guide covers the complete setup and deployment process for the PRE (Pre-Production) environment of NexusDocs360.

## 🚀 Quick Start

```bash
# Complete deployment with one command
cd deployment/gcp/scripts
./deploy-pre-complete.sh
```

Select option 1 for full deployment or choose specific steps as needed.

## 📋 Table of Contents

1. [Infrastructure Overview](#infrastructure-overview)
2. [Domain Configuration](#domain-configuration)
3. [GitHub Actions Setup](#github-actions-setup)
4. [Nginx Configuration](#nginx-configuration)
5. [SSL Certificates](#ssl-certificates)
6. [Deployment Process](#deployment-process)
7. [Monitoring and Troubleshooting](#monitoring-and-troubleshooting)

## 🏗️ Infrastructure Overview

### PRE Environment Details
- **Project ID**: nexusdocs360-pre
- **Region**: europe-west1
- **Zone**: europe-west1-b
- **Domain**: nexusdocs360.app

### Resources Created
| Resource | Name | Type | Details |
|----------|------|------|---------|
| VPC | nexus-vpc-pre | Custom VPC | 10.1.0.0/24 |
| Database | nexus-db-pre | Cloud SQL PostgreSQL | db-f1-micro |
| Cache | nexus-redis-pre | Memorystore Redis | 1GB |
| Vector DB | weaviate-pre | Compute Engine | e2-small |
| Proxy | nginx-proxy-pre | Compute Engine | e2-small, IP: 34.78.30.77 |
| Registry | nexusdocs360-pre | Artifact Registry | Docker images |

### Estimated Costs
- **Total**: ~$200-250/month
- **Capacity**: 50% of production

## 🌐 Domain Configuration

### URLs
- **Frontend**: https://pre.nexusdocs360.app
- **API**: https://pre-api.nexusdocs360.app
- **API Documentation**: https://pre-api.nexusdocs360.app/docs

### DNS Records (GoDaddy)
Configure these A records in your GoDaddy DNS management panel:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | pre | 34.78.30.77 | 600 |
| A | pre-api | 34.78.30.77 | 600 |

### DNS Verification
```bash
# Verify DNS propagation
dig pre.nexusdocs360.app
dig pre-api.nexusdocs360.app

# Test connectivity
curl -I https://pre.nexusdocs360.app
curl -I https://pre-api.nexusdocs360.app
```

## 🔧 GitHub Actions Setup

### 1. Create Service Account (Automated)
```bash
# Run the automated script
cd deployment/gcp/scripts
./setup-github-actions-pre.sh
```

This script will:
- Create the service account
- Grant all necessary IAM roles
- Generate the service account key
- Provide instructions for adding to GitHub

### Manual Steps (if needed)
<details>
<summary>Click to see manual commands</summary>

```bash
# Set project
PROJECT_ID=nexusdocs360-pre

# Create service account
gcloud iam service-accounts create github-actions-pre \
    --display-name="GitHub Actions PRE Deploy" \
    --project=$PROJECT_ID

# Set email variable
SA_EMAIL=github-actions-pre@${PROJECT_ID}.iam.gserviceaccount.com

# Grant necessary roles
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/artifactregistry.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/iam.serviceAccountUser"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/compute.instanceAdmin.v1"

# Generate key
gcloud iam service-accounts keys create ~/github-actions-pre-key.json \
    --iam-account=${SA_EMAIL} \
    --project=$PROJECT_ID
```
</details>

### 2. Configure GitHub Secret
1. Go to your GitHub repository
2. Navigate to: Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Name: `GCP_SA_KEY_PRE`
5. Value: Contents of `~/github-actions-pre-key.json`

```bash
# Display key content to copy
cat ~/github-actions-pre-key.json
```

### 3. Workflow File
The workflow is located at `.github/workflows/deploy-pre.yml` and triggers on:
- Push to `pre` branch
- Manual workflow dispatch

## 🔒 Nginx Configuration

### Automated Configuration
```bash
# Copy and run the configuration script
cd deployment/gcp/scripts
gcloud compute scp configure-nginx-pre.sh nginx-proxy-pre:~/ --zone=europe-west1-b --project=nexusdocs360-pre
gcloud compute ssh nginx-proxy-pre --zone=europe-west1-b --project=nexusdocs360-pre
sudo ~/configure-nginx-pre.sh
```

### Manual Configuration
<details>
<summary>Click to see manual steps</summary>

#### 1. Connect to Nginx Server
```bash
gcloud compute ssh nginx-proxy-pre \
    --zone=europe-west1-b \
    --project=nexusdocs360-pre
```

#### 2. Configure Nginx Sites
```bash
# Create site configuration
sudo tee /etc/nginx/sites-available/nexusdocs360-pre <<'EOF'
# HTTP to HTTPS redirect
server {
    listen 80;
    server_name pre.nexusdocs360.app pre-api.nexusdocs360.app;
    
    location / {
        return 301 https://$host$request_uri;
    }
}

# Frontend - pre.nexusdocs360.app
server {
    listen 443 ssl http2;
    server_name pre.nexusdocs360.app;
    
    ssl_certificate /etc/letsencrypt/live/pre.nexusdocs360.app/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pre.nexusdocs360.app/privkey.pem;
    
    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    location / {
        proxy_pass https://nexus-frontend-pre-xxxxx-ew.a.run.app;
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
    
    ssl_certificate /etc/letsencrypt/live/pre.nexusdocs360.app/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pre.nexusdocs360.app/privkey.pem;
    
    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # CORS headers for API
    add_header Access-Control-Allow-Origin "https://pre.nexusdocs360.app" always;
    add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, Content-Type" always;
    
    location / {
        proxy_pass https://nexus-backend-pre-xxxxx-ew.a.run.app;
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
sudo ln -sf /etc/nginx/sites-available/nexusdocs360-pre /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

### 3. Update Cloud Run URLs
After deployment, update the proxy_pass URLs with actual Cloud Run endpoints:
```bash
# Get Cloud Run URLs
BACKEND_URL=$(gcloud run services describe nexus-backend-pre --region=europe-west1 --format='value(status.url)')
FRONTEND_URL=$(gcloud run services describe nexus-frontend-pre --region=europe-west1 --format='value(status.url)')

# Update Nginx configuration with actual URLs
sudo sed -i "s|https://nexus-frontend-pre-xxxxx-ew.a.run.app|$FRONTEND_URL|g" /etc/nginx/sites-available/nexusdocs360-pre
sudo sed -i "s|https://nexus-backend-pre-xxxxx-ew.a.run.app|$BACKEND_URL|g" /etc/nginx/sites-available/nexusdocs360-pre

# Reload Nginx
sudo nginx -t && sudo systemctl reload nginx
```

## 🔐 SSL Certificates

### Generate Let's Encrypt Certificates
```bash
# Install Certbot if not already installed
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx

# Generate certificates
sudo certbot --nginx \
    -d pre.nexusdocs360.app \
    -d pre-api.nexusdocs360.app \
    --email admin@nexusdocs360.app \
    --agree-tos \
    --no-eff-email
```

### Auto-renewal
Certbot automatically sets up renewal. Verify with:
```bash
sudo certbot renew --dry-run
```

## 🚀 Deployment Process

### 1. Initial Setup
```bash
# Clone repository
git clone https://github.com/your-org/nexus-document-backend.git
cd nexus-document-backend

# Create PRE branch
git checkout -b pre

# Push to trigger deployment
git push -u origin pre
```

### 2. Manual Deployment
```bash
# Using GitHub Actions
# Go to Actions tab → Deploy to PRE Environment → Run workflow

# Using gcloud CLI
gcloud builds submit --config=deployment/gcp/cloudbuild-pre.yaml --project=nexusdocs360-pre
```

### 3. Update Secrets from .env
```bash
cd deployment/gcp/scripts
./update-secrets-from-env.sh pre
```

## 📊 Monitoring and Troubleshooting

### View Logs
```bash
# Cloud Run logs
gcloud run logs read --service=nexus-backend-pre --project=nexusdocs360-pre
gcloud run logs read --service=nexus-frontend-pre --project=nexusdocs360-pre

# Nginx logs
gcloud compute ssh nginx-proxy-pre --zone=europe-west1-b --command="sudo tail -f /var/log/nginx/error.log"
```

### Check Service Status
```bash
# List all Cloud Run services
gcloud run services list --project=nexusdocs360-pre

# Check specific service
gcloud run services describe nexus-backend-pre --region=europe-west1 --project=nexusdocs360-pre
```

### Database Connection
```bash
# Using Cloud SQL Proxy
./cloud-sql-proxy --port=5432 nexusdocs360-pre:europe-west1:nexus-db-pre

# Connect with psql
psql -h localhost -U nexus_user_pre -d nexusdocs360_pre
```

### Common Issues

#### DNS Not Resolving
- Wait 5-30 minutes for DNS propagation
- Verify records in GoDaddy dashboard
- Use `dig` or `nslookup` to check

#### SSL Certificate Issues
- Ensure domains point to correct IP before generating certificates
- Check certificate status: `sudo certbot certificates`
- Renew manually if needed: `sudo certbot renew`

#### 502 Bad Gateway
- Check Cloud Run service is running
- Verify Nginx proxy_pass URLs are correct
- Check VPC connector configuration

#### Database Connection Failed
- Verify database secret is correct
- Check VPC connector is attached to Cloud Run
- Ensure database is running: `gcloud sql instances list`

## 🔄 Updates and Maintenance

### Update Application
1. Push changes to `pre` branch
2. GitHub Actions will automatically deploy

### Update Infrastructure
```bash
cd deployment/gcp/scripts
./deploy-infrastructure-pre.sh
```

### Update Secrets
```bash
cd deployment/gcp/scripts
./update-secrets-from-env.sh pre
```

### Backup Database
```bash
# Create on-demand backup
gcloud sql backups create \
    --instance=nexus-db-pre \
    --project=nexusdocs360-pre
```

## 📝 Notes

- PRE environment uses test API keys (Stripe, etc.)
- Database is automatically backed up daily at 03:00
- SSL certificates auto-renew every 90 days
- All services are configured with minimal resources to reduce costs
- Access is not restricted by IP (configure firewall rules if needed)

## 🆘 Support

For issues or questions:
1. Check logs first
2. Verify DNS and SSL configuration
3. Ensure all secrets are properly configured
4. Check GitHub Actions workflow status