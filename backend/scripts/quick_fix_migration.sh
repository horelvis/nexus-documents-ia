#!/bin/bash

# Quick fix for duplicate column migration error

echo "🚀 Quick fix for migration error..."
echo ""

cd ../docker

# Step 1: Mark the problematic migration as completed
echo "1️⃣ Marking add_sub_fields_001 migration as completed..."
docker compose exec db psql -U postgres -d nexus_db -c "UPDATE alembic_version SET version_num = 'add_sub_fields_001' WHERE version_num = 'add_doc_categorization';"

echo ""
echo "2️⃣ Current migration status:"
docker compose exec db psql -U postgres -d nexus_db -c "SELECT version_num FROM alembic_version;"

echo ""
echo "✅ Migration marked as completed!"
echo ""
echo "Now run: docker compose exec api alembic upgrade head"