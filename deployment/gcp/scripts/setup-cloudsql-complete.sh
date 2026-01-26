#!/bin/bash
# Complete Cloud SQL configuration for NouxCubeIA Backend
# This script configures all necessary database variables for Cloud Run

set -e

echo "🔧 Complete Cloud SQL Configuration for NouxCubeIA"
echo "=================================================="
echo ""

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
SERVICE_NAME="nexus-backend-pre"

# Check if user is authenticated
echo "Checking Google Cloud authentication..."
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ Not authenticated. Please run: gcloud auth login"
    exit 1
fi

# Set project
gcloud config set project $PROJECT_ID 2>/dev/null || true

# Find Cloud SQL instance
echo ""
echo "1️⃣ Finding Cloud SQL instance..."
INSTANCES=$(gcloud sql instances list --project=$PROJECT_ID --format="value(name)" 2>/dev/null || echo "")

if [ -z "$INSTANCES" ]; then
    echo "❌ No Cloud SQL instances found in project $PROJECT_ID"
    echo ""
    echo "Would you like to create a new Cloud SQL instance? (y/n)"
    read -p "> " create_instance
    
    if [ "$create_instance" = "y" ]; then
        echo ""
        echo "Creating Cloud SQL instance..."
        INSTANCE_NAME="nexusdocs-pre"
        
        gcloud sql instances create $INSTANCE_NAME \
            --database-version=POSTGRES_15 \
            --tier=db-g1-small \
            --region=$REGION \
            --network=projects/$PROJECT_ID/global/networks/default \
            --no-assign-ip \
            --project=$PROJECT_ID
            
        echo "✅ Cloud SQL instance created: $INSTANCE_NAME"
    else
        echo "Please create a Cloud SQL instance first."
        exit 1
    fi
else
    echo "Found Cloud SQL instances:"
    echo "$INSTANCES"
    
    if [ $(echo "$INSTANCES" | wc -l) -eq 1 ]; then
        INSTANCE_NAME="$INSTANCES"
        echo "✅ Using instance: $INSTANCE_NAME"
    else
        echo ""
        echo "Multiple instances found. Please enter the instance name:"
        read -p "> " INSTANCE_NAME
    fi
fi

# Get instance details
echo ""
echo "2️⃣ Getting instance details..."
CONNECTION_NAME=$(gcloud sql instances describe $INSTANCE_NAME --project=$PROJECT_ID --format="value(connectionName)")
PRIVATE_IP=$(gcloud sql instances describe $INSTANCE_NAME --project=$PROJECT_ID --format="value(ipAddresses[0].ipAddress)" 2>/dev/null | grep -E "10\.|172\.|192\." || echo "")
PUBLIC_IP=$(gcloud sql instances describe $INSTANCE_NAME --project=$PROJECT_ID --format="value(ipAddresses[0].ipAddress)" 2>/dev/null | grep -v -E "10\.|172\.|192\." || echo "")

echo "Connection name: $CONNECTION_NAME"
echo "Private IP: ${PRIVATE_IP:-none}"
echo "Public IP: ${PUBLIC_IP:-none}"

# Check databases
echo ""
echo "3️⃣ Checking databases..."
DATABASES=$(gcloud sql databases list --instance=$INSTANCE_NAME --project=$PROJECT_ID --format="value(name)" 2>/dev/null || echo "")

if [ -z "$DATABASES" ] || ! echo "$DATABASES" | grep -q -v "^postgres$"; then
    echo "No application database found. Creating 'nexusdocs' database..."
    gcloud sql databases create nexusdocs --instance=$INSTANCE_NAME --project=$PROJECT_ID
    DB_NAME="nexusdocs"
else
    APP_DB=$(echo "$DATABASES" | grep -v "^postgres$" | head -1)
    echo "Found databases: $DATABASES"
    echo "Using database: $APP_DB"
    DB_NAME="$APP_DB"
