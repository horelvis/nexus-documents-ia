#!/bin/bash
# Script to add Clerk publishable key to GitHub secrets

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Add Clerk Publishable Key to GitHub Secrets${NC}"
echo ""

# Check if .env file exists (try from script location)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

ENV_FILE="$PROJECT_ROOT/backend/.env"
FRONTEND_ENV="$PROJECT_ROOT/frontend/.env"

# Try backend .env first
if [ -f "$ENV_FILE" ]; then
    CLERK_KEY=$(grep "^NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"' | tr -d "'")
fi

# If not found, try frontend .env
if [ -z "$CLERK_KEY" ] && [ -f "$FRONTEND_ENV" ]; then
    CLERK_KEY=$(grep "^NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=" "$FRONTEND_ENV" | cut -d'=' -f2- | tr -d '"' | tr -d "'")
fi
    
    if [ -z "$CLERK_KEY" ]; then
        echo -e "${YELLOW}Clerk publishable key not found in .env files${NC}"
        echo "Please enter it manually:"
        read -p "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: " CLERK_KEY
    else
        echo "Found Clerk key: ${CLERK_KEY:0:20}..."
    fi
fi

if [ -z "$CLERK_KEY" ]; then
    echo "Error: Clerk publishable key is required"
    exit 1
fi

# Get GitHub repository
read -p "Enter your GitHub repository (e.g., username/repo): " GITHUB_REPO

echo ""
echo "To add this secret to GitHub:"
echo "1. Go to: https://github.com/$GITHUB_REPO/settings/secrets/actions"
echo "2. Click 'New repository secret'"
echo "3. Add the following secret:"
echo ""
echo "   Name: CLERK_PUBLISHABLE_KEY_PRE"
echo "   Value: $CLERK_KEY"
echo ""
echo "Or use GitHub CLI:"
echo ""
echo "gh secret set CLERK_PUBLISHABLE_KEY_PRE --repo $GITHUB_REPO --body \"$CLERK_KEY\""
echo ""

# Ask if user has GitHub CLI
read -p "Do you have GitHub CLI installed and want to set it now? (y/n): " USE_GH_CLI

if [ "$USE_GH_CLI" = "y" ] || [ "$USE_GH_CLI" = "Y" ]; then
    echo "Setting secret via GitHub CLI..."
    gh secret set CLERK_PUBLISHABLE_KEY_PRE --repo "$GITHUB_REPO" --body "$CLERK_KEY"
    echo -e "${GREEN}✓ Secret added successfully!${NC}"
else
    echo ""
    echo "Please add the secret manually using the instructions above."
    echo "After adding the secret, push a new commit to trigger the deployment."
fi