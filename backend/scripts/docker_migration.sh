#!/bin/bash

# Enhanced Docker Migration Script
# Handles common migration issues automatically

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
DOCKER_COMPOSE="docker compose"
DB_NAME="nexus_db"
DB_USER="postgres"
BACKUP_DIR="./migration_backups"

# Ensure we're in the docker directory
cd "$(dirname "$0")/../docker" || exit 1

echo -e "${BLUE}🚀 Enhanced Migration Manager${NC}"
echo "================================"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Function to run command in API container
run_in_api() {
    $DOCKER_COMPOSE exec -T api "$@"
}

# Function to run SQL
run_sql() {
    $DOCKER_COMPOSE exec -T db psql -U "$DB_USER" -d "$DB_NAME" -c "$1"
}

# Function to backup database
backup_db() {
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="$BACKUP_DIR/backup_${timestamp}.sql"
    
    echo -e "${YELLOW}📦 Creating database backup...${NC}"
    $DOCKER_COMPOSE exec -T db pg_dump -U "$DB_USER" "$DB_NAME" > "$backup_file"
    echo -e "${GREEN}✅ Backup saved to: $backup_file${NC}"
}

# Function to check migration status
check_status() {
    echo -e "\n${BLUE}📊 Current Migration Status${NC}"
    echo "------------------------"
    
    # Current revision
    echo -e "\n${YELLOW}Current revision:${NC}"
    run_in_api alembic current 2>/dev/null || echo "No current revision"
    
    # Check for multiple heads
    echo -e "\n${YELLOW}Checking for multiple heads:${NC}"
    heads=$(run_in_api alembic heads 2>/dev/null | grep -c "(head)" || echo "0")
    
    if [ "$heads" -gt 1 ]; then
        echo -e "${RED}⚠️  Multiple heads detected!${NC}"
        run_in_api alembic heads
        return 1
    else
        echo -e "${GREEN}✅ Single head found${NC}"
        return 0
    fi
}

# Function to fix multiple heads
fix_multiple_heads() {
    echo -e "\n${YELLOW}🔧 Fixing multiple heads...${NC}"
    
    # Get head revisions
    heads=$(run_in_api alembic heads | grep "(head)" | awk '{print $1}')
    head_count=$(echo "$heads" | wc -l)
    
    if [ "$head_count" -gt 1 ]; then
        echo "Found $head_count heads. Creating merge migration..."
        
        # Create merge migration
        timestamp=$(date +%Y%m%d_%H%M%S)
        run_in_api alembic merge -m "auto_merge_$timestamp" --rev-id "merge_$timestamp"
        
        echo -e "${GREEN}✅ Merge migration created${NC}"
        return 0
    else
        echo "No multiple heads to fix"
        return 0
    fi
}

# Function to check for duplicate columns
check_duplicate_columns() {
    local table=$1
    local column=$2
    
    result=$(run_sql "SELECT column_name FROM information_schema.columns WHERE table_name = '$table' AND column_name = '$column';" | grep -c "$column" || echo "0")
    
    if [ "$result" -gt 0 ]; then
        return 0  # Column exists
    else
        return 1  # Column doesn't exist
    fi
}

# Function to safely apply migrations
safe_upgrade() {
    echo -e "\n${BLUE}🚀 Applying migrations safely...${NC}"
    
    # First, check status
    if ! check_status; then
        echo -e "${YELLOW}Attempting to fix issues...${NC}"
        fix_multiple_heads
    fi
    
    # Try to upgrade
    echo -e "\n${YELLOW}Running alembic upgrade...${NC}"
    
    if run_in_api alembic upgrade head 2>&1 | tee /tmp/migration_output.txt; then
        echo -e "${GREEN}✅ Migrations applied successfully!${NC}"
        return 0
    else
        # Check for common errors
        if grep -q "Multiple head revisions" /tmp/migration_output.txt; then
            echo -e "${YELLOW}Fixing multiple heads and retrying...${NC}"
            fix_multiple_heads
            run_in_api alembic upgrade head
        elif grep -q "already exists" /tmp/migration_output.txt; then
            echo -e "${RED}⚠️  Column/table already exists error detected${NC}"
            echo "You may need to manually skip this migration or update the migration file"
            return 1
        else
            echo -e "${RED}❌ Migration failed with unknown error${NC}"
            return 1
        fi
    fi
}

# Function to create migration
create_migration() {
    local message=$1
    
    if [ -z "$message" ]; then
        echo -e "${RED}❌ Please provide a migration message${NC}"
        echo "Usage: $0 create 'your migration message'"
        return 1
    fi
    
    echo -e "\n${BLUE}📝 Creating migration: $message${NC}"
    
    # Check for issues first
    if ! check_status; then
        echo -e "${YELLOW}⚠️  Issues detected. Fix them first with: $0 fix${NC}"
        return 1
    fi
    
    # Create migration with timestamp to avoid conflicts
    timestamp=$(date +%Y%m%d%H%M%S)
    safe_message=$(echo "$message" | tr ' ' '_' | tr -cd '[:alnum:]_')
    rev_id="${safe_message}_${timestamp}"
    
    run_in_api alembic revision --autogenerate -m "$message" --rev-id "$rev_id"
    
    echo -e "${GREEN}✅ Migration created with ID: $rev_id${NC}"
}

# Function to show history
show_history() {
    echo -e "\n${BLUE}📜 Migration History${NC}"
    echo "-------------------"
    run_in_api alembic history --verbose
}

# Function to reset migrations (DANGER!)
reset_migrations() {
    echo -e "\n${RED}⚠️  WARNING: This will reset all migrations!${NC}"
    echo "This should only be used in development."
    read -p "Are you sure? (type 'yes' to confirm): " confirm
    
    if [ "$confirm" != "yes" ]; then
        echo "Cancelled."
        return 1
    fi
    
    backup_db
    
    echo -e "\n${YELLOW}Resetting migrations...${NC}"
    run_sql "DROP TABLE IF EXISTS alembic_version CASCADE;"
    
    echo -e "${GREEN}✅ Migration table reset. You can now run fresh migrations.${NC}"
}

# Main menu
case "${1:-help}" in
    check)
        check_status
        ;;
    
    upgrade|up)
        backup_db
        safe_upgrade
        ;;
    
    create)
        create_migration "$2"
        ;;
    
    fix)
        backup_db
        fix_multiple_heads
        safe_upgrade
        ;;
    
    history)
        show_history
        ;;
    
    status)
        check_status
        echo -e "\n${BLUE}Database Tables:${NC}"
        run_sql "\dt" | grep -E "(users|documents|signature_contacts)"
        ;;
    
    reset)
        reset_migrations
        ;;
    
    backup)
        backup_db
        ;;
    
    help|*)
        echo "Usage: $0 {command} [options]"
        echo ""
        echo "Commands:"
        echo "  check    - Check migration status and issues"
        echo "  upgrade  - Apply pending migrations safely"
        echo "  create   - Create a new migration"
        echo "  fix      - Fix common migration issues"
        echo "  history  - Show migration history"
        echo "  status   - Show detailed status"
        echo "  reset    - Reset all migrations (DANGER!)"
        echo "  backup   - Create database backup"
        echo ""
        echo "Examples:"
        echo "  $0 check"
        echo "  $0 upgrade"
        echo "  $0 create 'add user preferences'"
        echo "  $0 fix"
        ;;
esac