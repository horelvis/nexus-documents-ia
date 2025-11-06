#!/bin/bash
# Setup secrets for NexusDocs360 PRODUCTION environment
# This script creates all necessary secrets with production-grade security

set -e

# Load environment variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/../load-env.sh"

PROJECT_ID=${GCP_PROJECT_ID:-nexusdocs360-prod}
REGION=${GCP_REGION:-europe-west1}

echo "🔐 Setting up secrets for PRODUCTION environment: $PROJECT_ID"
echo "⚠️  WARNING: This is PRODUCTION - Use real, secure values!"
echo ""

# Enable Secret Manager API
echo "📡 Enabling Secret Manager API..."
gcloud services enable secretmanager.googleapis.com --project=$PROJECT_ID

# Function to create or update secret
create_secret() {
    SECRET_NAME=$1
    SECRET_VALUE=$2
    
    if gcloud secrets describe $SECRET_NAME --project=$PROJECT_ID &>/dev/null; then
        echo "Updating secret: $SECRET_NAME"
        echo -n "$SECRET_VALUE" | gcloud secrets versions add $SECRET_NAME --data-file=- --project=$PROJECT_ID
    else
        echo "Creating secret: $SECRET_NAME"
        echo -n "$SECRET_VALUE" | gcloud secrets create $SECRET_NAME --data-file=- --replication-policy="user-managed" --locations="$REGION" --project=$PROJECT_ID
    fi
}

# Database secrets (PROD specific - strong passwords)
echo "🗄️ Setting up database secrets..."
create_secret "db-user-prod" "nexus_user_prod"
create_secret "db-pass-prod" "$(openssl rand -base64 32 | tr -d '/+' | cut -c1-32)"
create_secret "db-host-prod" "10.0.0.3"  # Will be updated after Cloud SQL creation
create_secret "db-name-prod" "nexusdocs360_prod"

# Application secrets (PROD - extra strong)
echo "🔑 Setting up application secrets..."
create_secret "secret-key-prod" "$(openssl rand -base64 64)"
create_secret "microservices-api-key-prod" "$(openssl rand -hex 32)"
create_secret "signature-encryption-key-prod" "$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

# Redis URL (will be updated with auth string after creation)
echo "💾 Setting up Redis secrets..."
create_secret "redis-url-prod" "redis://10.0.0.4:6379"

# AI Service Keys (PRODUCTION keys)
echo "🤖 Setting up AI service secrets..."
echo "⚠️  IMPORTANT: Update these with your PRODUCTION API keys!"
create_secret "openai-api-key-prod" "REPLACE_WITH_PRODUCTION_OPENAI_KEY"
create_secret "anthropic-api-key-prod" "REPLACE_WITH_PRODUCTION_ANTHROPIC_KEY"
create_secret "huggingface-token-prod" "REPLACE_WITH_PRODUCTION_HF_TOKEN"

# External service keys (PRODUCTION versions)
echo "🌐 Setting up external service secrets..."
echo "⚠️  CRITICAL: These must be PRODUCTION keys, not test keys!"
create_secret "clerk-secret-prod" "REPLACE_WITH_CLERK_PRODUCTION_SECRET_KEY"
create_secret "clerk-jwt-key-prod" "REPLACE_WITH_CLERK_PRODUCTION_JWT_PUBLIC_KEY"
create_secret "clerk-publishable-key-prod" "REPLACE_WITH_CLERK_PRODUCTION_PUBLISHABLE_KEY"
create_secret "stripe-secret-prod" "REPLACE_WITH_STRIPE_LIVE_SECRET_KEY"
create_secret "stripe-publishable-key-prod" "REPLACE_WITH_STRIPE_LIVE_PUBLISHABLE_KEY"
create_secret "stripe-webhook-secret-prod" "REPLACE_WITH_STRIPE_PRODUCTION_WEBHOOK_SECRET"
create_secret "sendgrid-api-key-prod" "REPLACE_WITH_SENDGRID_PRODUCTION_API_KEY"

# GCS credentials (PROD bucket)
echo "☁️ Setting up GCS credentials..."
if [ -f "../../../credentials/nexusdocs360-prod-gcs.json" ]; then
    gcloud secrets create gcs-credentials-prod --data-file=../../../credentials/nexusdocs360-prod-gcs.json --project=$PROJECT_ID || \
    gcloud secrets versions add gcs-credentials-prod --data-file=../../../credentials/nexusdocs360-prod-gcs.json --project=$PROJECT_ID
else
    echo "⚠️  GCS credentials file not found. Creating placeholder..."
    create_secret "gcs-credentials-prod" "{}"
fi

# Monitoring and alerting (PRODUCTION)
echo "📊 Setting up monitoring secrets..."
create_secret "slack-webhook-prod" "REPLACE_WITH_SLACK_PRODUCTION_WEBHOOK_URL"
create_secret "slack-webhook-critical" "REPLACE_WITH_SLACK_CRITICAL_WEBHOOK_URL"
create_secret "pagerduty-key-prod" "REPLACE_WITH_PAGERDUTY_INTEGRATION_KEY"
create_secret "datadog-api-key" "REPLACE_WITH_DATADOG_API_KEY"

# Feature flags (PRODUCTION settings)
echo "🚩 Setting up feature flags..."
create_secret "feature-flags-prod" '{
  "ai_agents": true,
  "advanced_analytics": true,
  "experimental": false,
  "maintenance_mode": false,
  "rate_limiting": true,
  "premium_features": true
}'

