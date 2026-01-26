#!/bin/bash
# Deploy infrastructure for NouxCubeIA on GCP
# This script determines the environment and calls the appropriate deployment script

set -e

# Load environment variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/load-env.sh"

# Determine environment from project ID or parameter
ENVIRONMENT=${1:-}
if [ -z "$ENVIRONMENT" ]; then
    if [[ "$GCP_PROJECT_ID" == *"-pre" ]]; then
        ENVIRONMENT="pre"
    elif [[ "$GCP_PROJECT_ID" == *"-prod" ]]; then
        ENVIRONMENT="prod"
    else
        echo "❌ Error: Cannot determine environment. Please specify 'pre' or 'prod'"
        echo "Usage: $0 [pre|prod]"
        exit 1
    fi
fi

echo "🎯 Detected environment: $ENVIRONMENT"
echo ""

# Call the appropriate deployment script
case $ENVIRONMENT in
    pre)
        echo "🚀 Deploying PRE environment infrastructure..."
        exec "$SCRIPT_DIR/scripts/deploy-infrastructure-pre.sh"
        ;;
    prod)
        echo "🚀 Deploying PRODUCTION environment infrastructure..."
        exec "$SCRIPT_DIR/scripts/deploy-infrastructure-prod.sh"
        ;;
    *)
        echo "❌ Error: Invalid environment '$ENVIRONMENT'"
        echo "Valid options: pre, prod"
        exit 1
        ;;
esac
