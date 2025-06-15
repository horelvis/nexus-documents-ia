#!/bin/bash

# Database utility commands for Docker environment

case "$1" in
    "status")
        echo "📊 Checking migration status..."
        docker compose exec api python alembic_manager.py status
        ;;
    
    "upgrade")
        echo "⬆️ Applying migrations..."
        docker compose exec api python alembic_manager.py upgrade
        ;;
    
    "downgrade")
        echo "⬇️ Rolling back last migration..."
        docker compose exec api python alembic_manager.py downgrade
        ;;
    
    "create")
        if [ -z "$2" ]; then
            echo "❌ Error: Please provide a migration message"
            echo "Usage: ./db-utils.sh create 'your migration message'"
            exit 1
        fi
        echo "📝 Creating new migration: $2"
        docker compose exec api python alembic_manager.py create --message "$2"
        ;;
    
    "history")
        echo "📜 Migration history:"
        docker compose exec api python alembic_manager.py history
        ;;
    
    "reset")
        echo "⚠️ WARNING: This will reset the database!"
        read -p "Are you sure? (y/N): " confirm
        if [ "$confirm" = "y" ]; then
            echo "🔄 Resetting database..."
            docker compose exec db psql -U postgres -d app -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
            docker compose exec api python alembic_manager.py auto-upgrade
        fi
        ;;
    
    "console")
        echo "🐘 Opening PostgreSQL console..."
        docker compose exec db psql -U postgres -d app
        ;;
    
    *)
        echo "📚 Database Utility Commands:"
        echo ""
        echo "  ./db-utils.sh status      - Check migration status"
        echo "  ./db-utils.sh upgrade     - Apply pending migrations"
        echo "  ./db-utils.sh downgrade   - Rollback last migration"
        echo "  ./db-utils.sh create MSG  - Create new migration"
        echo "  ./db-utils.sh history     - Show migration history"
        echo "  ./db-utils.sh reset       - Reset database (DANGER!)"
        echo "  ./db-utils.sh console     - Open PostgreSQL console"
        echo ""
        ;;
esac