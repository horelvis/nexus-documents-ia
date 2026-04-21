#!/usr/bin/env python3
"""
Script to sync Alfresco content model from the host machine.

Run this from outside Docker to access the local network.

Usage:
    cd backend/docker
    python sync_alfresco_model.py

Requirements:
    pip install httpx asyncio psycopg2-binary
"""
import asyncio
import json
import sys
from datetime import datetime, timezone
from uuid import UUID

import httpx

# Database connection (adjust if needed)
DATABASE_URL = "postgresql://nexus_user:nexus_password@localhost:5432/nouxcube"

# Alfresco connector ID (from your database)
CONNECTOR_ID = "49526fa0-c06b-41fc-9b8a-5df87e5d6bc7"


async def get_connector_config():
    """Get connector config from database."""
    import psycopg2

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(
        "SELECT config, tenant_id FROM connectors WHERE id = %s",
        (CONNECTOR_ID,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise ValueError(f"Connector {CONNECTOR_ID} not found")

    return row[0], row[1]


async def fetch_content_model(config: dict) -> dict:
    """Fetch content model from Alfresco Public API."""
    import base64

    base_url = config["url"].rstrip("/")
    username = config["username"]
    password = config["password"]

    # Auth header
    auth_str = f"{username}:{password}"
    auth_bytes = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_bytes}",
        "Accept": "application/json",
    }

    result = {
        "types": [],
        "aspects": [],
        "properties": {},
        "association_types": {},
        "custom_namespaces": set(),
    }

    standard_prefixes = {"cm", "sys", "app", "usr", "ver", "fm", "dl", "ia", "lnk", "st", "wf", "bpm"}

    async with httpx.AsyncClient(headers=headers, timeout=120.0) as client:
        # Fetch types
        print("Fetching types from Alfresco...")
        skip = 0
        has_more = True

        while has_more:
            response = await client.get(
                f"{base_url}/alfresco/api/-default-/public/alfresco/versions/1/types",
                params={
                    "skipCount": skip,
                    "maxItems": 100,
                    "include": "properties,mandatoryAspects,associations"
                }
            )
            response.raise_for_status()
            data = response.json()

            entries = data.get("list", {}).get("entries", [])
            pagination = data.get("list", {}).get("pagination", {})

            for entry in entries:
                type_def = entry.get("entry", {})
                result["types"].append(type_def)

                # Track custom namespaces
                type_id = type_def.get("id", "")
                if ":" in type_id:
                    prefix = type_id.split(":")[0]
                    if prefix not in standard_prefixes:
                        result["custom_namespaces"].add(prefix)

                # Add properties
                for prop in type_def.get("properties", []):
                    prop_id = prop.get("id")
                    if prop_id:
                        result["properties"][prop_id] = prop

            has_more = pagination.get("hasMoreItems", False)
            skip += len(entries)
            print(f"  Types: {len(result['types'])} (has_more={has_more})")

            if not entries:
                break

        # Fetch aspects
        print("Fetching aspects from Alfresco...")
        skip = 0
        has_more = True

        while has_more:
            response = await client.get(
                f"{base_url}/alfresco/api/-default-/public/alfresco/versions/1/aspects",
                params={
                    "skipCount": skip,
                    "maxItems": 100,
                    "include": "properties,associations"
                }
            )
            response.raise_for_status()
            data = response.json()

            entries = data.get("list", {}).get("entries", [])
            pagination = data.get("list", {}).get("pagination", {})

            for entry in entries:
                aspect_def = entry.get("entry", {})
                result["aspects"].append(aspect_def)

                # Track custom namespaces
                aspect_id = aspect_def.get("id", "")
                if ":" in aspect_id:
                    prefix = aspect_id.split(":")[0]
                    if prefix not in standard_prefixes:
                        result["custom_namespaces"].add(prefix)

                # Add properties
                for prop in aspect_def.get("properties", []):
                    prop_id = prop.get("id")
                    if prop_id:
                        result["properties"][prop_id] = prop

            has_more = pagination.get("hasMoreItems", False)
            skip += len(entries)
            print(f"  Aspects: {len(result['aspects'])} (has_more={has_more})")

            if not entries:
                break

    result["custom_namespaces"] = list(result["custom_namespaces"])
    return result


async def save_content_model(tenant_id: str, content_model: dict):
    """Save content model to database."""
    import psycopg2
    import psycopg2.extras

    # Register UUID adapter
    psycopg2.extras.register_uuid()

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Convert types/aspects lists to dicts keyed by ID
    types_dict = {t["id"]: t for t in content_model.get("types", [])}
    aspects_dict = {a["id"]: a for a in content_model.get("aspects", [])}

    now = datetime.now(timezone.utc)

    # Check if exists
    cur.execute(
        "SELECT id FROM connector_content_models WHERE connector_id = %s",
        (UUID(CONNECTOR_ID),)
    )
    existing = cur.fetchone()

    if existing:
        # Update
        cur.execute("""
            UPDATE connector_content_models
            SET content_types = %s,
                aspects = %s,
                property_definitions = %s,
                association_types = %s,
                discovery_method = 'public_api',
                last_updated_at = %s
            WHERE connector_id = %s
        """, (
            json.dumps(types_dict),
            json.dumps(aspects_dict),
            json.dumps(content_model.get("properties", {})),
            json.dumps(content_model.get("association_types", {})),
            now,
            UUID(CONNECTOR_ID),
        ))
        print(f"Updated existing content model record")
    else:
        # Insert
        import uuid
        cur.execute("""
            INSERT INTO connector_content_models
            (id, connector_id, tenant_id, content_types, aspects, property_definitions,
             association_types, discovery_method, discovered_at, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'public_api', %s, %s)
        """, (
            uuid.uuid4(),
            UUID(CONNECTOR_ID),
            UUID(tenant_id),
            json.dumps(types_dict),
            json.dumps(aspects_dict),
            json.dumps(content_model.get("properties", {})),
            json.dumps(content_model.get("association_types", {})),
            now,
            now,
        ))
        print(f"Created new content model record")

    conn.commit()
    cur.close()
    conn.close()


async def main():
    print("=" * 60)
    print("Alfresco Content Model Sync")
    print("=" * 60)

    # Get connector config
    print(f"\nFetching connector config for {CONNECTOR_ID}...")
    config, tenant_id = await get_connector_config()
    print(f"  URL: {config.get('url')}")
    print(f"  User: {config.get('username')}")
    print(f"  Tenant: {tenant_id}")

    # Fetch content model
    print(f"\nConnecting to Alfresco...")
    content_model = await fetch_content_model(config)

    # Summary
    print(f"\n" + "=" * 60)
    print("Content Model Summary:")
    print(f"  Types: {len(content_model['types'])}")
    print(f"  Aspects: {len(content_model['aspects'])}")
    print(f"  Properties: {len(content_model['properties'])}")
    print(f"  Custom namespaces: {content_model['custom_namespaces']}")

    # Show some custom types/aspects
    print(f"\nCustom types/aspects found:")
    for t in content_model["types"]:
        if ":" in t.get("id", "") and t["id"].split(":")[0] not in {"cm", "sys", "app"}:
            print(f"  Type: {t['id']} - {t.get('title', '')}")
    for a in content_model["aspects"]:
        if ":" in a.get("id", "") and a["id"].split(":")[0] not in {"cm", "sys", "app"}:
            print(f"  Aspect: {a['id']} - {a.get('title', '')}")

    # Save to database
    print(f"\nSaving to database...")
    await save_content_model(tenant_id, content_model)

    print(f"\n" + "=" * 60)
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
