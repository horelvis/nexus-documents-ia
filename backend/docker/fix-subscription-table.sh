#!/bin/bash

echo "🔧 Fixing subscription table schema..."

# Run the fix script inside the API container
docker compose exec api python fix_subscription_table.py

echo "✅ Fix complete!"