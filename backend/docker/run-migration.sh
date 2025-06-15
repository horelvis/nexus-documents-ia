#!/bin/bash

echo "🔄 Running database migrations..."

# Run alembic migrations inside the API container
docker compose exec api python -m alembic upgrade head

echo "✅ Migrations complete!"

# Show current migration status
echo ""
echo "📊 Current migration status:"
docker compose exec api python -m alembic current