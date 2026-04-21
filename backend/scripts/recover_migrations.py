#!/usr/bin/env python3
"""
Comprehensive migration recovery script for fixing transaction and dependency issues
"""
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def fix_problematic_migrations():
    """Fix the circular dependency between migrations"""
    print("🔧 Fixing Problematic Migrations")
    print("=" * 60)
    
    versions_dir = Path("alembic/versions")
    
    # Backup original files
    problematic_files = [
        "add_document_categorization_fields.py",
        "20250616_add_subscription_fields.py"
    ]
    
    for filename in problematic_files:
        filepath = versions_dir / filename
        if filepath.exists():
            backup_path = filepath.with_suffix('.py.bak')
            shutil.copy2(filepath, backup_path)
            print(f"✅ Backed up {filename} to {backup_path.name}")
    
    # Create fixed versions
    print("\n📝 Creating fixed migration files...")
    
    # Fixed categorization migration
    cat_migration = '''"""add document categorization fields - fixed

Revision ID: add_doc_categorization_fixed
Revises: unified_20250615
Create Date: 2024-01-18 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import ProgrammingError

# revision identifiers, used by Alembic.
revision = 'add_doc_categorization_fixed'
down_revision = 'unified_20250615'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use connection to check columns existence
    conn = op.get_bind()
    
    # Check if documents table exists
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'documents')"
    ))
    if not result.scalar():
        print("Documents table doesn't exist, skipping migration")
        return
    
    # Get existing columns
    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'documents'"
    ))
    existing_columns = {row[0] for row in result}
    
    # Add columns if they don't exist
    if 'category' not in existing_columns:
        op.add_column('documents', sa.Column('category', sa.String(50), nullable=True))
        print("✅ Added category column")
    
    if 'document_metadata' not in existing_columns:
        op.add_column('documents', sa.Column('document_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'))
        print("✅ Added document_metadata column")
    
    if 'content' not in existing_columns:
        op.add_column('documents', sa.Column('content', sa.Text(), nullable=True))
        print("✅ Added content column")
    
    if 'extracted_entities' not in existing_columns:
        op.add_column('documents', sa.Column('extracted_entities', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        print("✅ Added extracted_entities column")
    
    # Create indexes if they don't exist
    result = conn.execute(sa.text(
        "SELECT indexname FROM pg_indexes WHERE tablename = 'documents'"
    ))
    existing_indexes = {row[0] for row in result}
    
    if 'idx_documents_category' not in existing_indexes:
        try:
            op.create_index('idx_documents_category', 'documents', ['category'])
            print("✅ Created idx_documents_category index")
        except ProgrammingError:
            pass
    
    if 'idx_documents_category_tenant' not in existing_indexes:
        try:
            op.create_index('idx_documents_category_tenant', 'documents', ['category', 'tenant_id'])
            print("✅ Created idx_documents_category_tenant index")
        except ProgrammingError:
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
'''
    
    # Fixed subscription migration
    sub_migration = '''"""add subscription fields to user - fixed

Revision ID: add_sub_fields_fixed
Revises: add_doc_categorization_fixed
Create Date: 2025-06-16 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import ProgrammingError

# revision identifiers, used by Alembic.
revision = 'add_sub_fields_fixed'
down_revision = 'add_doc_categorization_fixed'
branch_labels = None
depends_on = None


def upgrade():
    """Add subscription_plan and subscription_status to users table"""
    conn = op.get_bind()
    
    # Check if users table exists
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'users')"
    ))
    if not result.scalar():
        print("Users table doesn't exist, skipping migration")
        return
    
    # Get existing columns
    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"
    ))
    existing_columns = {row[0] for row in result}
    
    # Add columns if they don't exist
    if 'subscription_plan' not in existing_columns:
        op.add_column('users', sa.Column('subscription_plan', sa.String(50), nullable=True, server_default='free'))
        print("✅ Added subscription_plan column")
    
    if 'subscription_status' not in existing_columns:
        op.add_column('users', sa.Column('subscription_status', sa.String(50), nullable=True, server_default='active'))
        print("✅ Added subscription_status column")


def downgrade():
    """Remove subscription fields from users table"""
    try:
        op.drop_column('users', 'subscription_status')
        op.drop_column('users', 'subscription_plan')
    except Exception as e:
        print(f"Could not remove subscription fields: {e}")
'''
    
    # Write fixed migrations
    fixed_cat_path = versions_dir / "add_document_categorization_fields_fixed.py"
    fixed_sub_path = versions_dir / "20250616_add_subscription_fields_fixed.py"
    
    with open(fixed_cat_path, 'w') as f:
        f.write(cat_migration)
    print(f"✅ Created {fixed_cat_path.name}")
    
    with open(fixed_sub_path, 'w') as f:
        f.write(sub_migration)
    print(f"✅ Created {fixed_sub_path.name}")
    
    # Remove original problematic files
    for filename in problematic_files:
        filepath = versions_dir / filename
        if filepath.exists():
            os.remove(filepath)
            print(f"✅ Removed original {filename}")
    
    return True


