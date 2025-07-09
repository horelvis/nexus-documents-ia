#!/bin/bash
# Clear alembic version table

cd "$(dirname "$0")/.." || exit 1

echo "Clearing alembic_version table..."
docker compose -f docker/docker-compose.yml exec -T db psql -U postgres -d doc_management -c "DELETE FROM alembic_version;" 2>/dev/null || {
    echo "Note: Could not clear alembic_version table (might already be empty)"
}

echo "✅ Done!"
echo ""
echo "Next steps:"
echo "1. Create a new initial migration:"
echo "   cd backend && alembic revision --autogenerate -m 'Initial migration'"
echo ""
echo "2. Stamp the database (if tables already exist):"
echo "   cd backend && alembic stamp head"
echo ""
echo "3. Or run the migration (if starting fresh):"
echo "   cd backend && alembic upgrade head"