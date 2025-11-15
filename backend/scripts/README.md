# Backend Scripts

This directory contains utility scripts for managing the Nexus Document Backend system.

## Database Migration Scripts

### Core Migration Tools
- **`alembic_utils.py`** - Comprehensive Alembic migration utilities
  - Check for migration issues (multiple heads, missing dependencies)
  - Fix multiple heads automatically
  - Visualize migration dependency graph
  - Usage: `python alembic_utils.py [check|fix|visualize]`

- **`alembic_safe_migrate.py`** - Safe migration runner with conflict detection
  - Prevents duplicate table/column errors
  - Can mark migrations as applied without running them
  - Syncs alembic version with actual database state
  - Usage: `python alembic_safe_migrate.py [--check|--dry-run|--fix-script|--mark-applied|--sync]`

- **`create_migration.py`** - Safe migration creation tool
  - Prevents multiple heads
  - Supports auto-generation from model changes
  - Usage: `python create_migration.py -m "description" [--autogenerate]`

- **`migration_manager.py`** - Additional migration management utilities
- **`docker_migration.sh`** - Docker-based migration management (backup, fix, reset)
- **`analyze_migrations.py`** - Analyze migration files and database state
- **`check_migration_status.py`** - Check current migration status and active transactions
- **`recover_migrations.py`** - Recovery tool for broken migrations
- **`reset_migrations.py`** - Reset all migrations to current state

## Database Setup & Initialization

- **`init_db.py`** - Main database initialization script
  - Creates all tables
  - Runs initial migrations
  - Seeds default data
  - Usage: `python init_db.py`

- **`setup_db.py`** - Production database setup script
  - Creates database if not exists
  - Sets up proper permissions
  - Usage: `python setup_db.py`

## Data Management

- **`seed_data.py`** - Seed database with sample data
- **`clean_dev_data.py`** - Clean development data while preserving structure
- **`add_test_users.py`** - Add test users for development
- **`make_superuser.py`** - Create or update superuser accounts
- **`reindex_documents.py`** - Reindex all documents in vector database
- **`migrate_extract_entities_langextract.py`** - Extrae entidades de documentos existentes usando el microservicio LangExtract (batch/filtros por tenant)

## Service Configuration

- **`init_agents.py`** - Initialize AI agents in the system
- **`setup_signature_provider.py`** - Configure signature providers (DocuSign, YouSign, etc.)
- **`generate_api_key.py`** - Generate secure API keys

## Stripe Integration

- **`create_stripe_products.py`** - Create Stripe products and pricing
- **`configure_stripe_portal.py`** - Configure Stripe customer portal
- **`verify_stripe_config.py`** - Verify Stripe configuration

## Development Tools

- **`generate_api_docs.py`** - Generate API documentation
- **`test_entity_search.py`** - Test entity search functionality

## Usage Examples

### Initialize a new database
```bash
python init_db.py
```

### Create a new migration safely
```bash
python create_migration.py -m "add new feature" --autogenerate
```

### Check and fix migration issues
```bash
python alembic_utils.py check
python alembic_utils.py fix
```

### Run migrations safely
```bash
python alembic_safe_migrate.py --check
python alembic_safe_migrate.py
```

### Add a superuser
```bash
python make_superuser.py
```

### Setup signature providers
```bash
python setup_signature_provider.py
```

## Best Practices

1. Always use `create_migration.py` instead of `alembic revision` directly
2. Check for migration issues with `alembic_utils.py check` before creating new migrations
3. Use `alembic_safe_migrate.py` for running migrations in production
4. Back up your database before running any migration scripts
5. Use `init_db.py` for initial setup, not for existing databases
