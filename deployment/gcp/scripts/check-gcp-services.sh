#!/bin/bash
# Check GCP configuration and services deployed by GitHub Actions

echo "🔍 Checking GCP Configuration"
echo "============================="

# Check current GCP configuration
echo "📋 Current GCP Configuration:"
echo "Project: $(gcloud config get-value project)"
echo "Account: $(gcloud config get-value account)"
echo "Region: $(gcloud config get-value compute/region)"
echo ""

# List all accessible projects
echo "📁 Projects you have access to:"
gcloud projects list --format="table(projectId,name,projectNumber)" 2>/dev/null || echo "Error listing projects"
echo ""

# Check specific project
PROJECT_ID="nexusdocs360-pre"
echo "🔍 Checking project: $PROJECT_ID"

# Set project temporarily for this check
export CLOUDSDK_CORE_PROJECT=$PROJECT_ID

# List Cloud Run services in different regions
echo ""
echo "☁️  Cloud Run Services in project $PROJECT_ID:"
for region in europe-west1 us-central1 us-east1 europe-west2; do
    echo ""
    echo "Region: $region"
    gcloud run services list --region=$region --project=$PROJECT_ID --format="table(metadata.name,status.url)" 2>/dev/null || echo "  No access or no services"
done

# Check Cloud Build history (to see what GitHub Actions deployed)
echo ""
echo "🏗️  Recent Cloud Build history:"
gcloud builds list --limit=10 --project=$PROJECT_ID --format="table(id,status,createTime.date('%Y-%m-%d %H:%M'),substitutions.SERVICE_NAME)" 2>/dev/null || echo "No access to build history"

# Check Container Registry / Artifact Registry for images
echo ""
echo "🐳 Container images in registry:"
gcloud container images list --project=$PROJECT_ID 2>/dev/null || echo "No access to container registry"

# Check GitHub Actions workflow files
echo ""
echo "📄 Looking for GitHub Actions workflow files locally..."
if [ -d ".github/workflows" ]; then
    echo "Found workflows:"
    ls -la .github/workflows/
    echo ""
    echo "Service names in workflows:"
    grep -h "SERVICE_NAME\|service-name\|gcloud run deploy" .github/workflows/*.yml 2>/dev/null | grep -v "^#" | sort -u || echo "No service names found"
fi

# Provide guidance
echo ""
echo "💡 Next Steps:"
echo "============="
echo ""
echo "1. If you don't see your project in the list above:"
echo "   - Make sure you're logged in with the right account"
echo "   - Request access to the project from the project owner"
echo ""
echo "2. If you see the project but no services:"
echo "   - Check GitHub Actions run history in GitHub"
echo "   - Verify the deployment workflow completed successfully"
echo "   - Check if services are deployed in a different region"
echo ""
echo "3. Common service naming patterns:"
echo "   - nexus-api-[env]"
echo "   - nexus-backend-[env]"
echo "   - nexus-frontend-[env]"
echo "   - [project]-api-[env]"
echo "   - [project]-web-[env]"
echo ""
echo "4. To manually check a specific service:"
echo "   gcloud run services describe SERVICE_NAME --region=REGION --project=$PROJECT_ID"