#!/usr/bin/env python3
"""
Initialize Apache AGE Graph for the Active Sector

Reads ACTIVE_SECTOR from environment and creates the corresponding
graph schema in Apache AGE (PostgreSQL extension).

Must be run AFTER PostgreSQL with AGE is running and BEFORE data ingestion.

Usage:
    # Uses ACTIVE_SECTOR from environment
    python scripts/init_sector_graphs.py

    # Override sector
    python scripts/init_sector_graphs.py --sector=legal

    # Dry run (print SQL without executing)
    python scripts/init_sector_graphs.py --dry-run
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg2


VALID_SECTORS = {"legal", "medical", "documental"}

# Resolve schema files relative to emma-agent-service config
SCHEMA_DIR = (
    Path(__file__).parent.parent
    / "microservices"
    / "emma-agent-service"
    / "config"
    / "graphs"
)

SECTOR_SCHEMA_FILES = {
    "legal": "legal_graph_schema.cypher",
    "medical": "medical_graph_schema.cypher",
    "documental": "documental_graph_schema.cypher",
}


def get_db_connection():
    """Create PostgreSQL connection using environment variables."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", os.getenv("POSTGRES_SERVER", "localhost")),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "nexus_db"),
        user=os.getenv("POSTGRES_USER", "nexus_user"),
        password=os.getenv("POSTGRES_PASSWORD", "nexus_password"),
    )


def ensure_age_extension(conn):
    """Ensure Apache AGE extension is loaded."""
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS age;")
        cur.execute("LOAD 'age';")
        cur.execute("SET search_path = ag_catalog, '$user', public;")
    conn.commit()


def graph_exists(conn, graph_name: str) -> bool:
    """Check if a graph already exists in AGE."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = %s",
            (graph_name,),
        )
        return cur.fetchone()[0] > 0


def execute_schema(conn, schema_path: Path, dry_run: bool = False):
    """Execute a Cypher schema file against AGE."""
    content = schema_path.read_text()

    # Extract SQL statements (skip comments and empty lines)
    statements = []
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("--"):
            # Handle multi-line statements ending with ;
            if line.endswith(";"):
                statements.append(line)

    if dry_run:
        print(f"\n📝 SQL statements from {schema_path.name}:")
        for stmt in statements:
            print(f"  {stmt}")
        return

    with conn.cursor() as cur:
        for stmt in statements:
            try:
                cur.execute(stmt)
                print(f"  ✅ {stmt[:80]}...")
            except Exception as e:
                # Ignore "already exists" errors
                if "already exists" in str(e):
                    print(f"  ⏭️  {stmt[:60]}... (already exists)")
                    conn.rollback()
                    # Re-set search path after rollback
                    cur.execute("SET search_path = ag_catalog, '$user', public;")
                else:
                    print(f"  ❌ {stmt[:60]}... ERROR: {e}")
                    conn.rollback()
                    cur.execute("SET search_path = ag_catalog, '$user', public;")

    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Initialize Apache AGE graph for active sector")
    parser.add_argument("--sector", default=None, help="Override ACTIVE_SECTOR env var")
    parser.add_argument("--dry-run", action="store_true", help="Print SQL without executing")
    args = parser.parse_args()

    sector = (args.sector or os.getenv("ACTIVE_SECTOR", "")).strip().lower()

    if not sector:
        print("❌ No sector specified. Set ACTIVE_SECTOR env var or use --sector=<name>")
        print(f"   Valid sectors: {', '.join(sorted(VALID_SECTORS))}")
        sys.exit(1)

    if sector not in VALID_SECTORS:
        print(f"❌ Invalid sector: '{sector}'")
        print(f"   Valid sectors: {', '.join(sorted(VALID_SECTORS))}")
        sys.exit(1)

    schema_file = SCHEMA_DIR / SECTOR_SCHEMA_FILES[sector]
    if not schema_file.exists():
        print(f"❌ Schema file not found: {schema_file}")
        sys.exit(1)

    graph_name = f"{sector}_graph"
    print(f"🏗️  Initializing graph '{graph_name}' for sector '{sector}'")
    print(f"📄 Schema: {schema_file}")

    if args.dry_run:
        execute_schema(None, schema_file, dry_run=True)
        print("\n✅ Dry run complete. No changes made.")
        return

    try:
        conn = get_db_connection()
        print(f"🔌 Connected to PostgreSQL")

        ensure_age_extension(conn)
        print(f"✅ Apache AGE extension loaded")

        if graph_exists(conn, graph_name):
            print(f"⚠️  Graph '{graph_name}' already exists. Skipping creation.")
            print(f"   To recreate, drop it first: SELECT drop_graph('{graph_name}', true);")
        else:
            execute_schema(conn, schema_file)
            print(f"\n✅ Graph '{graph_name}' initialized successfully")

        conn.close()

    except Exception as e:
        print(f"❌ Failed: {e}")
        sys.exit(1)

    print(f"\n📋 Next: Start data ingestion for sector '{sector}'")


if __name__ == "__main__":
    main()
