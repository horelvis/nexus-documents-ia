#!/bin/bash
# Complete deployment script for PRE environment
# This script orchestrates the entire deployment process

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
ZONE="europe-west1-b"

echo "🚀 NexusDocs360 PRE Environment Deployment"
echo "=========================================="
echo ""

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
echo "📋 Checking prerequisites..."
if ! command_exists gcloud; then
    echo "❌ gcloud CLI not found. Please install it first."
    exit 1
fi

if ! command_exists git; then
    echo "❌ git not found. Please install it first."
    exit 1
fi

# Check authentication
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &>/dev/null; then
    echo "❌ Please authenticate with gcloud first:"
    echo "   gcloud auth login"
    exit 1
fi

echo "✅ Prerequisites OK"
echo ""

# Menu
echo "Select deployment steps to run:"
echo "1) Full deployment (all steps)"
echo "2) Setup secrets only"
echo "3) Deploy infrastructure only"
echo "4) Setup GitHub Actions only"
echo "5) Deploy applications only"
echo "6) Configure Nginx only"
echo ""
read -p "Enter your choice (1-6): " choice

case $choice in
    1)
        # Full deployment
        echo "🔄 Running full deployment..."
        
        # Step 1: Setup secrets
        echo ""
        echo "Step 1/5: Setting up secrets..."
        if [ -f "$SCRIPT_DIR/setup-secrets-pre.sh" ]; then
            "$SCRIPT_DIR/setup-secrets-pre.sh"
        else
            echo "❌ setup-secrets-pre.sh not found"
            exit 1
        fi
        
        # Step 2: Update secrets from .env
        echo ""
        echo "Step 2/6: Updating secrets from .env..."
        if [ -f "$SCRIPT_DIR/update-secrets-from-env.sh" ]; then
            "$SCRIPT_DIR/update-secrets-from-env.sh" pre
        else
            echo "⚠️  update-secrets-from-env.sh not found, skipping"
        fi
        
        # Step 3: Grant secrets access
        echo ""
        echo "Step 3/6: Granting secrets access..."
        if [ -f "$SCRIPT_DIR/grant-secrets-access-pre.sh" ]; then
            "$SCRIPT_DIR/grant-secrets-access-pre.sh"
        else
            echo "⚠️  grant-secrets-access-pre.sh not found, skipping"
        fi
        
        # Step 4: Deploy infrastructure
        echo ""
        echo "Step 4/6: Deploying infrastructure..."
        if [ -f "$SCRIPT_DIR/deploy-infrastructure-pre.sh" ]; then
            "$SCRIPT_DIR/deploy-infrastructure-pre.sh"
        else
            echo "❌ deploy-infrastructure-pre.sh not found"
            exit 1
        fi
        
        # Step 5: Setup GitHub Actions
        echo ""
        echo "Step 5/6: Setting up GitHub Actions..."
        if [ -f "$SCRIPT_DIR/setup-github-actions-pre.sh" ]; then
            "$SCRIPT_DIR/setup-github-actions-pre.sh"
        else
            echo "❌ setup-github-actions-pre.sh not found"
            exit 1
        fi
        
        # Step 6: Deploy applications
        echo ""
        echo "Step 6/6: Deploying applications..."
        echo "⚠️  Please push to 'pre' branch to trigger deployment"
        echo "   git checkout -b pre"
        echo "   git push -u origin pre"
        ;;
        
    2)
        # Setup secrets only
        echo "🔐 Setting up secrets..."
        "$SCRIPT_DIR/setup-secrets-pre.sh"
        
        if [ -f "$SCRIPT_DIR/update-secrets-from-env.sh" ]; then
            echo ""
            echo "Updating secrets from .env..."
            "$SCRIPT_DIR/update-secrets-from-env.sh" pre
        fi
        ;;
        
    3)
        # Deploy infrastructure only
        echo "🏗️ Deploying infrastructure..."
        "$SCRIPT_DIR/deploy-infrastructure-pre.sh"
        ;;
        
    4)
        # Setup GitHub Actions only
        echo "🔧 Setting up GitHub Actions..."
        "$SCRIPT_DIR/setup-github-actions-pre.sh"
        ;;
        
    5)
        # Deploy applications only
        echo "📦 Deploying applications..."
        read -p "Do you want to use Cloud Build (y) or GitHub Actions (n)? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            # Use Cloud Build
            cd "$SCRIPT_DIR/../../.."
            gcloud builds submit --config=deployment/gcp/cloudbuild-pre.yaml --project=$PROJECT_ID
        else
            echo "Please push to 'pre' branch to trigger GitHub Actions deployment"
            echo "   git checkout pre"
            echo "   git push origin pre"
        fi
        ;;
        
    6)
        # Configure Nginx only
        echo "🔒 Configuring Nginx..."
        echo "This needs to be run on the Nginx server."
        echo ""
        echo "1. Copy the configuration script to Nginx server:"
        echo "   gcloud compute scp $SCRIPT_DIR/configure-nginx-pre.sh nginx-proxy-pre:~/ --zone=$ZONE --project=$PROJECT_ID"
        echo ""
        echo "2. Connect to Nginx server:"
        echo "   gcloud compute ssh nginx-proxy-pre --zone=$ZONE --project=$PROJECT_ID"
        echo ""
        echo "3. Run the configuration script:"
        echo "   sudo ~/configure-nginx-pre.sh"
        echo ""
        read -p "Do you want to copy and connect now? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            gcloud compute scp "$SCRIPT_DIR/configure-nginx-pre.sh" nginx-proxy-pre:~/ --zone=$ZONE --project=$PROJECT_ID
            gcloud compute ssh nginx-proxy-pre --zone=$ZONE --project=$PROJECT_ID
        fi
        ;;
        
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "✅ Deployment process complete!"
echo ""
echo "📋 Important URLs:"
echo "   Frontend: https://pre.nexusdocs360.app"
echo "   API: https://pre-api.nexusdocs360.app"
echo "   API Docs: https://pre-api.nexusdocs360.app/docs"
echo ""
echo "📊 Monitoring:"
echo "   gcloud run logs read --service=nexus-backend-pre --project=$PROJECT_ID"
echo "   gcloud run logs read --service=nexus-frontend-pre --project=$PROJECT_ID"
echo ""
echo "🔍 Troubleshooting:"
echo "   - Check DNS: dig pre.nexusdocs360.app"
echo "   - Check services: gcloud run services list --project=$PROJECT_ID"
echo "   - Check Nginx: gcloud compute ssh nginx-proxy-pre --zone=$ZONE --project=$PROJECT_ID"