# Security tokens
echo "🛡️ Setting up security tokens..."
create_secret "csrf-secret-prod" "$(openssl rand -hex 32)"
create_secret "jwt-secret-prod" "$(openssl rand -base64 64)"
create_secret "api-rate-limit-secret" "$(openssl rand -hex 16)"

# Backup encryption key
echo "💾 Setting up backup encryption..."
create_secret "backup-encryption-key-prod" "$(openssl rand -base64 32)"

# OAuth tokens (if using social auth)
echo "🔐 Setting up OAuth secrets..."
create_secret "google-oauth-client-id" "REPLACE_WITH_GOOGLE_CLIENT_ID"
create_secret "google-oauth-client-secret" "REPLACE_WITH_GOOGLE_CLIENT_SECRET"
create_secret "github-oauth-client-id" "REPLACE_WITH_GITHUB_CLIENT_ID"
create_secret "github-oauth-client-secret" "REPLACE_WITH_GITHUB_CLIENT_SECRET"

# Database connection strings
echo "🔗 Creating connection string secrets..."
DB_USER=$(gcloud secrets versions access latest --secret=db-user-prod --project=$PROJECT_ID)
DB_PASS=$(gcloud secrets versions access latest --secret=db-pass-prod --project=$PROJECT_ID)
DB_HOST=$(gcloud secrets versions access latest --secret=db-host-prod --project=$PROJECT_ID)
DB_NAME=$(gcloud secrets versions access latest --secret=db-name-prod --project=$PROJECT_ID)

create_secret "database-url-prod" "postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}:5432/${DB_NAME}?sslmode=require"
create_secret "async-database-url-prod" "postgresql+asyncpg://${DB_USER}:${DB_PASS}@${DB_HOST}:5432/${DB_NAME}?ssl=require"

# Grant access to service account
echo "👤 Granting secret access to service account..."
SERVICE_ACCOUNT="nexus-cloud-run-prod@${PROJECT_ID}.iam.gserviceaccount.com"

# Create service account if it doesn't exist
gcloud iam service-accounts create nexus-cloud-run-prod \
    --display-name="NexusDocs360 PROD Cloud Run Service Account" \
    --project=$PROJECT_ID || true

# Grant secret accessor role
echo "Granting access to all secrets..."
for secret in $(gcloud secrets list --project=$PROJECT_ID --format="value(name)"); do
    gcloud secrets add-iam-policy-binding $secret \
        --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role="roles/secretmanager.secretAccessor" \
        --project=$PROJECT_ID --quiet
done

# Grant other necessary roles
echo "🎯 Granting additional roles for PRODUCTION..."
ROLES=(
    "roles/cloudsql.client"
    "roles/storage.objectAdmin"
    "roles/redis.editor"
    "roles/monitoring.metricWriter"
    "roles/cloudtrace.agent"
    "roles/logging.logWriter"
    "roles/cloudkms.cryptoKeyEncrypterDecrypter"
)

for role in "${ROLES[@]}"; do
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role="$role" \
        --quiet
done

# Create a secrets validation file
cat > /tmp/prod-secrets-checklist.txt << EOF
PRODUCTION SECRETS CHECKLIST
============================

❗ CRITICAL: Update these secrets with PRODUCTION values before deploying:

AI Services:
□ openai-api-key-prod - Production OpenAI API key
□ anthropic-api-key-prod - Production Anthropic API key
□ huggingface-token-prod - Production HuggingFace token

Authentication:
□ clerk-secret-prod - Clerk production secret key
□ clerk-jwt-key-prod - Clerk production JWT public key
□ clerk-publishable-key-prod - Clerk production publishable key

Payments:
□ stripe-secret-prod - Stripe LIVE secret key (starts with sk_live_)
□ stripe-publishable-key-prod - Stripe LIVE publishable key
□ stripe-webhook-secret-prod - Stripe production webhook secret

Communication:
□ sendgrid-api-key-prod - SendGrid production API key

Monitoring:
□ slack-webhook-prod - Slack webhook for production alerts
□ slack-webhook-critical - Slack webhook for critical alerts
□ pagerduty-key-prod - PagerDuty integration key
□ datadog-api-key - Datadog API key (optional)

OAuth (if using):
□ google-oauth-client-id - Google OAuth client ID
□ google-oauth-client-secret - Google OAuth client secret
□ github-oauth-client-id - GitHub OAuth client ID
□ github-oauth-client-secret - GitHub OAuth client secret

Database:
□ db-host-prod - Will be auto-updated after Cloud SQL creation
□ redis-url-prod - Will be auto-updated after Redis creation

To update a secret:
gcloud secrets versions add SECRET_NAME --data-file=- --project=$PROJECT_ID

Example:
echo -n "sk_live_..." | gcloud secrets versions add stripe-secret-prod --data-file=- --project=$PROJECT_ID
EOF

echo "✅ PRODUCTION Secrets setup complete!"
echo ""
echo "📋 Checklist saved to: /tmp/prod-secrets-checklist.txt"
echo ""
echo "⚠️  CRITICAL ACTIONS REQUIRED:"
echo "1. Review the checklist at /tmp/prod-secrets-checklist.txt"
echo "2. Update ALL placeholder secrets with PRODUCTION values"
echo "3. Verify all API keys are for PRODUCTION (not test/development)"
echo "4. Ensure strong passwords are used"
echo "5. Enable secret versioning and rotation policies"
echo ""
echo "🔒 Security Recommendations:"
echo "- Enable VPC Service Controls"
echo "- Set up secret rotation schedules"
echo "- Configure access logs for secret access"
echo "- Use Cloud KMS for additional encryption"
echo "- Implement least-privilege access policies"