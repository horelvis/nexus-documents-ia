#!/bin/bash

# Script to fix multiple heads in alembic migrations

echo "🔧 Fixing multiple migration heads..."
echo ""

cd ../docker

# Step 1: Show current heads
echo "1️⃣ Current migration heads:"
docker compose exec api alembic heads
echo ""

# Step 2: Show current migration state
echo "2️⃣ Current migration state:"
docker compose exec api alembic current
echo ""

# Step 3: Show migration history
echo "3️⃣ Migration history:"
docker compose exec api alembic history --verbose | head -20
echo ""

# Step 4: Create a merge migration
echo "4️⃣ Creating merge migration..."
docker compose exec api alembic merge -m "merge multiple heads" --rev-id merge_all_heads

echo ""
echo "✅ Merge migration created!"
echo ""
echo "Now run:"
echo "docker compose exec api alembic upgrade heads"
echo ""
echo "Or if you want to upgrade to a specific head:"
echo "docker compose exec api alembic upgrade add_sub_fields_001_safe"
echo "docker compose exec api alembic upgrade merge_signature_ai_heads"