def create_recovery_sql():
    """Create SQL commands for manual recovery"""
    recovery_sql = """
-- Recovery SQL for Alembic Migration Issues
-- Run these commands if the Python scripts fail

-- 1. Terminate any blocked transactions
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE datname = 'nouxcube' 
AND state = 'idle in transaction' 
AND pid != pg_backend_pid();

-- 2. Backup current alembic version
CREATE TABLE IF NOT EXISTS alembic_version_backup AS 
SELECT * FROM alembic_version;

-- 3. Check current version
SELECT version_num FROM alembic_version;

-- 4. Reset to safe point if needed
DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('unified_20250615');

-- 5. Check if columns already exist (to avoid duplicate errors)
SELECT column_name 
FROM information_schema.columns 
WHERE table_name = 'documents' 
AND column_name IN ('category', 'document_metadata', 'content', 'extracted_entities');

SELECT column_name 
FROM information_schema.columns 
WHERE table_name = 'users' 
AND column_name IN ('subscription_plan', 'subscription_status');

-- 6. If you need to manually add the columns:
-- For documents table (only if they don't exist):
ALTER TABLE documents ADD COLUMN IF NOT EXISTS category VARCHAR(50);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS document_metadata JSONB DEFAULT '{}';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extracted_entities JSONB;

-- For users table (only if they don't exist):
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_plan VARCHAR(50) DEFAULT 'free';
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(50) DEFAULT 'active';

-- 7. Update alembic version to reflect the changes
DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('add_sub_fields_fixed');

-- 8. Verify the fix
SELECT version_num FROM alembic_version;
"""
    
    with open("recovery.sql", 'w') as f:
        f.write(recovery_sql)
    
    print("\n📄 Created recovery.sql file with manual recovery commands")


def main():
    print("🚀 Alembic Migration Recovery Tool")
    print("=" * 60)
    print(f"Timestamp: {datetime.now()}")
    print(f"Working Directory: {os.getcwd()}")
    print()
    
    # Check if we're in the right directory
    if not Path("alembic.ini").exists():
        print("❌ Error: alembic.ini not found. Please run from the backend directory.")
        sys.exit(1)
    
    # Step 1: Analyze current state
    print("\n📊 Step 1: Analyzing current migration state...")
    from scripts.alembic_utils import AlembicMigrationManager
    
    try:
        manager = AlembicMigrationManager()
        problems = manager.detect_problems()
        
        print("\nDetected problems:")
        for problem_type, issues in problems.items():
            if issues:
                print(f"  - {problem_type}: {issues}")
        
        if not any(problems.values()):
            print("  ✅ No problems detected!")
    except Exception as e:
        print(f"  ⚠️  Could not analyze migrations: {e}")
    
    # Step 2: Fix problematic migrations
    print("\n📊 Step 2: Fixing problematic migrations...")
    success = fix_problematic_migrations()
    
    if success:
        print("\n✅ Migration files fixed successfully!")
    else:
        print("\n❌ Failed to fix migration files")
        sys.exit(1)
    
    # Step 3: Create recovery SQL
    create_recovery_sql()
    
    # Step 4: Show next steps
    print("\n📌 Next Steps:")
    print("=" * 60)
    print("1. If using Docker, run:")
    print("   docker compose -f docker/docker-compose.yml exec api alembic current")
    print("   docker compose -f docker/docker-compose.yml exec api alembic upgrade head")
    print()
    print("2. If running locally, run:")
    print("   alembic current")
    print("   alembic upgrade head")
    print()
    print("3. If migrations still fail, use the recovery.sql file:")
    print("   docker compose -f docker/docker-compose.yml exec -T postgres psql -U nexus_user -d nouxcube < recovery.sql")
    print()
    print("4. To verify the fix:")
    print("   alembic current")
    print("   alembic history")
    print()
    print("✅ Recovery preparation complete!")


if __name__ == "__main__":
    main()