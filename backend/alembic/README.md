# Alembic Migration Best Practices

## 🚨 Common Issues and How to Prevent Them

### 1. Multiple Heads
**Problem**: Multiple migration branches that aren't connected.
**Prevention**: 
- Always use `migration_manager.py` to create migrations
- Run `python scripts/migration_manager.py check` before creating new migrations
- Use timestamp-based revision IDs

### 2. Duplicate Columns/Tables
**Problem**: Migrations fail because columns/tables already exist.
**Prevention**:
- Use safe migration functions (see template below)
- Always check if objects exist before creating them
- Use `--autogenerate` carefully and review the generated code

### 3. Circular Dependencies
**Problem**: Migrations depend on each other in a circular way.
**Prevention**:
- Keep migrations linear
- Don't manually edit down_revision unless necessary
- Use the migration manager to create migrations

## 🛠️ Tools and Commands

### Migration Manager
The `migration_manager.py` script provides safe migration operations:

```bash
# Check for issues
python scripts/migration_manager.py check

# Create a safe migration
python scripts/migration_manager.py create "add new feature"

# Apply migrations with safety checks
python scripts/migration_manager.py upgrade

# Fix multiple heads
python scripts/migration_manager.py fix-heads

# Show detailed status
python scripts/migration_manager.py status
```

### Safe Migration Template
All new migrations should use these helper functions:

```python
def table_exists(table_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()

def column_exists(table_name, column_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    if not table_exists(table_name):
        return False
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def upgrade():
    # Safe column addition
    if not column_exists('users', 'new_column'):
        op.add_column('users', sa.Column('new_column', sa.String(50)))
    
    # Safe table creation
    if not table_exists('new_table'):
        op.create_table('new_table', 
            sa.Column('id', sa.UUID(), primary_key=True),
            # ... other columns
        )
```

## 📋 Migration Checklist

Before creating a migration:
- [ ] Run `migration_manager.py check`
- [ ] Pull latest changes from repository
- [ ] Ensure database is in clean state

When creating a migration:
- [ ] Use `migration_manager.py create "description"`
- [ ] Review the generated migration
- [ ] Add safety checks if needed
- [ ] Test in development first

After creating a migration:
- [ ] Run `migration_manager.py upgrade` locally
- [ ] Verify database state
- [ ] Commit both migration file and this tracking file

## 🚑 Emergency Fixes

### Fix Multiple Heads
```bash
python scripts/migration_manager.py fix-heads
# or manually:
alembic merge -m "merge heads"
alembic upgrade head
```

### Skip Failed Migration
```bash
# Mark migration as complete without running it
docker compose exec db psql -U postgres -d nouxcube -c "UPDATE alembic_version SET version_num = 'revision_id';"
```

### Reset Migration State
```bash
# DANGER: Only in development!
docker compose exec db psql -U postgres -d nouxcube -c "DELETE FROM alembic_version;"
docker compose exec db psql -U postgres -d nouxcube -c "INSERT INTO alembic_version VALUES ('initial_revision_id');"
```

## 🎯 Best Practices

1. **One Change Per Migration**: Keep migrations focused
2. **Descriptive Names**: Use clear, descriptive migration messages
3. **Test First**: Always test migrations in development
4. **No Manual Edits**: Avoid manually editing revision IDs
5. **Safety First**: Always use existence checks
6. **Document Changes**: Add comments explaining why changes are needed

## 🔄 Workflow

1. Before starting work:
   ```bash
   git pull
   python scripts/migration_manager.py check
   python scripts/migration_manager.py upgrade
   ```

2. Create migration:
   ```bash
   python scripts/migration_manager.py create "add user preferences"
   ```

3. Apply and test:
   ```bash
   python scripts/migration_manager.py upgrade
   # Test your changes
   ```

4. Commit:
   ```bash
   git add alembic/versions/
   git commit -m "Add migration: user preferences"
   ```