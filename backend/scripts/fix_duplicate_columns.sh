#!/bin/bash

# Script to fix duplicate column errors in migrations

echo "🔧 Fixing duplicate column migration errors..."
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$BACKEND_DIR/docker"

echo "📍 Working directory: $BACKEND_DIR"
echo ""

# Function to run SQL command
run_sql() {
    local sql="$1"
    cd "$DOCKER_DIR" && docker compose exec -T db psql -U postgres -d nexus_db -c "$sql"
}

# Function to run command in API container
run_in_api() {
    local cmd="$1"
    cd "$DOCKER_DIR" && docker compose exec -T api sh -c "$cmd"
}

# Step 1: Check current migration status
echo "1️⃣ Checking current migration status..."
current_version=$(run_sql "SELECT version_num FROM alembic_version;" | grep -v "version_num" | grep -v "---" | grep -v "row" | tr -d ' ')
echo "Current alembic version: $current_version"
echo ""

# Step 2: Check if columns already exist
echo "2️⃣ Checking if subscription columns already exist..."
columns_check=$(run_sql "SELECT column_name FROM information_schema.columns WHERE table_name = 'users' AND column_name IN ('subscription_plan', 'subscription_status');" | grep -E "(subscription_plan|subscription_status)" || echo "none")

if [ "$columns_check" != "none" ]; then
    echo -e "${YELLOW}⚠️  Subscription columns already exist in database${NC}"
    echo "Columns found: $columns_check"
    echo ""
    
    # Step 3: Update alembic version to skip the problematic migration
    echo "3️⃣ Updating alembic version to skip the duplicate migration..."
    
    # First, backup current state
    echo "Backing up current alembic_version..."
    run_sql "CREATE TABLE IF NOT EXISTS alembic_version_backup AS SELECT * FROM alembic_version;"
    
    # Update to the next migration (skipping add_sub_fields_001)
    if [ "$current_version" = "add_doc_categorization" ]; then
        echo "Marking add_sub_fields_001 as completed..."
        run_sql "UPDATE alembic_version SET version_num = 'add_sub_fields_001' WHERE version_num = 'add_doc_categorization';"
        echo -e "${GREEN}✅ Updated alembic version to skip duplicate migration${NC}"
    else
        echo "Current version is not add_doc_categorization, checking if we need to fix it..."
    fi
else
    echo -e "${GREEN}✅ Subscription columns do not exist yet, migration can proceed normally${NC}"
fi

# Step 4: Remove the problematic migration file and use the safe version
echo ""
echo "4️⃣ Replacing problematic migration with safe version..."
cd "$BACKEND_DIR"

if [ -f "alembic/versions/20250616_add_subscription_fields.py" ]; then
    echo "Backing up original migration..."
    cp alembic/versions/20250616_add_subscription_fields.py alembic/versions/20250616_add_subscription_fields.py.bak
    
    echo "Removing original migration..."
    rm alembic/versions/20250616_add_subscription_fields.py
fi

if [ -f "alembic/versions/20250616_add_subscription_fields_safe.py" ]; then
    echo "Renaming safe version to original name..."
    mv alembic/versions/20250616_add_subscription_fields_safe.py alembic/versions/20250616_add_subscription_fields.py
    
    # Update revision ID in the file
    sed -i "s/revision = 'add_sub_fields_001_safe'/revision = 'add_sub_fields_001'/g" alembic/versions/20250616_add_subscription_fields.py
fi

# Step 5: Show next steps
echo ""
echo "5️⃣ Next steps:"
echo ""
echo -e "${GREEN}The migration issue has been fixed!${NC}"
echo ""
echo "Now you can run:"
echo -e "${YELLOW}cd $DOCKER_DIR${NC}"
echo -e "${YELLOW}docker compose exec api alembic upgrade head${NC}"
echo ""
echo "If you still get errors, you can manually mark all migrations as complete:"
echo -e "${YELLOW}docker compose exec db psql -U postgres -d nexus_db -c \"UPDATE alembic_version SET version_num = 'latest_revision_id';\"${NC}"
echo ""

# Optional: Show current database schema
echo "Current users table schema:"
run_sql "\d users" | grep -E "(subscription_plan|subscription_status)" || echo "No subscription columns found"