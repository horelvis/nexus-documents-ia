#!/bin/bash
# Enable all required Google Cloud APIs for NouxCubeIA
# Works for both PRE and PROD environments

set -e

echo "🔧 Enabling Google Cloud APIs..."
echo "================================"

# Get current project
PROJECT_ID=$(gcloud config get-value project)
echo "Project: $PROJECT_ID"

# Verify project exists and is accessible
if ! gcloud projects describe $PROJECT_ID &>/dev/null; then
    echo -e "\n❌ ERROR: Project '$PROJECT_ID' does not exist or you don't have access."
    echo -e "\n📝 To create the project, run:"
    echo -e "   gcloud projects create $PROJECT_ID --name=\"NouxCubeIA\""
    echo -e "\n🔧 Then configure it:"
    echo -e "   gcloud config set project $PROJECT_ID"
    echo -e "\n💳 And link billing:"
    echo -e "   gcloud beta billing accounts list"
    echo -e "   gcloud beta billing projects link $PROJECT_ID --billing-account=YOUR_BILLING_ID"
    exit 1
fi

# Check if billing is enabled
BILLING_ENABLED=$(gcloud beta billing projects describe $PROJECT_ID --format="value(billingEnabled)" 2>/dev/null || echo "false")
if [ "$BILLING_ENABLED" != "True" ]; then
    echo -e "\n⚠️  WARNING: Billing is not enabled for project '$PROJECT_ID'"
    echo -e "Some APIs may fail to enable without billing."
    echo -e "\n💳 To enable billing:"
    echo -e "   gcloud beta billing accounts list"
    echo -e "   gcloud beta billing projects link $PROJECT_ID --billing-account=YOUR_BILLING_ID"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Core APIs
echo -e "\n📡 Enabling core APIs..."
gcloud services enable \
  compute.googleapis.com \
  cloudbuild.googleapis.com \
  --project=$PROJECT_ID

# Cloud Run will be enabled automatically by Cloud Build
echo -e "\n📌 Note: Cloud Run API will be enabled automatically by Cloud Build"

# Database and Storage
echo -e "\n💾 Enabling database and storage APIs..."
gcloud services enable \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  storage.googleapis.com \
  storage-component.googleapis.com \
  --project=$PROJECT_ID

# Security and Secrets
echo -e "\n🔐 Enabling security APIs..."
gcloud services enable \
  secretmanager.googleapis.com \
  cloudkms.googleapis.com \
  iamcredentials.googleapis.com \
  --project=$PROJECT_ID

# Networking
echo -e "\n🌐 Enabling networking APIs..."
gcloud services enable \
  servicenetworking.googleapis.com \
  vpcaccess.googleapis.com \
  dns.googleapis.com \
  --project=$PROJECT_ID

# Container and Artifact Management
echo -e "\n📦 Enabling Artifact Registry API..."
gcloud services enable \
  artifactregistry.googleapis.com \
  --project=$PROJECT_ID

# Monitoring and Logging
echo -e "\n📊 Enabling monitoring APIs..."
gcloud services enable \
  monitoring.googleapis.com \
  logging.googleapis.com \
  cloudtrace.googleapis.com \
  clouderrorreporting.googleapis.com \
  cloudprofiler.googleapis.com \
  --project=$PROJECT_ID

# Additional APIs for production
if [[ "$PROJECT_ID" == *"-prod" ]]; then
  echo -e "\n🛡️ Enabling additional production APIs..."
  gcloud services enable \
    clouddebugger.googleapis.com \
    dlp.googleapis.com \
    securitycenter.googleapis.com \
    cloudscheduler.googleapis.com \
    --project=$PROJECT_ID
fi

# Billing and Resource Management
echo -e "\n💰 Enabling billing APIs..."
gcloud services enable \
  cloudbilling.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project=$PROJECT_ID

# AI/ML APIs (if needed)
echo -e "\n🤖 Enabling AI/ML APIs..."
gcloud services enable \
  aiplatform.googleapis.com \
  notebooks.googleapis.com \
  --project=$PROJECT_ID || echo "AI/ML APIs optional - skipping if not available"

# List all enabled APIs
echo -e "\n✅ Currently enabled APIs:"
gcloud services list --enabled --format="table(NAME:sort=1)" --project=$PROJECT_ID

echo -e "\n🎉 All required APIs have been enabled!"
echo "You can now proceed with infrastructure deployment."