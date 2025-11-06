#!/bin/bash
# Setup Stripe test configuration

set -e

PROJECT_ID="nexusdocs360-pre"

echo "🔧 Setting up Stripe Test Configuration"
echo "====================================="
echo ""

# Test keys (these are example keys - replace with your actual test keys)
STRIPE_TEST_SECRET_KEY="sk_test_51234567890abcdefghijklmnopqrstuvwxyz"
STRIPE_TEST_PUBLISHABLE_KEY="pk_test_51234567890abcdefghijklmnopqrstuvwxyz"
STRIPE_TEST_WEBHOOK_SECRET="whsec_test1234567890abcdefghijklmnop"

echo "⚠️  IMPORTANT: These are placeholder test keys!"
echo "Replace them with your actual Stripe test keys from https://dashboard.stripe.com/test/apikeys"
echo ""
echo "Do you want to continue with placeholder keys? (y/n)"
read -r response

if [[ "$response" != "y" ]]; then
    echo ""
    echo "Please enter your Stripe test keys:"
    echo -n "Secret Key (sk_test_...): "
    read -r STRIPE_TEST_SECRET_KEY
    echo -n "Publishable Key (pk_test_...): "
    read -r STRIPE_TEST_PUBLISHABLE_KEY
    echo -n "Webhook Secret (whsec_... or leave empty): "
    read -r STRIPE_TEST_WEBHOOK_SECRET
fi

echo ""
echo "Creating Stripe secrets..."

# Create secrets
echo "$STRIPE_TEST_SECRET_KEY" | gcloud secrets create stripe-secret-key-pre \
    --data-file=- \
    --project=$PROJECT_ID 2>/dev/null || \
echo "$STRIPE_TEST_SECRET_KEY" | gcloud secrets versions add stripe-secret-key-pre \
    --data-file=- \
    --project=$PROJECT_ID

echo "$STRIPE_TEST_PUBLISHABLE_KEY" | gcloud secrets create stripe-publishable-key-pre \
    --data-file=- \
    --project=$PROJECT_ID 2>/dev/null || \
echo "$STRIPE_TEST_PUBLISHABLE_KEY" | gcloud secrets versions add stripe-publishable-key-pre \
    --data-file=- \
    --project=$PROJECT_ID

if [ -n "$STRIPE_TEST_WEBHOOK_SECRET" ]; then
    echo "$STRIPE_TEST_WEBHOOK_SECRET" | gcloud secrets create stripe-webhook-secret-pre \
        --data-file=- \
        --project=$PROJECT_ID 2>/dev/null || \
    echo "$STRIPE_TEST_WEBHOOK_SECRET" | gcloud secrets versions add stripe-webhook-secret-pre \
        --data-file=- \
        --project=$PROJECT_ID
fi

echo ""
echo "✅ Stripe secrets created/updated"
echo ""
echo "To use real Stripe keys:"
echo "1. Go to https://dashboard.stripe.com/test/apikeys"
echo "2. Copy your test keys"
echo "3. Run this script again with your real keys"
echo ""
echo "Now run ./fix-backend-errors.sh to apply the configuration"