#!/bin/bash
# Update GCP secrets from backend/.env file
# Usage: ./update-secrets-from-env.sh [environment]
# Example: ./update-secrets-from-env.sh pre

set -e

ENVIRONMENT=${1:-pre}
PROJECT_ID="nexusdocs360-${ENVIRONMENT}"
ENV_FILE="../../../backend/.env"

echo "🔐 Updating secrets for $ENVIRONMENT environment from .env file"

# Check if .env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: $ENV_FILE not found"
    exit 1
fi

# Function to read value from .env file
get_env_value() {
    local key=$1
    grep "^${key}=" "$ENV_FILE" | cut -d '=' -f2- | sed 's/^"//' | sed 's/"$//'
}

# Function to update secret
update_secret() {
    local secret_name=$1
    local secret_value=$2
    
    if [ -z "$secret_value" ] || [ "$secret_value" = "" ]; then
        echo "⚠️  Skipping $secret_name (empty value)"
        return
    fi
    
    echo "✓ Updating $secret_name"
    echo -n "$secret_value" | gcloud secrets versions add "$secret_name-$ENVIRONMENT" --data-file=- --project=$PROJECT_ID 2>/dev/null || {
        echo "  Creating new secret: $secret_name-$ENVIRONMENT"
        echo -n "$secret_value" | gcloud secrets create "$secret_name-$ENVIRONMENT" --data-file=- --project=$PROJECT_ID
    }
}

echo "📋 Reading configuration from $ENV_FILE..."

# Clerk Configuration
echo "🔑 Updating Clerk secrets..."
update_secret "clerk-publishable-key" "$(get_env_value 'CLERK_PUBLISHABLE_KEY')"
update_secret "clerk-secret" "$(get_env_value 'CLERK_SECRET_KEY')"

# Stripe Configuration
echo "💳 Updating Stripe secrets..."
update_secret "stripe-public-key" "$(get_env_value 'STRIPE_PUBLIC_KEY')"
update_secret "stripe-secret" "$(get_env_value 'STRIPE_SECRET_KEY')"
update_secret "stripe-webhook-secret" "$(get_env_value 'STRIPE_WEBHOOK_SECRET')"
update_secret "stripe-pro-price-id" "$(get_env_value 'STRIPE_PRO_PRICE_ID')"
update_secret "stripe-enterprise-price-id" "$(get_env_value 'STRIPE_ENTERPRISE_PRICE_ID')"

# Email Configuration
echo "📧 Updating email secrets..."
update_secret "mail-username" "$(get_env_value 'MAIL_USERNAME')"
update_secret "mail-password" "$(get_env_value 'MAIL_PASSWORD')"
update_secret "mail-from" "$(get_env_value 'MAIL_FROM')"
update_secret "mail-from-name" "$(get_env_value 'MAIL_FROM_NAME')"
update_secret "mail-server" "$(get_env_value 'MAIL_SERVER')"
update_secret "mail-port" "$(get_env_value 'MAIL_PORT')"
update_secret "mail-starttls" "$(get_env_value 'MAIL_STARTTLS')"
update_secret "mail-ssl-tls" "$(get_env_value 'MAIL_SSL_TLS')"
update_secret "mail-use-credentials" "$(get_env_value 'MAIL_USE_CREDENTIALS')"
update_secret "mail-validate-certs" "$(get_env_value 'MAIL_VALIDATE_CERTS')"

# GCS Configuration
echo "☁️  Updating GCS secrets..."
update_secret "gcs-project-id" "$(get_env_value 'GCS_PROJECT_ID')"
update_secret "gcs-bucket-name" "$(get_env_value 'GCS_BUCKET_NAME')"

# Microservices
echo "🔧 Updating microservices secrets..."
update_secret "microservices-api-key" "$(get_env_value 'MICROSERVICES_API_KEY')"
update_secret "storage-api-key" "$(get_env_value 'STORAGE_API_KEY')"

# AI/LLM Configuration
echo "🤖 Updating AI/LLM secrets..."
update_secret "openai-api-key" "$(get_env_value 'OPENAI_API_KEY')"
update_secret "anthropic-api-key" "$(get_env_value 'ANTHROPIC_API_KEY')"
update_secret "huggingface-token" "$(get_env_value 'HF_TOKEN')"
update_secret "xai-api-key" "$(get_env_value 'XAI_API_KEY')"

# Database Configuration (only if running locally)
if [ "$ENVIRONMENT" = "local" ]; then
    echo "🗄️  Updating database secrets..."
    update_secret "db-user" "$(get_env_value 'POSTGRES_USER')"
    update_secret "db-pass" "$(get_env_value 'POSTGRES_PASSWORD')"
    update_secret "db-name" "$(get_env_value 'POSTGRES_DB')"
    update_secret "db-host" "$(get_env_value 'POSTGRES_SERVER')"
fi

echo ""
echo "✅ Secrets updated successfully!"
echo ""
echo "📝 Summary:"
echo "   - Environment: $ENVIRONMENT"
echo "   - Project: $PROJECT_ID"
echo "   - Source: $ENV_FILE"
echo ""
echo "⚠️  Note: Some secrets may need manual configuration:"
echo "   - Database credentials (for cloud environments)"
echo "   - Monitoring webhooks (Slack, PagerDuty)"
echo "   - GCS service account credentials file"
echo ""
echo "To verify secrets, run:"
echo "   gcloud secrets list --project=$PROJECT_ID"