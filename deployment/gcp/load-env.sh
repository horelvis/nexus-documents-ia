#!/bin/bash
# Script to load environment variables for GCP deployment

# Function to load .env file
load_env() {
    local env_file="${1:-.env}"
    
    if [ ! -f "$env_file" ]; then
        echo "Error: $env_file not found!"
        echo "Please copy .env.prod to .env and update with your values"
        return 1
    fi
    
    # Export variables from .env file
    set -a
    source "$env_file"
    set +a
    
    # Generate derived variables
    export FRONTEND_URL="https://${APP_SUBDOMAIN}.${DOMAIN}"
    export API_URL="https://${API_SUBDOMAIN}.${DOMAIN}"
    export MAIN_URL="https://${DOMAIN}"
    export WWW_URL="https://${WWW_SUBDOMAIN}.${DOMAIN}"
    
    echo "Environment loaded from $env_file"
    echo "Domain: $DOMAIN"
    echo "Frontend URL: $FRONTEND_URL"
    echo "API URL: $API_URL"
}

# Load environment if sourced directly
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    load_env "$@"
fi