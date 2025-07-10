#!/bin/bash
# Setup and run Cloud SQL Proxy for local development
# This allows secure connection to Cloud SQL without exposing public IP

set -e

# Configuration
PROJECT_ID="nexusdocs360-pre"
INSTANCE_CONNECTION="nexusdocs360-pre:europe-west1:nexusdocuments360db"
LOCAL_PORT=5432

echo "🔌 Cloud SQL Proxy Setup"
echo "========================"
echo "Instance: $INSTANCE_CONNECTION"
echo "Local Port: $LOCAL_PORT"
echo ""

# Check if cloud-sql-proxy is installed
PROXY_CMD=""
if command -v cloud-sql-proxy &> /dev/null; then
    PROXY_CMD="cloud-sql-proxy"
elif command -v cloud_sql_proxy &> /dev/null; then
    PROXY_CMD="cloud_sql_proxy"
else
    echo "❌ Cloud SQL Proxy not installed"
    echo ""
    echo "📦 Installing Cloud SQL Proxy..."
    
    # Detect OS
    OS="$(uname -s)"
    ARCH="$(uname -m)"
    
    case "$OS" in
        Darwin*)
            if [ "$ARCH" = "arm64" ]; then
                DOWNLOAD_URL="https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.11.4/cloud-sql-proxy.darwin.arm64"
            else
                DOWNLOAD_URL="https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.11.4/cloud-sql-proxy.darwin.amd64"
            fi
            ;;
        Linux*)
            if [ "$ARCH" = "aarch64" ]; then
                DOWNLOAD_URL="https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.11.4/cloud-sql-proxy.linux.arm64"
            else
                DOWNLOAD_URL="https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.11.4/cloud-sql-proxy.linux.amd64"
            fi
            ;;
        *)
            echo "❌ Unsupported OS: $OS"
            exit 1
            ;;
    esac
    
    echo "Downloading from: $DOWNLOAD_URL"
    curl -o /tmp/cloud-sql-proxy $DOWNLOAD_URL
    chmod +x /tmp/cloud-sql-proxy
    
    # Try to move to system location
    if [ -w "/usr/local/bin" ]; then
        mv /tmp/cloud-sql-proxy /usr/local/bin/cloud-sql-proxy
        echo "✅ Installed to /usr/local/bin/cloud-sql-proxy"
        PROXY_CMD="cloud-sql-proxy"
    else
        # Keep in current directory
        mv /tmp/cloud-sql-proxy ./cloud-sql-proxy
        echo "✅ Installed to ./cloud-sql-proxy (no system write access)"
        PROXY_CMD="./cloud-sql-proxy"
    fi
fi

# Check authentication
echo ""
echo "🔐 Checking authentication..."
if ! gcloud auth application-default print-access-token &> /dev/null; then
    echo "❌ Not authenticated. Running authentication..."
    gcloud auth application-default login
else
    echo "✅ Already authenticated"
fi

# Get database credentials
echo ""
echo "📊 Getting database credentials..."
DB_USER=$(gcloud secrets versions access latest --secret=db-user-pre --project=$PROJECT_ID 2>/dev/null || echo "nexus_user_pre")
DB_NAME=$(gcloud secrets versions access latest --secret=db-name-pre --project=$PROJECT_ID 2>/dev/null || echo "nexusdocs360_pre")
DB_PASS=$(gcloud secrets versions access latest --secret=db-pass-pre --project=$PROJECT_ID 2>/dev/null || echo "")

# Create .env.proxy file with connection details
cat > .env.proxy << EOF
# Cloud SQL Proxy Connection Details
# Source this file: source .env.proxy

export DATABASE_HOST="localhost"
export DATABASE_PORT="$LOCAL_PORT"
export DATABASE_USER="$DB_USER"
export DATABASE_NAME="$DB_NAME"
export DATABASE_PASSWORD="$DB_PASS"

# Connection URLs
export DATABASE_URL="postgresql://$DB_USER:$DB_PASS@localhost:$LOCAL_PORT/$DB_NAME"
export ASYNC_DATABASE_URL="postgresql+asyncpg://$DB_USER:$DB_PASS@localhost:$LOCAL_PORT/$DB_NAME"

# For SQLAlchemy
export SQLALCHEMY_DATABASE_URL="postgresql://$DB_USER:$DB_PASS@localhost:$LOCAL_PORT/$DB_NAME"
EOF

echo "✅ Created .env.proxy file with connection details"
echo ""

# Check if proxy is already running
if lsof -Pi :$LOCAL_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  Port $LOCAL_PORT is already in use. Stopping existing process..."
    lsof -ti:$LOCAL_PORT | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# Start proxy
echo "🚀 Starting Cloud SQL Proxy..."
echo "   Command: $PROXY_CMD --port=$LOCAL_PORT $INSTANCE_CONNECTION"
echo ""
echo "📝 Connection details:"
echo "   Host: localhost"
echo "   Port: $LOCAL_PORT"
echo "   Database: $DB_NAME"
echo "   User: $DB_USER"
echo ""
echo "🔗 Connection string:"
echo "   postgresql://$DB_USER:<password>@localhost:$LOCAL_PORT/$DB_NAME"
echo ""
echo "Press Ctrl+C to stop the proxy"
echo "="*50

# Run proxy in foreground
$PROXY_CMD --port=$LOCAL_PORT $INSTANCE_CONNECTION