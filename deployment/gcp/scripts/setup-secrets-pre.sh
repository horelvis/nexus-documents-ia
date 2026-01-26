#!/bin/bash
# Setup secrets for NouxCubeIA PRE environment

set -e

# Load environment variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/../load-env.sh"

PROJECT_ID=${GCP_PROJECT_ID:-nexusdocs360-pre}
REGION=${GCP_REGION:-europe-west1}

echo "🔐 Setting up secrets for PRE environment: $PROJECT_ID"

# Enable Secret Manager API
echo "📡 Enabling Secret Manager API..."
gcloud services enable secretmanager.googleapis.com --project=$PROJECT_ID

# Function to create or update secret
create_secret() {
    SECRET_NAME=$1
    SECRET_VALUE=$2
    
    # Validate secret value is not empty
    if [ -z "$SECRET_VALUE" ]; then
        echo "❌ Error: Empty value for secret $SECRET_NAME"
        return 1
    fi
    
    if gcloud secrets describe $SECRET_NAME --project=$PROJECT_ID &>/dev/null; then
        echo "Updating secret: $SECRET_NAME"
        echo -n "$SECRET_VALUE" | gcloud secrets versions add $SECRET_NAME --data-file=- --project=$PROJECT_ID
    else
        echo "Creating secret: $SECRET_NAME"
        echo -n "$SECRET_VALUE" | gcloud secrets create $SECRET_NAME --data-file=- --project=$PROJECT_ID
    fi
}

# Database secrets (PRE specific)
echo "🗄️ Setting up database secrets..."
create_secret "db-user-pre" "nexus_user_pre"
create_secret "db-pass-pre" "$(openssl rand -base64 32)"
create_secret "db-host-pre" "10.1.0.3"  # Will be updated after Cloud SQL creation
create_secret "db-name-pre" "nexusdocs360_pre"

# Application secrets
echo "🔑 Setting up application secrets..."
create_secret "secret-key-pre" "$(openssl rand -base64 64)"
create_secret "microservices-api-key-pre" "$(openssl rand -hex 32)"
create_secret "storage-api-key-pre" "$(openssl rand -hex 32)"
# Generate signature encryption key (check if cryptography is installed)
if python3 -c "import cryptography" 2>/dev/null; then
    SIGNATURE_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
else
    echo "⚠️  Python cryptography module not found. Generating alternative key..."
    SIGNATURE_KEY=$(openssl rand -base64 32)
fi
create_secret "signature-encryption-key-pre" "$SIGNATURE_KEY"

# Redis URL
echo "💾 Setting up Redis secrets..."
create_secret "redis-url-pre" "redis://10.1.0.4:6379"

# AI Service Keys (can be shared with prod or separate)
echo "🤖 Setting up AI service secrets..."
create_secret "openai-api-key-pre" "REPLACE_WITH_OPENAI_KEY"
create_secret "anthropic-api-key-pre" "REPLACE_WITH_ANTHROPIC_KEY"
create_secret "huggingface-token-pre" "REPLACE_WITH_HF_TOKEN"
create_secret "xai-api-key-pre" "REPLACE_WITH_XAI_KEY"

# External service keys (PRE versions)
echo "🌐 Setting up external service secrets..."
create_secret "clerk-secret-pre" "REPLACE_WITH_CLERK_SECRET_KEY"
create_secret "clerk-jwt-key-pre" "REPLACE_WITH_CLERK_JWT_PUBLIC_KEY"
create_secret "clerk-publishable-key-pre" "REPLACE_WITH_CLERK_PUBLISHABLE_KEY"
create_secret "stripe-public-key-pre" "REPLACE_WITH_STRIPE_PUBLIC_KEY"
create_secret "stripe-secret-pre" "REPLACE_WITH_STRIPE_TEST_SECRET_KEY"
create_secret "stripe-webhook-secret-pre" "REPLACE_WITH_STRIPE_WEBHOOK_SECRET"

