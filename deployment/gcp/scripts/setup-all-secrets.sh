#!/bin/bash
# Setup all required secrets for the application
# This script creates all necessary secrets in Secret Manager

set -e

echo "🔐 Setting up all application secrets"
echo "===================================="
echo ""

PROJECT_ID="nexusdocs360-pre"
SERVICE_ACCOUNT="nexus-cloud-run-pre@${PROJECT_ID}.iam.gserviceaccount.com"

# Function to create/update secret
create_secret() {
    local name=$1
    local value=$2
    local description=$3
    
    echo -n "Creating $name... "
    if echo -n "$value" | gcloud secrets create $name \
        --data-file=- \
        --project=$PROJECT_ID 2>/dev/null; then
        echo "✅ Created"
    else
        echo -n "$value" | gcloud secrets versions add $name \
            --data-file=- \
            --project=$PROJECT_ID
        echo "✅ Updated"
    fi
}

echo "1️⃣ Creating application secrets..."
echo ""

# Core application secrets
create_secret "secret-key-pre" "$(openssl rand -hex 32)" "Application secret key"
create_secret "microservices-api-key-pre" "unified-microservices-key-$(openssl rand -hex 16)" "Microservices API key"

# Redis
echo ""
echo "2️⃣ Setting up Redis secrets..."
REDIS_HOST="redis-pre"  # Update this with your Redis instance
REDIS_PORT="6379"
create_secret "redis-url-pre" "redis://${REDIS_HOST}:${REDIS_PORT}/0" "Redis connection URL"

# GCS Bucket
echo ""
echo "3️⃣ Setting up GCS secrets..."
create_secret "gcs-bucket-name-pre" "nexusdocs360-pre-docs-eu" "GCS bucket name"

# Clerk (if you have the values)
echo ""
echo "4️⃣ Setting up Clerk secrets..."
echo "Enter Clerk configuration (press Enter to skip if not available):"
read -p "CLERK_SECRET_KEY: " CLERK_SECRET_KEY
if [ ! -z "$CLERK_SECRET_KEY" ]; then
    create_secret "clerk-secret-pre" "$CLERK_SECRET_KEY" "Clerk secret key"
fi

# Stripe (if you have the values)
echo ""
echo "5️⃣ Setting up Stripe secrets..."
echo "Enter Stripe configuration (press Enter to skip if not available):"
read -p "STRIPE_SECRET_KEY: " STRIPE_SECRET_KEY
if [ ! -z "$STRIPE_SECRET_KEY" ]; then
    create_secret "stripe-secret-pre" "$STRIPE_SECRET_KEY" "Stripe secret key"
else
    # Create a placeholder if not available
    create_secret "stripe-secret-pre" "sk_test_placeholder" "Stripe secret key (placeholder)"
fi

# Email configuration (optional)
echo ""
echo "6️⃣ Setting up email secrets (optional)..."
create_secret "mail-username-pre" "" "Email username"
create_secret "mail-password-pre" "" "Email password"
create_secret "mail-from-pre" "noreply@nexusdocs360.app" "From email"
create_secret "mail-from-name-pre" "NexusDocs360" "From name"
create_secret "mail-server-pre" "smtp.gmail.com" "Mail server"
create_secret "mail-port-pre" "587" "Mail port"

# Grant permissions to all secrets
echo ""
echo "7️⃣ Granting permissions to service account..."
echo "This will grant access to all secrets ending with '-pre'"

gcloud secrets list --project=$PROJECT_ID --filter="name:pre" --format="value(name)" | while read secret; do
    echo -n "Granting access to $secret... "
    gcloud secrets add-iam-policy-binding $secret \
        --member="serviceAccount:$SERVICE_ACCOUNT" \
        --role="roles/secretmanager.secretAccessor" \
        --project=$PROJECT_ID --quiet
    echo "✅"
done

echo ""
echo "✅ All secrets created and configured!"
echo ""
echo "Summary of secrets created:"
echo "- Core: secret-key-pre, microservices-api-key-pre"
echo "- Redis: redis-url-pre"
echo "- GCS: gcs-bucket-name-pre"
echo "- Clerk: clerk-secret-pre"
echo "- Stripe: stripe-secret-pre"
echo "- Email: mail-* secrets"
echo ""
echo "All secrets have been granted access to: $SERVICE_ACCOUNT"
echo ""
echo "Note: Database secrets should be created by running ./setup-cloudsql-database.sh"