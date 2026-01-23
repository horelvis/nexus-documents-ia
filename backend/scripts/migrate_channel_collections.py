#!/usr/bin/env python3
"""
Migration Script: Rename Channel Collections to New Format.

This script migrates Weaviate collections from the legacy format:
    Nouxcube_{tenant_id}__documents

To the new channel-specific format:
    nexus_{tenant_id}_channel_{channel_id}

The new format allows:
- Separate collections per information channel (Gmail, Drive, Slack, etc.)
- Better organization as more channel types are added
- Efficient channel-specific queries

Usage:
    # Dry run (shows what would be migrated)
    python migrate_channel_collections.py --dry-run

    # Execute migration
    python migrate_channel_collections.py

    # Migrate specific tenant only
    python migrate_channel_collections.py --tenant-id 1a94d369-8426-4d2b-afec-8971073fce1e

    # Keep old collection (don't delete after migration)
    python migrate_channel_collections.py --keep-old
"""

import argparse
import asyncio
import logging
import sys
from typing import Dict, List, Optional, Set
from dataclasses import dataclass

import weaviate
from weaviate.classes.config import Configure, Property, DataType

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Weaviate configuration
WEAVIATE_URL = "http://weaviate:8080"  # Inside Docker network
WEAVIATE_LOCAL_URL = "http://localhost:8080"  # Outside Docker


@dataclass
class MigrationInfo:
    """Information about a collection to migrate."""
    old_name: str
    new_name: str
    tenant_id: str
    channel_id: str
    source_type: str
    document_count: int


def get_channel_collection_name(tenant_id: str, channel_id: str) -> str:
    """Generate channel-specific collection name for Weaviate."""
    tenant_normalized = tenant_id.lower().replace("-", "_")
    channel_normalized = channel_id.lower().replace("-", "_")
    return f"nexus_{tenant_normalized}_channel_{channel_normalized}"


def is_legacy_channel_collection(name: str) -> bool:
    """
    Check if a collection uses the legacy naming format.

    Legacy format: Nouxcube_{tenant_uuid}__documents (note double underscore)
    """
    import re
    # Pattern: Nouxcube_{uuid}__documents (case-insensitive, double underscore)
    pattern = r"^nexus_[a-f0-9_]+__documents$"
    return bool(re.match(pattern, name.lower()))


async def discover_migrations(client: weaviate.WeaviateClient, tenant_filter: Optional[str] = None) -> List[MigrationInfo]:
    """
    Discover all collections that need migration.

    Returns:
        List of MigrationInfo objects describing what needs to be migrated
    """
    migrations = []

    # Get all collections
    collections = client.collections.list_all()
    logger.info(f"Found {len(collections)} total collections")

    for coll_name in collections:
        if not is_legacy_channel_collection(coll_name):
            continue

        logger.info(f"Analyzing legacy collection: {coll_name}")

        try:
            collection = client.collections.get(coll_name)

            # Query to find unique channel_ids in this collection
            channel_ids: Dict[str, Dict] = {}  # channel_id -> {source_type, count}

            # Fetch objects to analyze
            result = collection.query.fetch_objects(
                limit=1000,
                return_properties=["channel_id", "source_type", "tenant_id"]
            )

            for obj in result.objects:
                props = obj.properties
                channel_id = props.get("channel_id")
                source_type = props.get("source_type", "unknown")
                tenant_id = props.get("tenant_id")

                if channel_id:
                    if channel_id not in channel_ids:
                        channel_ids[channel_id] = {
                            "source_type": source_type,
                            "tenant_id": tenant_id,
                            "count": 0
                        }
                    channel_ids[channel_id]["count"] += 1

            if not channel_ids:
                logger.warning(f"No channel_id found in collection {coll_name}, skipping")
                continue

            # Create migration info for each channel found
            for channel_id, info in channel_ids.items():
                tenant_id = info["tenant_id"]

                # Apply tenant filter if specified
                if tenant_filter and tenant_id != tenant_filter:
                    continue

                new_name = get_channel_collection_name(tenant_id, channel_id)

                migrations.append(MigrationInfo(
                    old_name=coll_name,
                    new_name=new_name,
                    tenant_id=tenant_id,
                    channel_id=channel_id,
                    source_type=info["source_type"],
                    document_count=info["count"]
                ))

        except Exception as e:
            logger.error(f"Error analyzing collection {coll_name}: {e}")

    return migrations