fi

# Get database credentials
echo ""
echo "4️⃣ Database credentials setup..."
echo ""
echo "Enter database credentials:"
read -p "Database user (default: postgres): " DB_USER
DB_USER=${DB_USER:-postgres}

# Check if we need to set password
echo ""
echo "Do you need to set/update the database password? (y/n)"
read -p "> " update_password

if [ "$update_password" = "y" ]; then
    read -sp "Enter new database password: " DB_PASSWORD
    echo ""
    echo "Setting database password..."
    gcloud sql users set-password $DB_USER --instance=$INSTANCE_NAME --password="$DB_PASSWORD" --project=$PROJECT_ID
    echo "✅ Password updated"
else
    read -sp "Enter existing database password: " DB_PASSWORD
    echo ""
fi

# Determine connection method
echo ""
echo "5️⃣ Configuring connection method..."

# Check if Cloud Run service has VPC connector
VPC_CONNECTOR=$(gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(spec.template.metadata.annotations.'run.googleapis.com/vpc-access-connector')" 2>/dev/null || echo "")

if [ ! -z "$PRIVATE_IP" ] && [ ! -z "$VPC_CONNECTOR" ]; then
    echo "✅ Using private IP connection (VPC connector found)"
    POSTGRES_SERVER="$PRIVATE_IP"
    USE_CLOUD_SQL_PROXY="false"
else
    echo "✅ Using Cloud SQL Proxy (Unix socket)"
    POSTGRES_SERVER="/cloudsql/$CONNECTION_NAME"
    USE_CLOUD_SQL_PROXY="true"
fi

# Create all required secrets
echo ""
echo "6️⃣ Creating/updating secrets..."

# Function to create or update secret
create_or_update_secret() {
    local secret_name=$1
    local secret_value=$2
    
    echo -n "$secret_value" | gcloud secrets create $secret_name \
        --data-file=- \
        --project=$PROJECT_ID 2>/dev/null || \
    echo -n "$secret_value" | gcloud secrets versions add $secret_name \
        --data-file=- \
        --project=$PROJECT_ID
}

# Create individual PostgreSQL variables (required by backend)
create_or_update_secret "postgres-server-pre" "$POSTGRES_SERVER"
create_or_update_secret "postgres-user-pre" "$DB_USER"
create_or_update_secret "postgres-password-pre" "$DB_PASSWORD"
create_or_update_secret "postgres-db-pre" "$DB_NAME"

# Also create DATABASE_URL for compatibility
if [ "$USE_CLOUD_SQL_PROXY" = "true" ]; then
    DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=${POSTGRES_SERVER}"
    ASYNC_DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=${POSTGRES_SERVER}"
else
    DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@${POSTGRES_SERVER}:5432/${DB_NAME}"
    ASYNC_DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${POSTGRES_SERVER}:5432/${DB_NAME}"
fi

create_or_update_secret "database-url-pre" "$DATABASE_URL"
create_or_update_secret "async-database-url-pre" "$ASYNC_DATABASE_URL"

# Also create SQLALCHEMY_DATABASE_URI (some versions might use this)
create_or_update_secret "sqlalchemy-database-uri-pre" "$DATABASE_URL"

echo "✅ All secrets created/updated"

# Grant permissions to service account
echo ""
echo "7️⃣ Granting permissions..."
SERVICE_ACCOUNT="nexus-cloud-run-pre@${PROJECT_ID}.iam.gserviceaccount.com"

for secret in postgres-server-pre postgres-user-pre postgres-password-pre postgres-db-pre database-url-pre async-database-url-pre sqlalchemy-database-uri-pre; do
    gcloud secrets add-iam-policy-binding $secret \
        --member="serviceAccount:$SERVICE_ACCOUNT" \
        --role="roles/secretmanager.secretAccessor" \
        --project=$PROJECT_ID --quiet 2>/dev/null || true
done

# Grant Cloud SQL client role
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/cloudsql.client" --quiet 2>/dev/null || true

echo "✅ Permissions granted"

# Update Cloud Run service
echo ""
echo "8️⃣ Updating Cloud Run service..."

# Build the secrets update string
SECRETS_UPDATE="POSTGRES_SERVER=postgres-server-pre:latest"
SECRETS_UPDATE+=",POSTGRES_USER=postgres-user-pre:latest"
SECRETS_UPDATE+=",POSTGRES_PASSWORD=postgres-password-pre:latest"
SECRETS_UPDATE+=",POSTGRES_DB=postgres-db-pre:latest"
SECRETS_UPDATE+=",DATABASE_URL=database-url-pre:latest"
SECRETS_UPDATE+=",ASYNC_DATABASE_URL=async-database-url-pre:latest"
SECRETS_UPDATE+=",SQLALCHEMY_DATABASE_URI=sqlalchemy-database-uri-pre:latest"

# Update service with all secrets
gcloud run services update $SERVICE_NAME \
    --update-secrets="$SECRETS_UPDATE" \
    --region=$REGION \
    --project=$PROJECT_ID

# If using Cloud SQL Proxy, ensure the connection is added
if [ "$USE_CLOUD_SQL_PROXY" = "true" ]; then
    echo ""
    echo "Ensuring Cloud SQL connection..."
    gcloud run services update $SERVICE_NAME \
        --add-cloudsql-instances=$CONNECTION_NAME \
        --region=$REGION \
        --project=$PROJECT_ID
fi

echo "✅ Cloud Run service updated"

# Wait for deployment
echo ""
echo "⏳ Waiting for deployment to complete..."
sleep 30

# Test the connection
echo ""
echo "9️⃣ Testing database connection..."
BACKEND_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --project=$PROJECT_ID --format='value(status.url)')

