# GCP Deployment Scripts

This directory contains the main deployment scripts for NouxCubeIA on Google Cloud Platform.

## Main Deployment Scripts

### 1. `setup-cloudsql-database.sh`
Sets up Cloud SQL PostgreSQL instance and database with all required configurations.
- Creates Cloud SQL instance (if not exists)
- Creates database
- Sets up all database-related secrets
- Configures permissions

**Usage:**
```bash
./setup-cloudsql-database.sh
```

### 2. `setup-all-secrets.sh`
Creates all application secrets in Secret Manager (except database secrets).
- Application secret key
- Redis configuration
- GCS bucket name
- Clerk authentication
- Stripe payments
- Email configuration

**Usage:**
```bash
./setup-all-secrets.sh
```

### 3. `deploy-backend-cloudrun.sh`
Deploys the backend service to Cloud Run with all configurations.
- Sets up service account with required permissions
- Deploys with 8GB RAM and 4 CPUs
- Configures all environment variables and secrets
- Sets up Cloud SQL connection
- Tests the deployment

**Usage:**
```bash
./deploy-backend-cloudrun.sh
```

### 4. `setup-nginx-proxy.sh`
Configures Nginx reverse proxy with SSL certificates.
- Installs Nginx and Certbot
- Configures proxy for frontend and API
- Obtains Let's Encrypt SSL certificates
- Sets up auto-renewal

**Usage:**
```bash
# Run this on the nginx VM
./setup-nginx-proxy.sh
```

### 5. `validate-deployment.sh`
Validates the complete deployment.
- Checks all Google Cloud services
- Tests direct endpoints
- Tests domain endpoints
- Validates SSL certificates
- Checks for recent errors

**Usage:**
```bash
./validate-deployment.sh
```

## Deployment Order

For a fresh deployment, run the scripts in this order:

1. **Database Setup**
   ```bash
   ./setup-cloudsql-database.sh
   ```

2. **Application Secrets**
   ```bash
   ./setup-all-secrets.sh
   ```

3. **Backend Deployment**
   ```bash
   ./deploy-backend-cloudrun.sh
   ```

4. **Nginx Proxy** (on the VM)
   ```bash
   ./setup-nginx-proxy.sh
   ```

5. **Validation**
   ```bash
   ./validate-deployment.sh
   ```

## Environment Variables

The scripts use these default values:
- Project ID: `nexusdocs360-pre`
- Region: `europe-west1`
- Service Name: `nexus-backend-pre`
- Domain: `nexusdocs360.app`

## Prerequisites

- Google Cloud SDK installed and authenticated
- Appropriate IAM permissions
- DNS records configured for your domain
- Docker images built and pushed to Artifact Registry (via GitHub Actions)

## Troubleshooting

### Backend not starting
- Check logs: `gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=nexus-backend-pre" --project=nexusdocs360-pre --limit=50`
- Verify all secrets exist: `gcloud secrets list --project=nexusdocs360-pre --filter="name:pre"`

### SSL certificate issues
- Ensure DNS A records point to nginx VM IP
- Wait for DNS propagation (can take up to 48 hours)
- Check nginx logs: `sudo tail -f /var/log/nginx/error.log`

### Database connection issues
- Verify Cloud SQL instance is running
- Check if secrets are correctly configured
- Ensure Cloud Run service has Cloud SQL connection enabled

## Additional Scripts

Other scripts in this directory:
- `deploy-infrastructure-*.sh` - Complete infrastructure deployment
- `enable-apis.sh` - Enable required Google Cloud APIs
- `configure-nginx-pre.sh` - Detailed nginx configuration
- `check-gcp-services.sh` - Check status of GCP services