async def create_channel_collection(client: weaviate.WeaviateClient, name: str, source_collection: str) -> bool:
    """
    Create a new channel collection with the same schema as the source.
    """
    try:
        # Get source collection schema
        source = client.collections.get(source_collection)
        config = source.config.get()

        # Create new collection with same properties
        properties = []
        for prop in config.properties:
            properties.append(Property(
                name=prop.name,
                data_type=prop.data_type,
                description=prop.description,
                index_filterable=prop.index_filterable,
                index_searchable=prop.index_searchable
            ))

        # Create the new collection
        client.collections.create(
            name=name,
            vectorizer_config=Configure.Vectorizer.none(),  # We use precomputed vectors
            properties=properties
        )

        logger.info(f"Created collection: {name}")
        return True

    except Exception as e:
        if "already exists" in str(e).lower():
            logger.info(f"Collection {name} already exists")
            return True
        logger.error(f"Error creating collection {name}: {e}")
        return False


async def migrate_documents(
    client: weaviate.WeaviateClient,
    migration: MigrationInfo,
    dry_run: bool = False
) -> int:
    """
    Migrate documents from old collection to new collection.

    Returns:
        Number of documents migrated
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would migrate {migration.document_count} documents")
        logger.info(f"  From: {migration.old_name}")
        logger.info(f"  To:   {migration.new_name}")
        return migration.document_count

    try:
        source = client.collections.get(migration.old_name)
        target = client.collections.get(migration.new_name)

        migrated = 0
        batch_size = 100

        # Fetch documents for this specific channel
        # Use cursor-based pagination for large collections
        cursor = None

        while True:
            if cursor:
                result = source.query.fetch_objects(
                    limit=batch_size,
                    after=cursor,
                    include_vector=True,
                    return_properties=None  # All properties
                )
            else:
                result = source.query.fetch_objects(
                    limit=batch_size,
                    include_vector=True,
                    return_properties=None  # All properties
                )

            if not result.objects:
                break

            # Filter and migrate documents for this channel
            objects_to_insert = []
            for obj in result.objects:
                if obj.properties.get("channel_id") == migration.channel_id:
                    # Handle vector format - can be dict or list
                    vector = None
                    if obj.vector:
                        if isinstance(obj.vector, dict):
                            vector = obj.vector.get("default")
                        elif isinstance(obj.vector, list):
                            vector = obj.vector
                    objects_to_insert.append({
                        "properties": obj.properties,
                        "vector": vector,
                        "uuid": obj.uuid
                    })

            # Insert documents one by one (more reliable than batch for vectors)
            for obj_data in objects_to_insert:
                try:
                    # Skip documents with empty or missing vectors
                    vector = obj_data["vector"]
                    if vector is None or (isinstance(vector, list) and len(vector) == 0):
                        logger.warning(f"Skipping document {obj_data['uuid']} - no vector")
                        continue

                    target.data.insert(
                        properties=obj_data["properties"],
                        vector=vector,
                        uuid=obj_data["uuid"]
                    )
                    migrated += 1
                except Exception as insert_error:
                    logger.warning(f"Error inserting document {obj_data['uuid']}: {insert_error}")

            # Update cursor for next batch
            if result.objects:
                cursor = result.objects[-1].uuid
            else:
                break

            logger.info(f"Migrated {migrated} documents so far...")

        logger.info(f"Migration complete: {migrated} documents migrated")
        return migrated

    except Exception as e:
        logger.error(f"Error migrating documents: {e}")
        return 0


async def delete_legacy_collection(client: weaviate.WeaviateClient, name: str, dry_run: bool = False) -> bool:
    """Delete a legacy collection after migration."""
    if dry_run:
        logger.info(f"[DRY RUN] Would delete collection: {name}")
        return True

    try:
        client.collections.delete(name)
        logger.info(f"Deleted legacy collection: {name}")
        return True
    except Exception as e:
        logger.error(f"Error deleting collection {name}: {e}")
        return False


async def run_migration(
    tenant_filter: Optional[str] = None,
    dry_run: bool = False,
    keep_old: bool = False
):
    """Run the complete migration process."""

    # Try to connect to Weaviate
    try:
        client = weaviate.connect_to_local(
            host="localhost",
            port=8080
        )
        logger.info("Connected to Weaviate (localhost)")
    except Exception:
        try:
            client = weaviate.connect_to_local(
                host="weaviate",
                port=8080
            )
            logger.info("Connected to Weaviate (Docker network)")
        except Exception as e:
            logger.error(f"Failed to connect to Weaviate: {e}")
            return

    try:
        # Discover what needs to be migrated
        logger.info("=" * 60)
        logger.info("PHASE 1: Discovery")
        logger.info("=" * 60)

        migrations = await discover_migrations(client, tenant_filter)

        if not migrations:
            logger.info("No collections found that need migration")
            return

        logger.info(f"Found {len(migrations)} channel(s) to migrate:")
        for m in migrations:
            logger.info(f"  - {m.old_name} -> {m.new_name}")
            logger.info(f"    Channel: {m.channel_id} ({m.source_type})")
            logger.info(f"    Documents: {m.document_count}")

        # Create new collections
        logger.info("")
        logger.info("=" * 60)
        logger.info("PHASE 2: Create New Collections")
        logger.info("=" * 60)

        created: Set[str] = set()
        for m in migrations:
            if m.new_name not in created:
                if dry_run:
                    logger.info(f"[DRY RUN] Would create collection: {m.new_name}")
                else:
                    await create_channel_collection(client, m.new_name, m.old_name)
                created.add(m.new_name)

        # Migrate documents
        logger.info("")
        logger.info("=" * 60)
        logger.info("PHASE 3: Migrate Documents")
        logger.info("=" * 60)

        total_migrated = 0
        for m in migrations:
            logger.info(f"Migrating channel {m.channel_id}...")
            count = await migrate_documents(client, m, dry_run)
            total_migrated += count

        logger.info(f"Total documents migrated: {total_migrated}")

        # Cleanup old collections
        if not keep_old:
            logger.info("")
            logger.info("=" * 60)
            logger.info("PHASE 4: Cleanup Legacy Collections")
            logger.info("=" * 60)

            deleted: Set[str] = set()
            for m in migrations:
                if m.old_name not in deleted:
                    await delete_legacy_collection(client, m.old_name, dry_run)
                    deleted.add(m.old_name)
        else:
            logger.info("Keeping old collections as requested (--keep-old)")

        logger.info("")
        logger.info("=" * 60)
        logger.info("Migration Complete!")
        logger.info("=" * 60)

    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Weaviate channel collections to new naming format"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes"
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        help="Only migrate collections for this specific tenant"
    )
    parser.add_argument(
        "--keep-old",
        action="store_true",
        help="Keep legacy collections after migration (don't delete)"
    )

    args = parser.parse_args()

    if args.dry_run:
        logger.info("=" * 60)
        logger.info("DRY RUN MODE - No changes will be made")
        logger.info("=" * 60)

    asyncio.run(run_migration(
        tenant_filter=args.tenant_id,
        dry_run=args.dry_run,
        keep_old=args.keep_old
    ))


if __name__ == "__main__":
    main()
