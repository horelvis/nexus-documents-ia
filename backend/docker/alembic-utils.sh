#!/bin/bash

# Alembic utility commands for Docker environment

case "$1" in
    "current")
        echo "📊 Current Alembic revision:"
        docker compose exec api python -m alembic current
        ;;
    
    "history")
        echo "📜 Alembic migration history:"
        docker compose exec api python -m alembic history
        ;;
    
    "heads")
        echo "🎯 Alembic heads:"
        docker compose exec api python -m alembic heads
        ;;
    
    "upgrade")
        echo "⬆️ Upgrading to head..."
        docker compose exec api python -m alembic upgrade head
        ;;
    
    "stamp")
        if [ -z "$2" ]; then
            echo "❌ Please provide a revision to stamp"
            exit 1
        fi
        echo "📌 Stamping revision: $2"
        docker compose exec api python -m alembic stamp $2
        ;;
    
    "fix")
        echo "🔧 Fixing Alembic state..."
        # First check current state
        docker compose exec api python check_alembic_state.py
        
        # Try to fix
        echo ""
        read -p "Do you want to fix the revision chain? (y/N): " confirm
        if [ "$confirm" = "y" ]; then
            docker compose exec api python fix_alembic_chain.py
        fi
        ;;
    
    "create")
        if [ -z "$2" ]; then
            echo "❌ Please provide a migration message"
            exit 1
        fi
        echo "📝 Creating migration: $2"
        docker compose exec api python -m alembic revision --autogenerate -m "$2"
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