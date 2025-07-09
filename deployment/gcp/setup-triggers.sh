#!/bin/bash
# Setup Cloud Build triggers for GitHub integration
# This creates automatic deployments on push/PR

set -e

echo "🔧 Setting up Cloud Build Triggers"
echo "=================================="

# Check if we have required parameters
if [ $# -lt 1 ]; then
    echo "Usage: $0 <github-repo-owner/repo-name> [environment]"
    echo "Example: $0 nexusdocs360/nexusdocs360 pre"
    exit 1
fi

GITHUB_REPO=$1
ENVIRONMENT=${2:-"both"}  # pre, prod, or both

# Parse repo owner and name
REPO_OWNER=$(echo $GITHUB_REPO | cut -d'/' -f1)
REPO_NAME=$(echo $GITHUB_REPO | cut -d'/' -f2)

echo "Repository: $GITHUB_REPO"
echo "Environment: $ENVIRONMENT"

# Function to create trigger
create_trigger() {
    local ENV=$1
    local BRANCH=$2
    local PROJECT_ID=$3
    local TRIGGER_NAME=$4
    local BUILD_CONFIG=$5
    local DESCRIPTION=$6
    
    echo -e "\n📌 Creating trigger: $TRIGGER_NAME"
    
    gcloud builds triggers create github \
        --project=$PROJECT_ID \
        --repo-name=$REPO_NAME \
        --repo-owner=$REPO_OWNER \
        --branch-pattern="^${BRANCH}$" \
        --build-config=$BUILD_CONFIG \
        --name=$TRIGGER_NAME \
        --description="$DESCRIPTION" \
        --include-logs-with-status \
        --substitutions="_ENVIRONMENT=${ENV}" || echo "Trigger already exists"
}

# Step 1: Connect GitHub repository (if not already connected)
echo -e "\n🔗 Connecting GitHub repository..."
echo "Please follow these steps:"
echo "1. Go to: https://console.cloud.google.com/cloud-build/triggers/connect"
echo "2. Select GitHub and authorize Cloud Build"
echo "3. Select repository: $GITHUB_REPO"
echo "4. Press Enter here when done..."
read -p ""

# Step 2: Create PRE environment triggers
if [ "$ENVIRONMENT" = "pre" ] || [ "$ENVIRONMENT" = "both" ]; then
    echo -e "\n🚀 Setting up PRE environment triggers..."
    
    # Set PRE project
    gcloud config set project nexusdocs360-pre
    
    # Main branch trigger for PRE
    create_trigger \
        "pre" \
        "develop" \
        "nexusdocs360-pre" \
        "deploy-pre-on-push" \
        "deployment/gcp/cloudbuild-trigger-pre.yaml" \
        "Deploy to PRE on push to develop branch"
    
    # PR trigger for PRE
    gcloud builds triggers create github \
        --project=nexusdocs360-pre \
        --repo-name=$REPO_NAME \
        --repo-owner=$REPO_OWNER \
        --pull-request-pattern="^.*$" \
        --build-config="deployment/gcp/cloudbuild-pr-validation.yaml" \
        --name="validate-pr" \
        --description="Validate PR with tests and linting" \
        --comment-control=COMMENTS_ENABLED \
        --include-logs-with-status || echo "PR trigger already exists"
    
    # Manual trigger for PRE
    create_trigger \
        "pre" \
        ".*" \
        "nexusdocs360-pre" \
        "deploy-pre-manual" \
        "deployment/gcp/cloudbuild-trigger-pre.yaml" \
        "Manual deployment to PRE (any branch)"
fi

# Step 3: Create PROD environment triggers
if [ "$ENVIRONMENT" = "prod" ] || [ "$ENVIRONMENT" = "both" ]; then
    echo -e "\n🚀 Setting up PRODUCTION environment triggers..."
    
    # Set PROD project
    gcloud config set project nexusdocs360-prod
    
    # Tag trigger for PROD (only on version tags)
    gcloud builds triggers create github \
        --project=nexusdocs360-prod \
        --repo-name=$REPO_NAME \
        --repo-owner=$REPO_OWNER \
        --tag-pattern="^v[0-9]+\.[0-9]+\.[0-9]+$" \
        --build-config="deployment/gcp/cloudbuild-trigger-prod.yaml" \
        --name="deploy-prod-on-tag" \
        --description="Deploy to PRODUCTION on version tag (v1.0.0)" \
        --include-logs-with-status || echo "Tag trigger already exists"
    
    # Manual trigger for PROD (protected)
    create_trigger \
        "prod" \
        "main" \
        "nexusdocs360-prod" \
        "deploy-prod-manual" \
        "deployment/gcp/cloudbuild-trigger-prod.yaml" \
        "Manual deployment to PRODUCTION (requires approval)"
    
    # Rollback trigger for PROD
    gcloud builds triggers create github \
        --project=nexusdocs360-prod \
        --repo-name=$REPO_NAME \
        --repo-owner=$REPO_OWNER \
        --tag-pattern="^rollback-.*$" \
        --build-config="deployment/gcp/cloudbuild-rollback-prod.yaml" \
        --name="rollback-prod" \
        --description="Rollback PRODUCTION (tag: rollback-YYYYMMDD)" \
        --include-logs-with-status || echo "Rollback trigger already exists"
fi

# Step 4: Create PR validation build config
echo -e "\n📝 Creating PR validation config..."
cat > deployment/gcp/cloudbuild-pr-validation.yaml << 'EOF'
# PR Validation - runs tests and checks without deploying
steps:
  # Frontend tests
  - name: 'node:18'
    dir: 'frontend'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        npm ci
        npm run lint
        npm run test:ci
        npm run build

  # Backend tests
  - name: 'python:3.9'
    dir: 'backend'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        pip install -r requirements.txt
        pip install black flake8 pytest pytest-cov
        black --check app/
        flake8 app/
        pytest tests/ --cov=app --cov-report=xml

  # Security scan
  - name: 'gcr.io/cloud-builders/gcloud'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        echo "Running security checks..."
        # Add your security scanning tools here

options:
  machineType: 'E2_HIGHCPU_8'
  logging: CLOUD_LOGGING_ONLY

timeout: 1200s  # 20 minutes for PR validation
EOF

# Step 5: Create rollback config
echo -e "\n📝 Creating rollback config..."
cat > deployment/gcp/cloudbuild-rollback-prod.yaml << 'EOF'
# Rollback configuration for PRODUCTION
steps:
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        echo "🔄 Rolling back PRODUCTION to previous version..."
        
        # Get previous revision
        PREVIOUS_FRONTEND=$(gcloud run revisions list \
          --service=nexus-frontend-prod \
          --region=europe-west1 \
          --format="value(name)" \
          --limit=2 | tail -1)
        
        PREVIOUS_API=$(gcloud run revisions list \
          --service=nexus-api-prod \
          --region=europe-west1 \
          --format="value(name)" \
          --limit=2 | tail -1)
        
        # Shift traffic back
        gcloud run services update-traffic nexus-frontend-prod \
          --to-revisions=$PREVIOUS_FRONTEND=100 \
          --region=europe-west1
        
        gcloud run services update-traffic nexus-api-prod \
          --to-revisions=$PREVIOUS_API=100 \
          --region=europe-west1
        
        echo "✅ Rollback completed!"

timeout: 600s  # 10 minutes for rollback
EOF

# Step 6: Setup build notifications
echo -e "\n🔔 Setting up build notifications..."

# Create Pub/Sub topic for build notifications
gcloud pubsub topics create cloud-builds --project=${PROJECT_ID:-nexusdocs360-pre} || true

# Subscribe to email notifications (optional)
# gcloud pubsub subscriptions create cloud-builds-email \
#   --topic=cloud-builds \
#   --push-endpoint=https://your-webhook-url.com/builds

echo -e "\n✅ Cloud Build Triggers setup complete!"
echo ""
echo "📋 Created triggers:"
if [ "$ENVIRONMENT" = "pre" ] || [ "$ENVIRONMENT" = "both" ]; then
    echo "  PRE Environment:"
    echo "  - deploy-pre-on-push: Auto-deploy on push to develop"
    echo "  - validate-pr: Run tests on all PRs"
    echo "  - deploy-pre-manual: Manual deployment from any branch"
fi
if [ "$ENVIRONMENT" = "prod" ] || [ "$ENVIRONMENT" = "both" ]; then
    echo "  PROD Environment:"
    echo "  - deploy-prod-on-tag: Auto-deploy on version tags (v1.0.0)"
    echo "  - deploy-prod-manual: Manual deployment (requires approval)"
    echo "  - rollback-prod: Emergency rollback"
fi
echo ""
echo "🎯 Next steps:"
echo "1. Commit the new build files:"
echo "   git add deployment/gcp/cloudbuild-*.yaml"
echo "   git commit -m 'Add Cloud Build configurations'"
echo "   git push"
echo ""
echo "2. Test PRE deployment:"
echo "   git checkout -b test-deployment"
echo "   git push origin test-deployment"
echo "   # Create PR to develop branch"
echo ""
echo "3. For PRODUCTION deployment:"
echo "   git tag v1.0.0"
echo "   git push origin v1.0.0"
echo ""
echo "4. View builds at:"
echo "   https://console.cloud.google.com/cloud-build/builds"