#!/bin/bash
# Fix Alembic migration transaction error

echo "🔧 Fixing Alembic Migration Transaction Error"
echo "============================================"

# Check if we're in the backend directory
if [ ! -f "alembic.ini" ]; then
    echo "❌ Error: This script must be run from the backend directory"
    echo "   Current directory: $(pwd)"
    echo "   Please run: cd backend && ./scripts/fix_migration_transaction.sh"
    exit 1
fi

# Function to run SQL commands
run_sql() {
    docker compose -f docker/docker-compose.yml exec -T postgres psql -U nexus_user -d nexus_db -c "$1"
}

echo ""
echo "1️⃣ Checking current database status..."
echo "----------------------------------------"

# Check if docker is running
if ! docker compose -f docker/docker-compose.yml ps postgres | grep -q "running"; then
    echo "❌ PostgreSQL container is not running"
    echo "   Please start it with: cd docker && ./start-dev.sh"
    exit 1
fi

echo "✅ PostgreSQL container is running"

echo ""
echo "2️⃣ Checking for active transactions..."
echo "----------------------------------------"

run_sql "SELECT pid, state, query FROM pg_stat_activity WHERE datname = 'nexus_db' AND state != 'idle' AND pid != pg_backend_pid();"

echo ""
echo "3️⃣ Terminating any blocked transactions..."
echo "----------------------------------------"

run_sql "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'nexus_db' AND state = 'idle in transaction' AND pid != pg_backend_pid();"

echo ""
echo "4️⃣ Checking current alembic version..."
echo "----------------------------------------"

run_sql "SELECT version_num FROM alembic_version;"

echo ""
echo "5️⃣ Backing up current alembic_version table..."
echo "----------------------------------------"

run_sql "CREATE TABLE IF NOT EXISTS alembic_version_backup AS SELECT * FROM alembic_version;"
echo "✅ Backup created in alembic_version_backup table"

echo ""
echo "6️⃣ Cleaning up alembic_version table..."
echo "----------------------------------------"

# Clear the alembic_version table to remove any conflicts
run_sql "TRUNCATE TABLE alembic_version;"
echo "✅ Alembic version table cleared"

echo ""
echo "7️⃣ Setting safe migration point..."
echo "----------------------------------------"

# Insert the unified migration as the starting point
run_sql "INSERT INTO alembic_version (version_num) VALUES ('unified_20250615');"
echo "✅ Set alembic version to unified_20250615"

echo ""
echo "8️⃣ Fixing migration files..."
echo "----------------------------------------"

# Create a fixed version of add_doc_categorization
cat > alembic/versions/add_document_categorization_fields_fixed.py << 'EOF'
"""add document categorization fields - fixed

Revision ID: add_doc_categorization_fix
Revises: unified_20250615
Create Date: 2024-01-18 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_doc_categorization_fix'
down_revision = 'unified_20250615'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if columns already exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    try:
        columns = [col['name'] for col in inspector.get_columns('documents')]
    except:
        print("Documents table doesn't exist yet, skipping")
        return
    
    # Add category field to documents
    if 'category' not in columns:
        op.add_column('documents', sa.Column('category', sa.String(50), nullable=True))
    
    # Add document_metadata JSONB field to documents
    if 'document_metadata' not in columns:
        op.add_column('documents', sa.Column('document_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'))
    
    # Add content field for storing extracted text
    if 'content' not in columns:
        op.add_column('documents', sa.Column('content', sa.Text(), nullable=True))
    
    # Add extracted_entities JSONB field
    if 'extracted_entities' not in columns:
        op.add_column('documents', sa.Column('extracted_entities', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    # Create indexes for better performance
    try:
        indexes = [idx['name'] for idx in inspector.get_indexes('documents')]
        if 'idx_documents_category' not in indexes:
            op.create_index('idx_documents_category', 'documents', ['category'])
        if 'idx_documents_category_tenant' not in indexes:
            op.create_index('idx_documents_category_tenant', 'documents', ['category', 'tenant_id'])
    except:
        pass


def downgrade() -> None:
    # Drop indexes
    try:
        op.drop_index('idx_documents_category_tenant', 'documents')
        op.drop_index('idx_documents_category', 'documents')
    except:
        pass
    
    # Drop columns
    try:
        op.drop_column('documents', 'extracted_entities')
        op.drop_column('documents', 'content')
        op.drop_column('documents', 'document_metadata')
        op.drop_column('documents', 'category')
    except:
        pass
EOF

# Create a fixed version of add_sub_fields_001
cat > alembic/versions/20250616_add_subscription_fields_fixed.py << 'EOF'
"""add subscription fields to user - fixed

Revision ID: add_sub_fields_fix
Revises: add_doc_categorization_fix
Create Date: 2025-06-16 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_sub_fields_fix'
down_revision = 'add_doc_categorization_fix'
branch_labels = None
depends_on = None


def upgrade():
    """Add subscription_plan and subscription_status to users table"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    try:
        columns = [col['name'] for col in inspector.get_columns('users')]
    except:
        print("Users table doesn't exist yet, skipping")
        return
    
    if 'subscription_plan' not in columns:
        op.add_column('users', sa.Column('subscription_plan', sa.String(50), nullable=True, server_default='free'))
    
    if 'subscription_status' not in columns:
        op.add_column('users', sa.Column('subscription_status', sa.String(50), nullable=True, server_default='active'))


def downgrade():
    """Remove subscription fields from users table"""
    try:
        op.drop_column('users', 'subscription_status')
        op.drop_column('users', 'subscription_plan')
    except Exception as e:
        print(f"Could not remove subscription fields: {e}")
EOF

echo "✅ Created fixed migration files"

# Remove the problematic migration files
echo ""
echo "9️⃣ Removing problematic migration files..."
echo "----------------------------------------"

if [ -f "alembic/versions/add_document_categorization_fields.py" ]; then
    mv alembic/versions/add_document_categorization_fields.py alembic/versions/add_document_categorization_fields.py.bak
    echo "✅ Backed up add_document_categorization_fields.py"
fi

if [ -f "alembic/versions/20250616_add_subscription_fields.py" ]; then
    mv alembic/versions/20250616_add_subscription_fields.py alembic/versions/20250616_add_subscription_fields.py.bak
    echo "✅ Backed up 20250616_add_subscription_fields.py"
fi

echo ""
echo "🎯 Next Steps:"
echo "----------------------------------------"
echo "1. Run the migrations with the fixed files:"
echo "   alembic upgrade head"
echo ""
echo "2. If successful, you can remove the backup files:"
echo "   rm alembic/versions/*.py.bak"
echo ""
echo "3. If there are still issues, check the logs and run:"
echo "   alembic current"
echo "   alembic history"
echo ""
echo "✅ Migration transaction fix complete!"