echo "Testing health endpoint..."
response=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/health" || echo "failed")
echo "Health check response: HTTP $response"

if [ "$response" = "200" ]; then
    echo "✅ Backend is healthy!"
else
    echo ""
    echo "⚠️  Backend might still be starting up. Checking logs for database issues..."
    echo ""
    echo "Recent database-related logs:"
    gcloud run logs read $SERVICE_NAME \
        --limit=30 \
        --region=$REGION \
        --project=$PROJECT_ID | grep -E "database|postgres|connection|sqlalchemy|ERROR" | tail -10 || echo "No database logs found"
fi

# Summary
echo ""
echo "✅ Configuration Complete!"
echo "========================="
echo ""
echo "Database Configuration:"
echo "- Instance: $INSTANCE_NAME"
echo "- Database: $DB_NAME"
echo "- User: $DB_USER"
echo "- Connection: ${CONNECTION_NAME}"
echo "- Method: $([ "$USE_CLOUD_SQL_PROXY" = "true" ] && echo "Cloud SQL Proxy" || echo "Private IP")"
echo ""
echo "Environment Variables Set:"
echo "- POSTGRES_SERVER"
echo "- POSTGRES_USER"
echo "- POSTGRES_PASSWORD"
echo "- POSTGRES_DB"
echo "- DATABASE_URL"
echo "- ASYNC_DATABASE_URL"
echo "- SQLALCHEMY_DATABASE_URI"
echo ""
echo "Next Steps:"
echo "1. Monitor logs: gcloud run logs tail $SERVICE_NAME --region=$REGION --project=$PROJECT_ID"
echo "2. Check metrics: https://console.cloud.google.com/run/detail/$REGION/$SERVICE_NAME/metrics?project=$PROJECT_ID"
echo "3. Test API: curl $BACKEND_URL/docs"
echo ""
echo "If still having issues:"
echo "- Ensure the database exists and is accessible"
echo "- Check that the password is correct"
echo "- Verify network connectivity (VPC connector for private IP)"
echo "- Check Cloud SQL Admin API is enabled"