#!/bin/bash
# Configure Cloud SQL connection for backend

set -e

echo "🔧 Configuring Cloud SQL Connection"
echo "==================================="

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
SERVICE_NAME="nexus-backend-pre"

# Find Cloud SQL instance
echo "1️⃣ Finding Cloud SQL instance..."
INSTANCE_NAME=$(gcloud sql instances list --project=$PROJECT_ID --format="value(name)" | head -1)

if [ -z "$INSTANCE_NAME" ]; then
    echo "❌ No Cloud SQL instance found!"
    exit 1
fi

echo "✅ Found Cloud SQL instance: $INSTANCE_NAME"

# Get instance details
echo ""
echo "2️⃣ Cloud SQL instance details:"
gcloud sql instances describe $INSTANCE_NAME --project=$PROJECT_ID --format="table(
    name,
    databaseVersion,
    settings.tier,
    settings.ipConfiguration.ipv4Enabled,
    settings.ipConfiguration.privateNetwork,
    connectionName
)"

# Get connection name
CONNECTION_NAME=$(gcloud sql instances describe $INSTANCE_NAME --project=$PROJECT_ID --format="value(connectionName)")
echo ""
echo "Connection name: $CONNECTION_NAME"

# Check if Cloud Run service has Cloud SQL connection
echo ""
echo "3️⃣ Checking Cloud Run Cloud SQL connections..."
CURRENT_INSTANCES=$(gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(spec.template.metadata.annotations.'run.googleapis.com/cloudsql-instances')" 2>/dev/null || echo "none")

echo "Current Cloud SQL instances: ${CURRENT_INSTANCES:-none}"

# Enable Cloud SQL connection
if [ "$CURRENT_INSTANCES" == "none" ] || [ -z "$CURRENT_INSTANCES" ]; then
    echo ""
    echo "4️⃣ Enabling Cloud SQL connection for Cloud Run..."
    gcloud run services update $SERVICE_NAME \
        --add-cloudsql-instances=$CONNECTION_NAME \
        --region=$REGION \
        --project=$PROJECT_ID
    echo "✅ Cloud SQL connection enabled"
else
    echo "✅ Cloud SQL connection already enabled"
fi

# Check VPC connector (for private IP)
echo ""
echo "5️⃣ Checking VPC connector..."
VPC_CONNECTOR=$(gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(spec.template.metadata.annotations.'run.googleapis.com/vpc-access-connector')" 2>/dev/null || echo "none")

echo "VPC Connector: ${VPC_CONNECTOR:-none}"

# Create proper database URLs
echo ""
echo "6️⃣ Creating proper database URLs for Cloud SQL..."

# Check if using private IP
PRIVATE_IP=$(gcloud sql instances describe $INSTANCE_NAME --project=$PROJECT_ID --format="value(ipAddresses[0].ipAddress)" 2>/dev/null | grep -E "10\.|172\.|192\." || echo "")
PUBLIC_IP=$(gcloud sql instances describe $INSTANCE_NAME --project=$PROJECT_ID --format="value(ipAddresses[0].ipAddress)" 2>/dev/null | grep -v -E "10\.|172\.|192\." || echo "")

echo "Private IP: ${PRIVATE_IP:-none}"
echo "Public IP: ${PUBLIC_IP:-none}"

# Get database name
DB_NAME=$(gcloud sql databases list --instance=$INSTANCE_NAME --project=$PROJECT_ID --format="value(name)" | grep -v "postgres" | head -1 || echo "nexusdocs")
echo "Database name: $DB_NAME"

# Create connection script
cat > /tmp/setup-cloudsql-urls.sh << EOF
#!/bin/bash
# Setup Cloud SQL URLs

PROJECT_ID="$PROJECT_ID"
REGION="$REGION"
SERVICE_NAME="$SERVICE_NAME"
CONNECTION_NAME="$CONNECTION_NAME"
DB_NAME="$DB_NAME"
PRIVATE_IP="$PRIVATE_IP"

echo "Setting up Cloud SQL database URLs..."
echo ""

# Get credentials
echo "Enter database credentials:"
read -p "Database user (default: postgres): " DB_USER
DB_USER=\${DB_USER:-postgres}
read -sp "Database password: " DB_PASSWORD
echo ""

# Determine connection method
if [ ! -z "\$PRIVATE_IP" ] && [ "\$PRIVATE_IP" != "none" ]; then
    echo ""
    echo "Using private IP connection..."
    DATABASE_URL="postgresql://\${DB_USER}:\${DB_PASSWORD}@\${PRIVATE_IP}:5432/\${DB_NAME}"
    ASYNC_DATABASE_URL="postgresql+asyncpg://\${DB_USER}:\${DB_PASSWORD}@\${PRIVATE_IP}:5432/\${DB_NAME}"
else
    echo ""
    echo "Using Cloud SQL Proxy (Unix socket) connection..."
    # For Cloud SQL Proxy via Unix socket
    DATABASE_URL="postgresql://\${DB_USER}:\${DB_PASSWORD}@/\${DB_NAME}?host=/cloudsql/\${CONNECTION_NAME}"
    ASYNC_DATABASE_URL="postgresql+asyncpg://\${DB_USER}:\${DB_PASSWORD}@/\${DB_NAME}?host=/cloudsql/\${CONNECTION_NAME}"
fi

echo ""
echo "Database URLs configured:"
echo "DATABASE_URL: postgresql://***:***@***/\$DB_NAME"
echo ""

# Create/update secrets
echo "Creating/updating secrets..."

# DATABASE_URL
echo -n "\$DATABASE_URL" | gcloud secrets create database-url-pre \
    --data-file=- \
    --project=\$PROJECT_ID 2>/dev/null || \
echo -n "\$DATABASE_URL" | gcloud secrets versions add database-url-pre \
    --data-file=- \
    --project=\$PROJECT_ID

# ASYNC_DATABASE_URL
echo -n "\$ASYNC_DATABASE_URL" | gcloud secrets create async-database-url-pre \
    --data-file=- \
    --project=\$PROJECT_ID 2>/dev/null || \
echo -n "\$ASYNC_DATABASE_URL" | gcloud secrets versions add async-database-url-pre \
    --data-file=- \
    --project=\$PROJECT_ID

# Grant permissions
echo ""
echo "Granting permissions..."
for secret in database-url-pre async-database-url-pre; do
    gcloud secrets add-iam-policy-binding \$secret \
        --member="serviceAccount:nexus-cloud-run-pre@\${PROJECT_ID}.iam.gserviceaccount.com" \
        --role="roles/secretmanager.secretAccessor" \
        --project=\$PROJECT_ID --quiet
done

# Update Cloud Run service
echo ""
echo "Updating Cloud Run service..."
gcloud run services update \$SERVICE_NAME \
    --update-secrets="DATABASE_URL=database-url-pre:latest,ASYNC_DATABASE_URL=async-database-url-pre:latest" \
    --region=\$REGION \
    --project=\$PROJECT_ID

echo ""
echo "✅ Database configuration complete!"
echo ""
echo "Waiting for service to stabilize..."
sleep 20

# Test
BACKEND_URL=\$(gcloud run services describe \$SERVICE_NAME --region=\$REGION --project=\$PROJECT_ID --format='value(status.url)')
echo ""
echo "Testing connection..."
response=\$(curl -s -o /dev/null -w "%{http_code}" "\$BACKEND_URL/health" || echo "failed")
echo "Health check: HTTP \$response"

if [ "\$response" != "200" ]; then
    echo ""
    echo "⚠️  Service might need a moment to connect. Checking logs..."
    gcloud run logs read \$SERVICE_NAME --limit=10 --region=\$REGION --project=\$PROJECT_ID | grep -i "database\|postgres" | tail -5
fi
EOF

chmod +x /tmp/setup-cloudsql-urls.sh

echo ""
echo "7️⃣ Additional configuration needed in backend code:"
echo "================================================="
echo ""
echo "Make sure your backend's database configuration supports Cloud SQL:"
echo ""
cat << 'CODE'
# In backend/app/core/config.py or database.py:

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine

# For Cloud SQL with Unix socket
def get_database_url():
    # Get from environment
    database_url = os.getenv("DATABASE_URL")
    
    # If running in Cloud Run with Cloud SQL
    if "/cloudsql/" in database_url:
        # SQLAlchemy needs special handling for Unix sockets
        # Already handled in the URL format we're using
        pass
    
    return database_url

# For async connections
def get_async_database_url():
    return os.getenv("ASYNC_DATABASE_URL")

# Create engines
engine = create_engine(get_database_url(), pool_pre_ping=True)
async_engine = create_async_engine(get_async_database_url(), pool_pre_ping=True)
CODE

echo ""
echo "✅ Next steps:"
echo "============="
echo "1. Run the setup script to configure database URLs:"
echo "   /tmp/setup-cloudsql-urls.sh"
echo ""
echo "2. Make sure your Cloud SQL instance allows connections:"
echo "   - Has a database created (not just 'postgres')"
echo "   - Has proper user/password set"
echo "   - Network configuration allows Cloud Run connections"
echo ""
echo "3. If still having issues, check:"
echo "   - VPC connector is properly configured (for private IP)"
echo "   - Cloud SQL Admin API is enabled"
echo "   - Service account has Cloud SQL Client role"