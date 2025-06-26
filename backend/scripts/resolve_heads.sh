#!/bin/bash

# Script to resolve multiple heads issue

echo "🔧 Resolving multiple heads in migrations..."
echo ""

cd ../docker

# Option 1: Upgrade to all heads
echo "Option 1: Upgrading to all heads..."
docker compose exec api alembic upgrade heads

# If that doesn't work, try option 2
if [ $? -ne 0 ]; then
    echo ""
    echo "Option 2: Creating a merge migration..."
    
    # First, check the current state
    echo "Current state:"
    docker compose exec api alembic current
    
    # Create merge migration
    docker compose exec api alembic merge -m "merge subscription and signature heads"
    
    # Then upgrade
    docker compose exec api alembic upgrade head
fi

echo ""
echo "✅ Done!"