#!/bin/bash
# Grant Secret Manager access to service accounts for PRE environment
# Run this after creating secrets

set -e

PROJECT_ID="nexusdocs360-pre"
GITHUB_SA="github-actions-pre@$PROJECT_ID.iam.gserviceaccount.com"
CLOUDRUN_SA="nexus-cloud-run-pre@$PROJECT_ID.iam.gserviceaccount.com"

echo "🔐 Granting Secret Manager access for PRE environment"
echo "📋 Project: $PROJECT_ID"
echo ""

# Get all secrets
echo "1️⃣ Getting list of secrets..."
SECRETS=$(gcloud secrets list --project=$PROJECT_ID --format="value(name)")

if [ -z "$SECRETS" ]; then
    echo "❌ No secrets found. Please run setup-secrets-pre.sh first."
    exit 1
fi

SECRET_COUNT=$(echo "$SECRETS" | wc -l)
echo "✅ Found $SECRET_COUNT secrets"
echo ""

# Grant access to GitHub Actions service account
echo "2️⃣ Granting access to GitHub Actions service account..."
echo "   Service Account: $GITHUB_SA"

for SECRET in $SECRETS; do
    echo -n "   - $SECRET..."
    gcloud secrets add-iam-policy-binding $SECRET \
        --member="serviceAccount:$GITHUB_SA" \
        --role="roles/secretmanager.secretAccessor" \
        --project=$PROJECT_ID \
        --quiet 2>/dev/null && echo " ✓" || echo " (already granted)"
done

echo ""

# Grant access to Cloud Run service account
echo "3️⃣ Granting access to Cloud Run service account..."
echo "   Service Account: $CLOUDRUN_SA"

# Check if Cloud Run SA exists
if ! gcloud iam service-accounts describe $CLOUDRUN_SA &>/dev/null; then
    echo "   ⚠️  Cloud Run service account not found. It will be created during infrastructure deployment."
else
    for SECRET in $SECRETS; do
        echo -n "   - $SECRET..."
        gcloud secrets add-iam-policy-binding $SECRET \
            --member="serviceAccount:$CLOUDRUN_SA" \
            --role="roles/secretmanager.secretAccessor" \
            --project=$PROJECT_ID \
            --quiet 2>/dev/null && echo " ✓" || echo " (already granted)"
    done
fi

echo ""
echo "✅ Secret access configuration complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Deploy infrastructure: ./deploy-infrastructure-pre.sh"
echo "   2. Deploy applications via GitHub Actions"