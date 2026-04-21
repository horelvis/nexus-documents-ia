#!/usr/bin/env python3
"""
Migrate to Single Tenant Mode

This script consolidates all existing tenant data into the default single tenant.
Use this when transitioning from multi-tenant to single-tenant mode for on-premise.

WARNING: This script modifies data. Make a backup before running!

Usage:
    # Dry run (preview changes)
    python scripts/migrate_to_single_tenant.py --dry-run

    # Execute migration
    python scripts/migrate_to_single_tenant.py --execute

    # Clean up old empty tenants after migration
    python scripts/migrate_to_single_tenant.py --cleanup
"""

import argparse
import os
import sys
from uuid import UUID

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://nexus_user:nexus_password@localhost:5432/nouxcube")
DEFAULT_TENANT_ID = UUID(os.getenv("DEFAULT_TENANT_ID", "00000000-0000-0000-0000-000000000001"))
DEFAULT_TENANT_NAME = os.getenv("DEFAULT_TENANT_NAME", "NouxCubeIA Organization")
DEFAULT_TENANT_SLUG = os.getenv("DEFAULT_TENANT_SLUG", "nouxcube")

# Tables with tenant_id column that need migration
TENANT_TABLES = [
    "users",
    "documents",
    "folders",
    "roles",
    "teams",
    "team_members",
    "document_shares",
    "document_views",
    "document_tags",
    "document_analyses",
    "signatures",
    "signature_requests",
    "signature_providers",
    "alfresco_connectors",
    "channels",
    "channel_documents",
    "agent_conversations",
    "agent_messages",
    "user_interaction_history",
    "knowledge_entities",
    "entity_relationships",
    "document_classifications",
    "workflows",
    "workflow_instances",
    "workflow_tasks",
]


def get_engine():
    """Create database engine."""
    return create_engine(DATABASE_URL)


def ensure_default_tenant(session) -> bool:
    """Ensure the default tenant exists."""
    result = session.execute(
        text("SELECT id, name FROM tenants WHERE id = :tenant_id"),
        {"tenant_id": str(DEFAULT_TENANT_ID)}
    ).fetchone()

    if result:
        print(f"✓ Default tenant exists: {result[1]} ({result[0]})")
        return True

    # Create default tenant with all required fields
    bucket_name = f"nouxcube-{str(DEFAULT_TENANT_ID).replace('-', '')[:12]}"
    session.execute(
        text("""
            INSERT INTO tenants (
                id, name, slug, bucket_name, is_active, settings,
                auto_classification_enabled, auto_classification_k,
                auto_classification_min_confidence, site_enabled,
                created_at, updated_at
            )
            VALUES (
                :id, :name, :slug, :bucket_name, true, :settings,
                true, 7, 0.6, false, NOW(), NOW()
            )
        """),
        {
            "id": str(DEFAULT_TENANT_ID),
            "name": DEFAULT_TENANT_NAME,
            "slug": DEFAULT_TENANT_SLUG,
            "bucket_name": bucket_name,
            "settings": '{"deployment_mode": "single_tenant", "migrated_from_multi_tenant": true}'
        }
    )
    print(f"✓ Created default tenant: {DEFAULT_TENANT_NAME} ({DEFAULT_TENANT_ID})")
    print(f"  Bucket: {bucket_name}")
    return True


def get_tenants_to_migrate(session) -> list:
    """Get list of tenants to migrate (excluding default)."""
    result = session.execute(
        text("""
            SELECT id, name,
                   (SELECT COUNT(*) FROM users WHERE tenant_id = tenants.id) as user_count,
                   (SELECT COUNT(*) FROM documents WHERE tenant_id = tenants.id) as doc_count
            FROM tenants
            WHERE id != :default_id
            ORDER BY name
        """),
        {"default_id": str(DEFAULT_TENANT_ID)}
    ).fetchall()

    return [
        {"id": row[0], "name": row[1], "users": row[2], "docs": row[3]}
        for row in result
    ]


