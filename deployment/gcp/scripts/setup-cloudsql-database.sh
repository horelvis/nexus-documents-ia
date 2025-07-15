#!/bin/bash
# Setup Cloud SQL Database with all configurations
# This script creates and configures Cloud SQL instance and database

set -e

echo "🗄️  Setting up Cloud SQL Database"
echo "================================"
echo ""

# Configuration
PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
INSTANCE_NAME="nexusdocs-pre"
DB_NAME="nexusdocs"
DB_USER="postgres"
SERVICE_ACCOUNT="nexus-cloud-run-pre@${PROJECT_ID}.iam.gserviceaccount.com"

# Check if instance exists
echo "1️⃣ Checking for existing Cloud SQL instance..."
if gcloud sql instances describe $INSTANCE_NAME --project=$PROJECT_ID >/dev/null 2>&1; then
    echo "✅ Cloud SQL instance '$INSTANCE_NAME' already exists"
else
    echo "Creating Cloud SQL instance..."
    gcloud sql instances create $INSTANCE_NAME \
        --database-version=POSTGRES_15 \
        --tier=db-g1-small \
        --region=$REGION \
        --network=projects/$PROJECT_ID/global/networks/default \
        --no-assign-ip \
        --project=$PROJECT_ID
    
    echo "✅ Cloud SQL instance created"
fi

# Get instance details
echo ""
echo "2️⃣ Getting instance details..."
CONNECTION_NAME="${PROJECT_ID}:${REGION}:${INSTANCE_NAME}"
PRIVATE_IP=$(gcloud sql instances describe $INSTANCE_NAME --project=$PROJECT_ID --format="value(ipAddresses[0].ipAddress)" 2>/dev/null | grep -E "10\.|172\.|192\." || echo "")
PUBLIC_IP=$(gcloud sql instances describe $INSTANCE_NAME --project=$PROJECT_ID --format="value(ipAddresses[0].ipAddress)" 2>/dev/null | grep -v -E "10\.|172\.|192\." || echo "")

echo "Connection name: $CONNECTION_NAME"
echo "Private IP: ${PRIVATE_IP:-none}"
echo "Public IP: ${PUBLIC_IP:-none}"

# Create database
echo ""
echo "3️⃣ Creating database..."
if gcloud sql databases list --instance=$INSTANCE_NAME --project=$PROJECT_ID | grep -q $DB_NAME; then
    echo "✅ Database '$DB_NAME' already exists"
else
    gcloud sql databases create $DB_NAME --instance=$INSTANCE_NAME --project=$PROJECT_ID
    echo "✅ Database created"
fi

# Set password
echo ""
echo "4️⃣ Setting database password..."
if [ -z "$DB_PASSWORD" ]; then
    read -sp "Enter database password for user '$DB_USER': " DB_PASSWORD
    echo ""
fi

gcloud sql users set-password $DB_USER \
    --instance=$INSTANCE_NAME \
    --password="$DB_PASSWORD" \
    --project=$PROJECT_ID

echo "✅ Password set"

# Create all required secrets
echo ""
echo "5️⃣ Creating database secrets..."

# Determine connection method
if [ ! -z "$PRIVATE_IP" ]; then
    POSTGRES_SERVER="$PRIVATE_IP"
    echo "Using private IP connection"
else
    POSTGRES_SERVER="/cloudsql/$CONNECTION_NAME"
    echo "Using Cloud SQL Proxy (Unix socket)"
fi

# Function to create/update secret
create_secret() {
    local name=$1
    local value=$2
    echo "Creating/updating secret: $name"
    echo -n "$value" | gcloud secrets create $name --data-file=- --project=$PROJECT_ID 2>/dev/null || \
    echo -n "$value" | gcloud secrets versions add $name --data-file=- --project=$PROJECT_ID
}

# Create individual PostgreSQL secrets
create_secret "postgres-server-pre" "$POSTGRES_SERVER"
create_secret "postgres-user-pre" "$DB_USER"
create_secret "postgres-password-pre" "$DB_PASSWORD"
create_secret "postgres-db-pre" "$DB_NAME"

# Create connection URLs
if [[ "$POSTGRES_SERVER" == *"/cloudsql/"* ]]; then
    DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=${POSTGRES_SERVER}"
    ASYNC_DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=${POSTGRES_SERVER}"
else
    DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@${POSTGRES_SERVER}:5432/${DB_NAME}"
    ASYNC_DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${POSTGRES_SERVER}:5432/${DB_NAME}"
fi

create_secret "database-url-pre" "$DATABASE_URL"
create_secret "async-database-url-pre" "$ASYNC_DATABASE_URL"
create_secret "sqlalchemy-database-uri-pre" "$DATABASE_URL"

# Grant permissions
echo ""
echo "6️⃣ Granting permissions to service account..."
for secret in postgres-server-pre postgres-user-pre postgres-password-pre postgres-db-pre database-url-pre async-database-url-pre sqlalchemy-database-uri-pre; do
    gcloud secrets add-iam-policy-binding $secret \
        --member="serviceAccount:$SERVICE_ACCOUNT" \
        --role="roles/secretmanager.secretAccessor" \
        --project=$PROJECT_ID --quiet || echo "Permission might already exist"
done

# Grant Cloud SQL client role
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/cloudsql.client" --quiet || echo "Role might already exist"

echo ""
echo "✅ Cloud SQL setup complete!"
echo ""
echo "Summary:"
echo "- Instance: $INSTANCE_NAME"
echo "- Database: $DB_NAME"
echo "- User: $DB_USER"
echo "- Connection: $CONNECTION_NAME"
echo "- Secrets created for all database variables"
echo ""
echo "The following secrets are available:"
echo "- postgres-server-pre"
echo "- postgres-user-pre"
echo "- postgres-password-pre"
echo "- postgres-db-pre"
echo "- database-url-pre"
echo "- async-database-url-pre"
echo "- sqlalchemy-database-uri-pre"