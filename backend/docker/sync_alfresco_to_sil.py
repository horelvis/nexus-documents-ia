#!/usr/bin/env python3
"""
Script to sync Alfresco folders to the Structural Intelligence Layer (SIL).

This script:
1. Connects to Alfresco via the configured connector
2. Fetches all folders with their rich metadata (exp:*, pmreg:*, etc.)
3. Indexes them as structural entities in the SIL graph
4. Creates PARENT_OF relationships between folders and documents

In Alfresco, both folders and documents are content nodes. This script
enables the SIL to understand the folder hierarchy and use folder metadata
(like expediente classifications, registry numbers) for structural queries.

Usage:
    python sync_alfresco_to_sil.py [--connector-id UUID] [--limit N] [--dry-run]

Example:
    # Sync all folders from default connector
    python sync_alfresco_to_sil.py

    # Sync from specific connector
    python sync_alfresco_to_sil.py --connector-id 00000000-0000-0000-0000-000000000001

    # Dry run - show what would be synced
    python sync_alfresco_to_sil.py --dry-run
"""

import asyncio
import argparse
import logging
import sys
import os
from typing import Optional, Dict, Any, List
from uuid import UUID

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql://nexus_user:nexus_password@localhost:5432/nexus_db"
    )


def get_knowledge_tree_service_url() -> str:
    """Get Knowledge Tree service URL (fallback to Weaviate if not set)."""
    return os.getenv(
        "KNOWLEDGE_TREE_SERVICE_URL",
        os.getenv("WEAVIATE_SERVICE_URL", "http://localhost:8011"),
    )


def get_api_key() -> str:
    """Get microservices API key."""
    return os.getenv("MICROSERVICES_API_KEY", "test-api-key")


