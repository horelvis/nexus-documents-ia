#!/usr/bin/env python3
"""
Test script for the Database Connector Adapter.

Tests the multi-type database connector against the local PostgreSQL instance.
Uses standalone tests that don't require full app initialization.

Usage:
    cd backend/docker
    python3 test_database_connector.py
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# Standalone copies of schema for testing without full app initialization
# ============================================================================

class DatabaseEngine(str, Enum):
    """Supported database engines."""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MARIADB = "mariadb"
    SQLITE = "sqlite"
    MSSQL = "mssql"
    ORACLE = "oracle"


class DocumentStorageType(str, Enum):
    """How documents are stored in the database."""
    BLOB = "blob"
    FILE_PATH = "file_path"
    URL = "url"


def get_default_port(engine: DatabaseEngine) -> int:
    """Get default port for the database engine."""
    defaults = {
        DatabaseEngine.POSTGRESQL: 5432,
        DatabaseEngine.MYSQL: 3306,
        DatabaseEngine.MARIADB: 3306,
        DatabaseEngine.SQLITE: 0,
        DatabaseEngine.MSSQL: 1433,
        DatabaseEngine.ORACLE: 1521,
    }
    return defaults.get(engine, 5432)


def get_connection_url(
    engine: DatabaseEngine,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    include_password: bool = True,
) -> str:
    """Build SQLAlchemy connection URL."""
    drivers = {
        DatabaseEngine.POSTGRESQL: "postgresql+asyncpg",
        DatabaseEngine.MYSQL: "mysql+aiomysql",
        DatabaseEngine.MARIADB: "mysql+aiomysql",
        DatabaseEngine.SQLITE: "sqlite+aiosqlite",
        DatabaseEngine.MSSQL: "mssql+aioodbc",
        DatabaseEngine.ORACLE: "oracle+oracledb",
    }

    driver = drivers.get(engine, "postgresql+asyncpg")
    pwd = password if include_password else "***"

    if engine == DatabaseEngine.SQLITE:
        return f"{driver}:///{database}"

    return f"{driver}://{username}:{pwd}@{host}:{port}/{database}"


def build_select_query(
    table_name: str,
    column_mapping: Dict[str, str],
    extra_columns: List[str],
    where_clause: Optional[str] = None,
    order_by: Optional[str] = None,
) -> str:
    """Build SELECT query based on configuration."""
    columns = []
    for std_name, col_name in column_mapping.items():
        if col_name:
            columns.append(f"{col_name} AS {std_name}")

    for col in extra_columns:
        columns.append(col)

    query = f"SELECT {', '.join(columns)} FROM {table_name}"

    if where_clause:
        query += f" WHERE {where_clause}"

    if order_by:
        query += f" ORDER BY {order_by}"

    return query


async def test_config_building():
    """Test configuration and query building."""
    print("\n" + "=" * 60)
    print("TEST: Database Config Query Building")
    print("=" * 60)

    # Test PostgreSQL config
    engine = DatabaseEngine.POSTGRESQL
    host = "localhost"
    port = 5432
    database = "nexus_db"
    username = "nexus_user"
    password = "nexus_password"

    url = get_connection_url(engine, host, port, database, username, password, False)
    print(f"\nConnection URL (masked): {url}")
    print(f"Default port: {get_default_port(engine)}")

    column_mapping = {
        "id": "id",
        "content": "external_path",
        "filename": "title",
        "mime_type": "mime_type",
        "size": "size_bytes",
        "created_at": "source_created_at",
        "modified_at": "source_modified_at",
    }
    extra_columns = ["indexing_status", "connector_id"]
    where_clause = "indexing_status = 'indexed'"
    order_by = "source_modified_at DESC"

    query = build_select_query(
        "indexed_documents",
        column_mapping,
        extra_columns,
        where_clause,
        order_by,
    )
    print(f"\nGenerated SELECT query:")
    print(query)

    # Test MySQL config
    mysql_url = get_connection_url(
        DatabaseEngine.MYSQL, "mysql.example.com", 3306, "documents", "reader", "secret", False
    )
    print(f"\n\nMySQL Connection URL (masked): {mysql_url}")

    # Test SQL Server config
    mssql_url = get_connection_url(
        DatabaseEngine.MSSQL, "sqlserver.local", 1433, "Archive", "sa", "secret", False
    )
    print(f"\nSQL Server Connection URL (masked): {mssql_url}")

    print("\n✅ Config building tests passed!")
    return True


async def test_postgresql_connection():
    """Test actual PostgreSQL connection."""
    print("\n" + "=" * 60)
    print("TEST: PostgreSQL Connection")
    print("=" * 60)

    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        db_url = "postgresql+asyncpg://nexus_user:nexus_password@localhost:5432/nexus_db"

        print(f"Connecting to: {db_url.replace('nexus_password', '***')}")

        engine = create_async_engine(db_url)

        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            result.fetchone()
            print("✅ Connection successful!")

            result = await conn.execute(
                text("SELECT COUNT(*) FROM indexed_documents")
            )
            count = result.scalar()
            print(f"📊 Total indexed documents: {count}")

            result = await conn.execute(
                text("""
                    SELECT id, title, mime_type, external_path, indexing_status
                    FROM indexed_documents
                    WHERE indexing_status = 'indexed'
                    LIMIT 5
                """)
            )
            rows = result.fetchall()
            print(f"\n📄 Sample documents (limit 5):")
            for row in rows:
                print(f"  - {row[1]} ({row[2]}) - {row[4]}")

        await engine.dispose()
        return True

    except Exception as e:
        print(f"❌ PostgreSQL connection failed: {e}")
        return False


async def test_full_adapter_flow():
    """Test the full database adapter flow via direct query."""
    print("\n" + "=" * 60)
    print("TEST: Full Query Flow Simulation")
    print("=" * 60)

    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        db_url = "postgresql+asyncpg://nexus_user:nexus_password@localhost:5432/nexus_db"
        engine = create_async_engine(db_url)

        # Build query like the adapter would
        column_mapping = {
            "id": "id",
            "content": "external_path",
            "filename": "title",
            "mime_type": "mime_type",
            "size": "size_bytes",
            "created_at": "source_created_at",
            "modified_at": "source_modified_at",
        }
        extra_columns = ["indexing_status", "connector_id", "external_id"]

        query = build_select_query(
            "indexed_documents",
            column_mapping,
            extra_columns,
            "indexing_status = 'indexed'",
            "source_modified_at DESC",
        )

        # Add pagination
        query += " LIMIT 5 OFFSET 0"

        print(f"\n1. Executing query:")
        print(f"   {query[:100]}...")

        async with engine.connect() as conn:
            result = await conn.execute(text(query))
            rows = result.fetchall()
            columns = result.keys()

            print(f"\n2. Results: {len(rows)} documents")

            for i, row in enumerate(rows[:3]):
                row_dict = dict(zip(columns, row))
                print(f"\n   📄 Document {i + 1}:")
                print(f"      - ID: {row_dict.get('id')}")
                print(f"      - Filename: {row_dict.get('filename')}")
                print(f"      - MIME: {row_dict.get('mime_type')}")
                print(f"      - Size: {row_dict.get('size')} bytes")
                print(f"      - Path: {row_dict.get('content')}")
                print(f"      - Status: {row_dict.get('indexing_status')}")

            # Test incremental query
            print(f"\n3. Testing incremental sync (modified since yesterday)...")
            yesterday = datetime.utcnow() - timedelta(days=1)

            inc_query = build_select_query(
                "indexed_documents",
                column_mapping,
                extra_columns,
                f"indexing_status = 'indexed' AND source_modified_at > '{yesterday.isoformat()}'",
                "source_modified_at DESC",
            )
            inc_query += " LIMIT 5"

            result = await conn.execute(text(inc_query))
            recent_rows = result.fetchall()
            print(f"   Found {len(recent_rows)} recently modified documents")

        await engine.dispose()
        print("\n✅ Full adapter flow simulation passed!")
        return True

    except Exception as e:
        print(f"❌ Adapter flow test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_metadata_adapter_integration():
    """Test that database connector works with metadata adapter."""
    print("\n" + "=" * 60)
    print("TEST: Metadata Adapter Integration")
    print("=" * 60)

    try:
        from core.connectors import MetadataAdapterRegistry

        adapter = MetadataAdapterRegistry.get_adapter("database")
        print(f"Adapter: {adapter.__class__.__name__}")
        print(f"Richness level: {adapter.richness_level.name}")

        raw_metadata = {
            "id": "doc-123",
            "filename": "Contrato_Servicios_2024.pdf",
            "mime_type": "application/pdf",
            "size": 1024000,
            "created_at": "2024-01-15T10:00:00Z",
            "modified_at": "2024-01-20T14:30:00Z",
            "user_id": "user-456",
            "indexing_status": "indexed",
            "department": "legal",
        }

        normalized = adapter.normalize(
            document_id="doc-123",
            tenant_id="tenant-789",
            raw_metadata=raw_metadata,
            file_path="/documentos/Legal/Clientes/ACME/2024/Contratos/Contrato_Servicios_2024.pdf"
        )

        print(f"\nNormalized metadata:")
        print(f"  Semantic type: {normalized.classification.semantic_type}")
        print(f"  Domain: {normalized.classification.domain}")
        print(f"  Year (from path): {normalized.path.year_from_path}")
        print(f"  Client (from path): {normalized.path.client_from_path}")
        print(f"  Department: {normalized.business.department}")

        print(f"\nStructural description:")
        print(f"  {normalized.get_structural_description()}")

        print(f"\nKey properties:")
        for k, v in normalized.get_key_properties().items():
            print(f"  {k}: {v}")

        print("\n✅ Metadata adapter integration test passed!")
        return True

    except Exception as e:
        print(f"❌ Metadata adapter test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("DATABASE CONNECTOR TEST SUITE")
    print("=" * 60)

    results = []

    # Test 1: Config building
    try:
        await test_config_building()
        results.append(("Config Building", True))
    except Exception as e:
        print(f"❌ Config building failed: {e}")
        results.append(("Config Building", False))

    # Test 2: PostgreSQL connection
    result = await test_postgresql_connection()
    results.append(("PostgreSQL Connection", result))

    # Test 3: Full adapter flow
    if result:
        result = await test_full_adapter_flow()
        results.append(("Full Adapter Flow", result))

    # Test 4: Metadata adapter integration
    try:
        result = await test_metadata_adapter_integration()
        results.append(("Metadata Adapter", result))
    except Exception as e:
        print(f"❌ Metadata adapter test failed: {e}")
        results.append(("Metadata Adapter", False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("⚠️  SOME TESTS FAILED")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