# Email configuration (Google Workspace)
echo "📧 Setting up email configuration secrets..."
create_secret "mail-username-pre" "REPLACE_WITH_GOOGLE_EMAIL"
create_secret "mail-password-pre" "REPLACE_WITH_GOOGLE_APP_PASSWORD"
create_secret "mail-from-pre" "REPLACE_WITH_FROM_EMAIL"
create_secret "mail-from-name-pre" "Nexus Document Management"
create_secret "mail-server-pre" "smtp.gmail.com"
create_secret "mail-port-pre" "465"
create_secret "mail-starttls-pre" "false"
create_secret "mail-ssl-tls-pre" "true"
create_secret "mail-use-credentials-pre" "true"
create_secret "mail-validate-certs-pre" "true"

# GCS configuration
echo "☁️ Setting up GCS configuration..."
create_secret "gcs-project-id-pre" "nexusdocs360-pre"
create_secret "gcs-bucket-name-pre" "nexusdocs360-pre-docs-eu"

# GCS credentials (PRE bucket)
echo "☁️ Setting up GCS credentials..."
if [ -f "../../../credentials/nexusdocs360-pre-gcs.json" ]; then
    gcloud secrets create gcs-credentials-pre --data-file=../../../credentials/nexusdocs360-pre-gcs.json --project=$PROJECT_ID || \
    gcloud secrets versions add gcs-credentials-pre --data-file=../../../credentials/nexusdocs360-pre-gcs.json --project=$PROJECT_ID
else
    echo "⚠️  GCS credentials file not found. Creating placeholder..."
    create_secret "gcs-credentials-pre" "{}"
fi

# Monitoring and alerting
echo "📊 Setting up monitoring secrets..."
create_secret "slack-webhook-pre" "REPLACE_WITH_SLACK_WEBHOOK_URL"
create_secret "pagerduty-key-pre" "REPLACE_WITH_PAGERDUTY_KEY"

# Feature flags
echo "🚩 Setting up feature flags..."
create_secret "feature-flags-pre" '{"ai_agents":true,"advanced_analytics":true,"experimental":true}'

# Database connection strings
echo "🔗 Creating connection string secrets..."
DB_USER=$(gcloud secrets versions access latest --secret=db-user-pre --project=$PROJECT_ID)
DB_PASS=$(gcloud secrets versions access latest --secret=db-pass-pre --project=$PROJECT_ID)
DB_HOST=$(gcloud secrets versions access latest --secret=db-host-pre --project=$PROJECT_ID)
DB_NAME=$(gcloud secrets versions access latest --secret=db-name-pre --project=$PROJECT_ID)

create_secret "database-url-pre" "postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}:5432/${DB_NAME}"
create_secret "async-database-url-pre" "postgresql+asyncpg://${DB_USER}:${DB_PASS}@${DB_HOST}:5432/${DB_NAME}"

# Grant access to service account
echo "👤 Granting secret access to service account..."
SERVICE_ACCOUNT="nexus-cloud-run-pre@${PROJECT_ID}.iam.gserviceaccount.com"

# Create service account if it doesn't exist
gcloud iam service-accounts create nexus-cloud-run-pre \
    --display-name="NouxCubeIA PRE Cloud Run Service Account" \
    --project=$PROJECT_ID || true

# Grant secret accessor role
for secret in $(gcloud secrets list --project=$PROJECT_ID --format="value(name)"); do
    gcloud secrets add-iam-policy-binding $secret \
        --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role="roles/secretmanager.secretAccessor" \
        --project=$PROJECT_ID
done

# Grant other necessary roles
echo "🎯 Granting additional roles..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/cloudsql.client"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/redis.editor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/monitoring.metricWriter"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/cloudtrace.agent"

echo "✅ PRE Secrets setup complete!"
echo ""
echo "⚠️  Remember to update these secrets with real values:"
echo "  - openai-api-key-pre"
echo "  - anthropic-api-key-pre"
echo "  - clerk-secret-pre"
echo "  - clerk-jwt-key-pre"
echo "  - clerk-publishable-key-pre"
echo "  - stripe-secret-pre (use test keys)"
echo "  - mail-username-pre"
echo "  - mail-password-pre (use Google App Password)"
echo "  - mail-from-pre"
echo "  - slack-webhook-pre"
echo "  - db-host-pre (after Cloud SQL creation)"
echo "  - redis-url-pre (after Memorystore creation)"
echo ""
echo "Use: gcloud secrets versions add SECRET_NAME --data-file=- --project=$PROJECT_ID"