async def get_connector_folders(
    connector: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Fetch all folders from an Alfresco connector.

    Args:
        connector: Connector record with config

    Returns:
        List of folder dicts with metadata
    """
    import base64

    config = connector["config"]
    base_url = config.get("url", "").rstrip("/")
    username = config.get("username", "")
    password = config.get("password", "")

    auth_str = f"{username}:{password}"
    auth_bytes = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_bytes}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    all_folders = []

    async def fetch_folders_recursive(node_id: str, depth: int = 0, max_depth: int = 10):
        """Recursively fetch folders."""
        if depth >= max_depth:
            return

        try:
            async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
                # Get children that are folders
                response = await client.get(
                    f"{base_url}/alfresco/api/-default-/public/alfresco/versions/1/nodes/{node_id}/children",
                    params={
                        "include": "properties,aspectNames,path",
                        "where": "(isFolder=true)",
                        "maxItems": 100,
                    }
                )
                response.raise_for_status()
                data = response.json()

                entries = data.get("list", {}).get("entries", [])

                for entry in entries:
                    folder = entry.get("entry", {})
                    folder_id = folder.get("id")
                    folder_name = folder.get("name", "")

                    # Skip system folders
                    if folder_name in {"Data Dictionary", "User Homes", "Shared"}:
                        continue

                    # Parse folder with all properties
                    parsed = parse_folder_entry(folder)
                    parsed["depth"] = depth
                    parsed["connector_id"] = str(connector["id"])
                    parsed["tenant_id"] = str(connector["tenant_id"])

                    all_folders.append(parsed)

                    # Recurse into subfolders
                    await fetch_folders_recursive(folder_id, depth + 1, max_depth)

        except Exception as e:
            logger.warning(f"Error fetching folders from {node_id}: {e}")

    # Start from root
    await fetch_folders_recursive("-root-")

    return all_folders


def parse_folder_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse a folder entry with all properties.

    Args:
        entry: Folder entry from Alfresco API

    Returns:
        Parsed folder dict with all custom properties
    """
    properties = entry.get("properties", {})
    path_info = entry.get("path", {})

    # Build full path
    path_elements = path_info.get("elements", [])
    path_parts = [elem.get("name", "") for elem in path_elements]
    full_path = "/" + "/".join(path_parts) if path_parts else "/"

    # Extract ALL custom properties (exp:*, pmreg:*, etc.)
    custom_properties = {}
    standard_props = {"cm:name", "cm:title", "cm:description", "cm:created", "cm:modified", "cm:creator", "cm:modifier"}

    for prop_name, prop_value in properties.items():
        if prop_name in standard_props or prop_name.startswith("sys:"):
            continue
        if prop_value is not None:
            custom_properties[prop_name] = prop_value

    return {
        "id": entry.get("id"),
        "name": entry.get("name", ""),
        "path": full_path,
        "nodeType": entry.get("nodeType"),
        "aspectNames": entry.get("aspectNames", []),
        "title": properties.get("cm:title"),
        "description": properties.get("cm:description"),
        "created": properties.get("cm:created"),
        "modified": properties.get("cm:modified"),
        "creator": properties.get("cm:creator"),
        "customProperties": custom_properties,
        "parentId": entry.get("parentId"),
        "isFolder": True,
    }


async def index_folder_to_sil(
    client: httpx.AsyncClient,
    folder: Dict[str, Any],
    api_key: str,
) -> Dict[str, Any]:
    """
    Index a folder to the SIL graph.

    Args:
        client: HTTP client
        folder: Folder data
        api_key: API key for authentication

    Returns:
        Response from SIL service
    """
    knowledge_tree_url = get_knowledge_tree_service_url()

    # Build connector_metadata that looks like document metadata
    # but indicates this is a folder
    connector_metadata = {
        "alfresco_node_type": folder["nodeType"],
        "alfresco_aspects": folder["aspectNames"],
        "alfresco_parent_id": folder["parentId"],
        "alfresco_creator": folder.get("creator"),
        "alfresco_properties": folder["customProperties"],
        "is_folder": True,
        "folder_name": folder["name"],
    }

    payload = {
        "document_id": folder["id"],  # Use Alfresco node ID
        "tenant_id": folder["tenant_id"],
        "file_path": folder["path"] + "/" + folder["name"],
        "connector_metadata": connector_metadata,
        "learned_context": {
            "is_folder": True,
            "folder_depth": folder.get("depth", 0),
        },
        "connector_id": folder["connector_id"],
    }

    try:
        response = await client.post(
            f"{knowledge_tree_url}/tree/index",
            json=payload,
            headers={"X-API-Key": api_key},
            timeout=30.0,
        )

        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:200]}"
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def main(
    connector_id: Optional[str] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
):
    """Main function to sync Alfresco folders to SIL."""

    # Connect to database
    engine = create_engine(get_database_url())
    Session = sessionmaker(bind=engine)
    session = Session()

    api_key = get_api_key()
    knowledge_tree_url = get_knowledge_tree_service_url()

    logger.info(f"Knowledge Tree Service URL: {knowledge_tree_url}")
    logger.info(f"Dry run: {dry_run}")

    # Get connector(s)
    query = """
        SELECT id, tenant_id, connector_type, config, is_active
        FROM connectors
        WHERE connector_type = 'alfresco'
        AND is_active = true
    """

    if connector_id:
        query += f" AND id = '{connector_id}'"

    result = session.execute(text(query))
    connectors = [dict(row._mapping) for row in result]

    if not connectors:
        logger.warning("No active Alfresco connectors found")
        return

    logger.info(f"Found {len(connectors)} Alfresco connector(s)")

    # Process each connector
    total_folders = 0
    total_success = 0
    total_errors = 0

    for connector in connectors:
        logger.info(f"\n=== Processing connector: {connector['id']} ===")

        # Fetch folders from Alfresco
        try:
            folders = await get_connector_folders(connector)
            logger.info(f"Found {len(folders)} folders")

            if limit:
                folders = folders[:limit]
                logger.info(f"Limited to {len(folders)} folders")

            total_folders += len(folders)

            if dry_run:
                logger.info("Dry run - folders that would be indexed:")
                for folder in folders[:10]:
                    props = folder.get("customProperties", {})
                    logger.info(f"  - {folder['path']}/{folder['name']}")
                    logger.info(f"    Type: {folder['nodeType']}")
                    if props:
                        logger.info(f"    Properties: {list(props.keys())}")
                continue

            # Index folders to SIL
            async with httpx.AsyncClient() as client:
                for i, folder in enumerate(folders):
                    logger.info(
                        f"[{i+1}/{len(folders)}] Indexing folder: {folder['path']}/{folder['name']}"
                    )

                    result = await index_folder_to_sil(client, folder, api_key)

                    if result["success"]:
                        total_success += 1
                        data = result["data"]
                        logger.info(
                            f"  ✓ Type: {data.get('semantic_type', 'folder')}, "
                            f"Graph: {data.get('indexed_to_graph')}"
                        )
                    else:
                        total_errors += 1
                        logger.error(f"  ✗ Error: {result['error']}")

        except Exception as e:
            logger.error(f"Error processing connector {connector['id']}: {e}")
            continue

    session.close()

    logger.info(f"\n=== Summary ===")
    logger.info(f"Total folders found: {total_folders}")
    if not dry_run:
        logger.info(f"Successfully indexed: {total_success}")
        logger.info(f"Errors: {total_errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sync Alfresco folders to Structural Intelligence Layer"
    )
    parser.add_argument(
        "--connector-id",
        type=str,
        help="Specific connector ID to sync",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of folders to process",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without actually syncing",
    )

    args = parser.parse_args()

    asyncio.run(main(
        connector_id=args.connector_id,
        limit=args.limit,
        dry_run=args.dry_run,
    ))
