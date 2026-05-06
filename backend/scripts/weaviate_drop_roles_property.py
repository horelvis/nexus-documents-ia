"""
weaviate_drop_roles_property.py — Blue/green Weaviate collection migration.

Removes the `roles` property from every Weaviate collection via a
blue/green copy strategy:

  1. For each collection <Col>:
     a. Create <Col>_v2 with the same schema minus the `roles` property.
     b. Copy all objects (with their vectors) from <Col> to <Col>_v2.
     c. Delete <Col>.
     d. Rename <Col>_v2 → <Col> (copy again, delete _v2).

IMPORTANT: Weaviate v1 has no native rename operation. Step d performs
another copy+delete, doubling the window but keeping it atomic per
collection. All vectors are preserved — no re-embedding required.

Operational window: bounded by object copy time (not embedding time).
Idempotent: skips collections that do not exist or already lack `roles`.

Usage:
  python weaviate_drop_roles_property.py [--dry-run] [--url http://localhost:8080]

Requires:
  pip install weaviate-client>=4.0
"""

import argparse
import logging
import sys
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

COLLECTIONS = [
    "Nouxcube_documents",
    "Nouxcube_documents_summaries",
    "Nouxcube_knowledge",
    "Nouxcube_visual",
    "TrustGraphEntities",
    "OntologyTerms",
]


def _schema_without_roles(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of the collection schema with the `roles` property removed."""
    new_schema = {k: v for k, v in schema.items() if k not in ("class",)}
    props = new_schema.get("properties", [])
    new_schema["properties"] = [p for p in props if p.get("name") != "roles"]
    return new_schema


def _copy_objects(
    client,
    src_name: str,
    dst_name: str,
    dry_run: bool,
) -> int:
    """Copy all objects from src to dst, skipping the `roles` property.

    Returns the number of objects copied.
    """
    copied = 0
    cursor = None

    while True:
        # Fetch a page of objects with vectors
        query = (
            client.collections.get(src_name)
            .query
            .fetch_objects(
                include_vector=True,
                limit=100,
                after=cursor,
            )
        )
        objects = query.objects
        if not objects:
            break

        for obj in objects:
            props = {k: v for k, v in (obj.properties or {}).items() if k != "roles"}
            if not dry_run:
                client.collections.get(dst_name).data.insert(
                    properties=props,
                    uuid=obj.uuid,
                    vector=obj.vector,
                )
            copied += 1

        if len(objects) < 100:
            break
        cursor = objects[-1].uuid

    return copied


def migrate_collection(client, name: str, dry_run: bool) -> None:
    """Perform blue/green migration for a single collection."""
    # Check if collection exists
    try:
        existing = client.collections.get(name)
        schema = client.collections.export_config(name)
    except Exception as exc:
        logger.warning("Collection %r not found or inaccessible: %s — skipping", name, exc)
        return

    # Check if roles property exists
    props = schema.get("properties", []) if isinstance(schema, dict) else []
    prop_names = [p.get("name") for p in props]
    if "roles" not in prop_names:
        logger.info("Collection %r has no `roles` property — nothing to do", name)
        return

    v2_name = f"{name}_v2"
    logger.info("Migrating %r → %r (dry_run=%s)", name, v2_name, dry_run)

    # Step 1: Create _v2 without roles
    new_schema = _schema_without_roles(schema if isinstance(schema, dict) else {})
    if not dry_run:
        try:
            client.collections.delete(v2_name)
        except Exception:
            pass  # doesn't exist yet

        client.collections.create_from_dict({"class": v2_name, **new_schema})
        logger.info("Created %r", v2_name)
    else:
        logger.info("[dry-run] Would create %r without roles", v2_name)

    # Step 2: Copy objects → _v2
    n = _copy_objects(client, name, v2_name, dry_run)
    logger.info("Copied %d objects from %r → %r", n, name, v2_name)

    # Step 3: Delete original
    if not dry_run:
        client.collections.delete(name)
        logger.info("Deleted %r", name)
    else:
        logger.info("[dry-run] Would delete %r", name)

    # Step 4: Recreate as canonical name (copy _v2 → original, then delete _v2)
    if not dry_run:
        client.collections.create_from_dict({"class": name, **new_schema})
        _copy_objects(client, v2_name, name, dry_run)
        client.collections.delete(v2_name)
        logger.info("Renamed %r → %r, deleted %r", v2_name, name, v2_name)
    else:
        logger.info("[dry-run] Would rename %r → %r", v2_name, name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Drop roles property from Weaviate collections")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying Weaviate")
    parser.add_argument("--url", default="http://localhost:8080", help="Weaviate URL")
    args = parser.parse_args()

    try:
        import weaviate
    except ImportError:
        logger.error("weaviate-client not installed. Run: pip install weaviate-client>=4.0")
        sys.exit(1)

    logger.info("Connecting to Weaviate at %s", args.url)
    client = weaviate.connect_to_local(
        host=args.url.replace("http://", "").replace("https://", "").split(":")[0],
        port=int(args.url.rsplit(":", 1)[-1]) if ":" in args.url.rsplit("/", 1)[-1] else 8080,
    )

    try:
        for col in COLLECTIONS:
            migrate_collection(client, col, dry_run=args.dry_run)

        logger.info("Migration complete (dry_run=%s)", args.dry_run)
    finally:
        client.close()


if __name__ == "__main__":
    main()