def migrate_table(session, table_name: str, dry_run: bool = True) -> int:
    """Migrate a single table to the default tenant."""
    try:
        # Check if table exists and has tenant_id
        check = session.execute(
            text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = :table AND column_name = 'tenant_id'
            """),
            {"table": table_name}
        ).fetchone()

        if not check:
            return 0

        # Count records to migrate
        count_result = session.execute(
            text(f"SELECT COUNT(*) FROM {table_name} WHERE tenant_id != :default_id"),
            {"default_id": str(DEFAULT_TENANT_ID)}
        ).fetchone()
        count = count_result[0] if count_result else 0

        if count == 0:
            return 0

        if dry_run:
            print(f"  Would migrate {count} records in {table_name}")
        else:
            session.execute(
                text(f"UPDATE {table_name} SET tenant_id = :default_id WHERE tenant_id != :default_id"),
                {"default_id": str(DEFAULT_TENANT_ID)}
            )
            print(f"  ✓ Migrated {count} records in {table_name}")

        return count

    except Exception as e:
        print(f"  ✗ Error with {table_name}: {e}")
        return 0


def cleanup_empty_tenants(session, dry_run: bool = True) -> int:
    """Remove tenants with no data (except default)."""
    # Find empty tenants
    result = session.execute(
        text("""
            SELECT t.id, t.name
            FROM tenants t
            WHERE t.id != :default_id
            AND NOT EXISTS (SELECT 1 FROM users WHERE tenant_id = t.id)
            AND NOT EXISTS (SELECT 1 FROM documents WHERE tenant_id = t.id)
        """),
        {"default_id": str(DEFAULT_TENANT_ID)}
    ).fetchall()

    if not result:
        print("No empty tenants to clean up")
        return 0

    for row in result:
        if dry_run:
            print(f"  Would delete tenant: {row[1]} ({row[0]})")
        else:
            session.execute(
                text("DELETE FROM tenants WHERE id = :tenant_id"),
                {"tenant_id": str(row[0])}
            )
            print(f"  ✓ Deleted tenant: {row[1]} ({row[0]})")

    return len(result)


def main():
    parser = argparse.ArgumentParser(description="Migrate to single-tenant mode")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without executing")
    parser.add_argument("--execute", action="store_true", help="Execute the migration")
    parser.add_argument("--cleanup", action="store_true", help="Remove empty tenants after migration")
    args = parser.parse_args()

    if not args.dry_run and not args.execute and not args.cleanup:
        parser.print_help()
        print("\nPlease specify --dry-run, --execute, or --cleanup")
        sys.exit(1)

    engine = get_engine()
    Session = sessionmaker(bind=engine)

    print("=" * 60)
    print("SINGLE TENANT MIGRATION")
    print("=" * 60)
    print(f"\nTarget tenant: {DEFAULT_TENANT_NAME}")
    print(f"Tenant ID: {DEFAULT_TENANT_ID}")
    print(f"Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")

    with Session() as session:
        # Ensure default tenant exists
        print("\n1. Checking default tenant...")
        ensure_default_tenant(session)

        # Show tenants to migrate
        print("\n2. Tenants to migrate:")
        tenants = get_tenants_to_migrate(session)
        if not tenants:
            print("   No other tenants found")
        else:
            for t in tenants:
                print(f"   - {t['name']}: {t['users']} users, {t['docs']} documents")

        # Migrate tables
        if args.dry_run or args.execute:
            dry_run = args.dry_run
            print(f"\n3. {'[DRY RUN] ' if dry_run else ''}Migrating tables...")
            total_migrated = 0

            for table in TENANT_TABLES:
                migrated = migrate_table(session, table, dry_run)
                total_migrated += migrated

            print(f"\n   Total records {'to migrate' if dry_run else 'migrated'}: {total_migrated}")

            if not dry_run:
                session.commit()
                print("\n   ✓ Migration committed")

        # Cleanup
        if args.cleanup:
            dry_run = args.dry_run
            print(f"\n4. {'[DRY RUN] ' if dry_run else ''}Cleaning up empty tenants...")
            cleaned = cleanup_empty_tenants(session, dry_run)

            if not dry_run and cleaned > 0:
                session.commit()
                print(f"\n   ✓ Cleaned up {cleaned} tenants")

    print("\n" + "=" * 60)
    if args.dry_run:
        print("DRY RUN COMPLETE - No changes made")
        print("Run with --execute to apply changes")
    else:
        print("MIGRATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
