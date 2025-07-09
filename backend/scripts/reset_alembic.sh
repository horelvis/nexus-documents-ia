#!/bin/bash
# Reset alembic version table after removing migration files

echo "This script will clean the alembic_version table"
echo "WARNING: This should only be done after removing all migration files"
echo ""

# Get to backend directory
cd "$(dirname "$0")/.." || exit 1

# Check if we're in docker environment
if [ -f "docker/docker-compose.yml" ]; then
    echo "Using Docker environment..."
    
    # Show current alembic versions
    echo "Current alembic versions in database:"
    docker compose -f docker/docker-compose.yml exec -T db psql -U postgres -d doc_management -c "SELECT * FROM alembic_version;" 2>/dev/null || true
    
    echo ""
    read -p "Do you want to clear all alembic versions? (yes/no): " response
    
    if [ "$response" = "yes" ]; then
        # Clear alembic version table
        docker compose -f docker/docker-compose.yml exec -T db psql -U postgres -d doc_management -c "DELETE FROM alembic_version;" || {
            echo "Failed to clear alembic_version table"
            exit 1
        }
        
        echo ""
        echo "✅ Alembic version table cleared!"
        echo ""
        echo "Next steps:"
        echo "1. Create a new initial migration:"
        echo "   cd backend && alembic revision --autogenerate -m 'Initial migration'"
        echo ""
        echo "2. Review the generated migration file"
        echo ""
        echo "3. Stamp the database as up-to-date:"
        echo "   cd backend && alembic stamp head"
        echo ""
        echo "4. OR if you want to run the migration:"
        echo "   cd backend && alembic upgrade head"
    else
        echo "Aborted."
    fi
else
    echo "Docker compose file not found. Please run from backend directory."
    exit 1
fi