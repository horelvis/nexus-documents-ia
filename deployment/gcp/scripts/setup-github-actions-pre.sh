#!/bin/bash
# Setup GitHub Actions for PRE environment deployment
# This script creates the service account and generates the key for GitHub Actions

set -e

# Configuration
PROJECT_ID="nexusdocs360-pre"
SA_NAME="github-actions-pre"
SA_DISPLAY_NAME="GitHub Actions PRE Deploy"
CREDENTIALS_DIR="$SCRIPT_DIR/../../../credentials"
KEY_FILE="$CREDENTIALS_DIR/github-actions-pre-key.json"

# Create credentials directory if it doesn't exist
mkdir -p "$CREDENTIALS_DIR"

echo "🔧 Setting up GitHub Actions for PRE environment"
echo "📋 Project: $PROJECT_ID"
echo ""

# Check if already authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &>/dev/null; then
    echo "❌ Please authenticate with gcloud first:"
    echo "   gcloud auth login"
    exit 1
fi

# Set project
echo "1️⃣ Setting project..."
gcloud config set project $PROJECT_ID

# Create service account
echo "2️⃣ Creating service account..."
if gcloud iam service-accounts describe $SA_NAME@$PROJECT_ID.iam.gserviceaccount.com &>/dev/null; then
    echo "✅ Service account already exists"
else
    gcloud iam service-accounts create $SA_NAME \
        --display-name="$SA_DISPLAY_NAME" \
        --project=$PROJECT_ID
    echo "✅ Service account created"
fi

SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

# Grant roles
echo "3️⃣ Granting IAM roles..."

ROLES=(
    "roles/run.admin"
    "roles/artifactregistry.admin"
    "roles/iam.serviceAccountUser"
    "roles/compute.instanceAdmin.v1"
    "roles/storage.admin"
)

for ROLE in "${ROLES[@]}"; do
    echo "   - Granting $ROLE..."
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$SA_EMAIL" \
        --role="$ROLE" \
        --condition=None \
        --quiet 2>/dev/null || {
        echo "     ⚠️  Could not grant $ROLE (may already exist)"
    }
done

# Grant Secret Manager access separately
echo "   - Granting Secret Manager access..."
# Get all secrets and grant access
SECRETS=$(gcloud secrets list --project=$PROJECT_ID --format="value(name)" 2>/dev/null)
if [ -n "$SECRETS" ]; then
    echo "     Found $(echo "$SECRETS" | wc -l) secrets"
    for SECRET in $SECRETS; do
        gcloud secrets add-iam-policy-binding $SECRET \
            --member="serviceAccount:$SA_EMAIL" \
            --role="roles/secretmanager.secretAccessor" \
            --project=$PROJECT_ID \
            --quiet 2>/dev/null || true
    done
    echo "     ✅ Secret access granted"
else
    echo "     ⚠️  No secrets found yet. Grant access manually after creating secrets."
fi

echo "✅ All roles granted"

# Generate key
echo "4️⃣ Generating service account key..."
if [ -f "$KEY_FILE" ]; then
    echo "⚠️  Key file already exists at $KEY_FILE"
    read -p "Do you want to regenerate it? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Keeping existing key file"
    else
        rm -f "$KEY_FILE"
        gcloud iam service-accounts keys create "$KEY_FILE" \
            --iam-account=$SA_EMAIL \
            --project=$PROJECT_ID
        echo "✅ New key generated"
    fi
else
    gcloud iam service-accounts keys create "$KEY_FILE" \
        --iam-account=$SA_EMAIL \
        --project=$PROJECT_ID
    echo "✅ Key generated"
fi

# Display key info
echo ""
echo "📋 NEXT STEPS:"
echo "============="
echo ""
echo "1. Copy the service account key:"
echo "   cat $KEY_FILE | pbcopy  # macOS"
echo "   cat $KEY_FILE | xclip -selection clipboard  # Linux"
echo ""
echo "2. Go to your GitHub repository:"
echo "   https://github.com/YOUR_ORG/nexus-document-backend"
echo ""
echo "3. Navigate to:"
echo "   Settings → Secrets and variables → Actions"
echo ""
echo "4. Create a new secret:"
echo "   Name: GCP_SA_KEY_PRE"
echo "   Value: (paste the key content)"
echo ""
echo "5. The key file is saved at: $KEY_FILE"
echo "   ⚠️  Keep this file secure and delete it after adding to GitHub"
echo ""
echo "✅ GitHub Actions setup complete!"