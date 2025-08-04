# 🔐 GitHub Secrets Configuration Guide

## Required Secrets for CI/CD Pipeline

Configure estos secretos en GitHub: **Settings → Secrets and variables → Actions**

### 🔑 Google Cloud Platform
```bash
# Service Account Key (JSON completo)
GCP_SA_KEY

# Project ID
GCP_PROJECT_ID
```

### 🔐 Database & Storage
```bash
# PostgreSQL Connection String
DATABASE_URL="postgresql://user:pass@host:5432/dbname"

# Redis Host
REDIS_HOST="redis-instance-host"

# GCS Credentials (JSON)
GCS_CREDENTIALS
```

### 🎫 Authentication Services
```bash
# Clerk Auth
CLERK_SECRET_KEY
CLERK_PUBLISHABLE_KEY
CLERK_JWT_VERIFICATION_KEY

# Stripe Payments
STRIPE_SECRET_KEY
STRIPE_PUBLIC_KEY
STRIPE_WEBHOOK_SECRET
STRIPE_PRO_PRICE_ID
STRIPE_ENTERPRISE_PRICE_ID
```

### 🔒 Security Keys
```bash
# API Keys
MICROSERVICES_API_KEY="generate-secure-key-here"
SIGNATURE_ENCRYPTION_KEY="generate-secure-key-here"

# JWT Secret
SECRET_KEY="generate-secure-jwt-secret"
```

### 📢 Monitoring & Notifications
```bash
# Slack Webhook (Optional)
SLACK_WEBHOOK_URL

# SonarCloud (Optional)
SONAR_TOKEN
```

## 🛠️ How to Generate Secure Keys

### Generate API Keys
```bash
# Using OpenSSL
openssl rand -hex 32

# Using Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Using Node.js
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

### Create GCP Service Account
```bash
# 1. Create service account
gcloud iam service-accounts create nexus-deploy \
  --description="Service account for GitHub Actions deployment" \
  --display-name="GitHub Actions Deploy"

# 2. Grant necessary roles
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:nexus-deploy@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:nexus-deploy@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:nexus-deploy@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

# 3. Create and download key
gcloud iam service-accounts keys create key.json \
  --iam-account=nexus-deploy@PROJECT_ID.iam.gserviceaccount.com

# 4. Copy the content of key.json to GCP_SA_KEY secret
cat key.json | pbcopy  # macOS
cat key.json | xclip   # Linux
```

### Create Google Secret Manager Secrets
```bash
# Create secrets in GCP for runtime access
gcloud secrets create database-url --data-file=- <<< "postgresql://..."
gcloud secrets create redis-host --data-file=- <<< "redis-host"
gcloud secrets create clerk-secret-key --data-file=- <<< "your-clerk-key"
gcloud secrets create stripe-secret-key --data-file=- <<< "your-stripe-key"
gcloud secrets create microservices-api-key --data-file=- <<< "generated-key"
gcloud secrets create signature-encryption-key --data-file=- <<< "generated-key"
gcloud secrets create gcs-credentials --data-file=credentials.json
```

## 📋 Verification Checklist

- [ ] GCP_SA_KEY configured with proper JSON
- [ ] GCP_PROJECT_ID matches your GCP project
- [ ] DATABASE_URL points to production database
- [ ] All Clerk keys are from production environment
- [ ] Stripe keys are from live mode (not test)
- [ ] Generated secure random keys for APIs
- [ ] Created all secrets in Google Secret Manager
- [ ] Service account has necessary IAM roles
- [ ] Slack webhook configured (optional)

## 🚨 Security Best Practices

1. **Rotate keys regularly** (every 90 days)
2. **Use different keys** for staging/production
3. **Never commit secrets** to repository
4. **Limit secret access** to necessary workflows
5. **Use secret scanning** tools
6. **Monitor secret usage** in audit logs

## 🔄 Secret Rotation Process

1. Generate new secret value
2. Update in Google Secret Manager (create new version)
3. Update GitHub secret
4. Deploy application to use new secret
5. Wait for all instances to update
6. Delete old secret version

## 📝 Environment-Specific Secrets

### Staging Environment
```bash
# Prefix with STAGING_
STAGING_DATABASE_URL
STAGING_STRIPE_SECRET_KEY
# etc...
```

### Production Environment
```bash
# Prefix with PROD_
PROD_DATABASE_URL
PROD_STRIPE_SECRET_KEY
# etc...
```

## 🆘 Troubleshooting

### Secret not accessible in workflow
- Check secret name matches exactly
- Verify secret is in correct environment
- Ensure workflow has permission to access secrets

### Authentication failures
- Regenerate service account key
- Verify IAM roles are correct
- Check secret format (no extra spaces/newlines)

### Connection errors
- Verify DATABASE_URL format
- Check network connectivity
- Ensure services are accessible from Cloud Run