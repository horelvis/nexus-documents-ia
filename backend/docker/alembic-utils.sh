#!/bin/bash

# Alembic utility commands for Docker environment

COMPOSE="docker compose -f docker/docker-compose.yml"

case "$1" in
    "current")
        echo "📊 Current Alembic revision:"
        $COMPOSE exec api bash -lc "cd /app && alembic current"
        ;;
    
    "history")
        echo "📜 Alembic migration history:"
        $COMPOSE exec api bash -lc "cd /app && alembic history"
        ;;
    
    "heads")
        echo "🎯 Alembic heads:"
        $COMPOSE exec api bash -lc "cd /app && alembic heads"
        ;;
    
    "upgrade")
        echo "⬆️ Upgrading to head..."
        $COMPOSE exec api bash -lc "cd /app && alembic upgrade head"
        ;;
    
    "stamp")
        if [ -z "$2" ]; then
            echo "❌ Please provide a revision to stamp"
            exit 1
        fi
        echo "📌 Stamping revision: $2"
        $COMPOSE exec api bash -lc "cd /app && alembic stamp $2"
        ;;
    
    "fix")
        echo "🔧 Fixing Alembic state..."
        # First check current state
        $COMPOSE exec api python check_alembic_state.py
        
        # Try to fix
        echo ""
        read -p "Do you want to fix the revision chain? (y/N): " confirm
        if [ "$confirm" = "y" ]; then
            $COMPOSE exec api python fix_alembic_chain.py
        fi
        ;;
    
    "create")
        if [ -z "$2" ]; then
            echo "❌ Please provide a migration message"
            exit 1
        fi
        echo "📝 Creating migration: $2"
        $COMPOSE exec api bash -lc "cd /app && alembic revision --autogenerate -m \"$2\""
        ;;
    
    *)
        echo "📚 Alembic Utility Commands:"
        echo ""
        echo "  ./alembic-utils.sh current     - Show current revision"
        echo "  ./alembic-utils.sh history     - Show migration history"
        echo "  ./alembic-utils.sh heads       - Show all heads"
        echo "  ./alembic-utils.sh upgrade     - Upgrade to latest"
        echo "  ./alembic-utils.sh stamp REV   - Stamp specific revision"
        echo "  ./alembic-utils.sh fix         - Fix revision chain"
        echo "  ./alembic-utils.sh create MSG  - Create new migration"
        echo ""
        ;;
esac
