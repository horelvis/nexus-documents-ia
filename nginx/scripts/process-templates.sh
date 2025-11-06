#!/bin/bash
# Process nginx configuration templates with environment variables

set -e

# Environment variables
DOMAIN=${DOMAIN:-nexusdocs.com}
APP_SUBDOMAIN=${APP_SUBDOMAIN:-app}
API_SUBDOMAIN=${API_SUBDOMAIN:-api}
WWW_SUBDOMAIN=${WWW_SUBDOMAIN:-www}

echo "Processing nginx configuration templates..."
echo "Domain: $DOMAIN"
echo "Subdomains: app=$APP_SUBDOMAIN, api=$API_SUBDOMAIN, www=$WWW_SUBDOMAIN"

# Function to process a template file
process_template() {
    local input_file=$1
    local output_file=$2
    
    echo "Processing: $input_file -> $output_file"
    
    # Use envsubst to replace variables
    envsubst '${DOMAIN} ${APP_SUBDOMAIN} ${API_SUBDOMAIN} ${WWW_SUBDOMAIN}' < "$input_file" > "$output_file"
}

# Process configuration files
CONFIG_DIR="/etc/nginx/conf.d"
TEMPLATE_DIR="/etc/nginx/templates"

# Create output directory if it doesn't exist
mkdir -p "$CONFIG_DIR"

# Process each template
if [ -d "$TEMPLATE_DIR" ]; then
    for template in "$TEMPLATE_DIR"/*.conf; do
        if [ -f "$template" ]; then
            filename=$(basename "$template")
            process_template "$template" "$CONFIG_DIR/$filename"
        fi
    done
else
    echo "Warning: Template directory not found, using existing configs"
fi

echo "Configuration processing complete!"