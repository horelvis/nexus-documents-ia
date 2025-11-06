#!/bin/bash
# Setup GCP Secrets for NexusDocs360

set -e

# Load environment variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/load-env.sh"

PROJECT_ID=${1:-${GCP_PROJECT_ID:-nexus-document-prod}}
REGION=${2:-${GCP_REGION:-europe-west1}}

echo "🔐 Setting up secrets for project: $PROJECT_ID"

# Enable required APIs
echo "📡 Enabling required GCP APIs..."
gcloud services enable \
    secretmanager.googleapis.com \
    cloudrun.googleapis.com \
    cloudbuild.googleapis.com \
    sqladmin.googleapis.com \
    redis.googleapis.com \
    compute.googleapis.com \
    containerregistry.googleapis.com \
    --project=$PROJECT_ID

# Function to create or update secret
create_secret() {
    SECRET_NAME=$1
    SECRET_VALUE=$2
    
    if gcloud secrets describe $SECRET_NAME --project=$PROJECT_ID &>/dev/null; then
        echo "Updating secret: $SECRET_NAME"
        echo -n "$SECRET_VALUE" | gcloud secrets versions add $SECRET_NAME --data-file=- --project=$PROJECT_ID
    else
        echo "Creating secret: $SECRET_NAME"
        echo -n "$SECRET_VALUE" | gcloud secrets create $SECRET_NAME --data-file=- --project=$PROJECT_ID
    fi
}

# Database secrets
echo "🗄️ Setting up database secrets..."
create_secret "db-user" "nexus_user"
create_secret "db-pass" "$(openssl rand -base64 32)"
create_secret "db-host" "10.0.0.3"  # Internal IP, will be updated after Cloud SQL creation
create_secret "db-name" "nexus_db"

# Application secrets
echo "🔑 Setting up application secrets..."
create_secret "secret-key" "$(openssl rand -base64 64)"
create_secret "microservices-api-key" "$(openssl rand -hex 32)"
create_secret "signature-encryption-key" "$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

# Redis URL
echo "💾 Setting up Redis secrets..."
create_secret "redis-url" "redis://10.0.0.4:6379"  # Will be updated after Memorystore creation

# External service keys (placeholders - update with real values)
echo "🌐 Setting up external service secrets..."
create_secret "clerk-secret" "REPLACE_WITH_CLERK_SECRET_KEY"
create_secret "clerk-jwt-key" "REPLACE_WITH_CLERK_JWT_PUBLIC_KEY"
create_secret "clerk-publishable-key" "REPLACE_WITH_CLERK_PUBLISHABLE_KEY"
create_secret "stripe-secret" "REPLACE_WITH_STRIPE_SECRET_KEY"
create_secret "stripe-webhook-secret" "REPLACE_WITH_STRIPE_WEBHOOK_SECRET"
create_secret "sendgrid-api-key" "REPLACE_WITH_SENDGRID_API_KEY"

# GCS credentials
echo "☁️ Setting up GCS credentials..."
if [ -f "../../../credentials/nexus-document-ia-04252dae0146.json" ]; then
    gcloud secrets create gcs-credentials --data-file=../../../credentials/nexus-document-ia-04252dae0146.json --project=$PROJECT_ID || \
    gcloud secrets versions add gcs-credentials --data-file=../../../credentials/nexus-document-ia-04252dae0146.json --project=$PROJECT_ID
else
    echo "⚠️  GCS credentials file not found. Please add it manually."
fi

# Database connection strings
echo "🔗 Creating connection string secrets..."
DB_USER=$(gcloud secrets versions access latest --secret=db-user --project=$PROJECT_ID)
DB_PASS=$(gcloud secrets versions access latest --secret=db-pass --project=$PROJECT_ID)
DB_HOST=$(gcloud secrets versions access latest --secret=db-host --project=$PROJECT_ID)
DB_NAME=$(gcloud secrets versions access latest --secret=db-name --project=$PROJECT_ID)

create_secret "database-url" "postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}:5432/${DB_NAME}"
create_secret "async-database-url" "postgresql+asyncpg://${DB_USER}:${DB_PASS}@${DB_HOST}:5432/${DB_NAME}"

# Grant access to Cloud Run service account
echo "👤 Granting secret access to service account..."
SERVICE_ACCOUNT="nexus-cloud-run@${PROJECT_ID}.iam.gserviceaccount.com"

# Create service account if it doesn't exist
gcloud iam service-accounts create nexus-cloud-run \
    --display-name="Nexus Cloud Run Service Account" \
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

echo "✅ Secrets setup complete!"
echo ""
echo "⚠️  Remember to update these secrets with real values:"
echo "  - clerk-secret"
echo "  - clerk-jwt-key"
echo "  - clerk-publishable-key"
echo "  - stripe-secret"
echo "  - stripe-webhook-secret"
echo "  - sendgrid-api-key"
echo "  - db-host (after Cloud SQL creation)"
echo "  - redis-url (after Memorystore creation)"
echo ""
echo "Use: gcloud secrets versions add SECRET_NAME --data-file=- --project=$PROJECT_ID"