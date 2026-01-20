"""
MCP Database Query Tools.

SECURITY: All queries are read-only. Dangerous keywords are blocked.
"""

import logging
import re
from typing import Any, Dict, List, Optional

import asyncpg

from app.core.config import get_databases, settings, DatabaseConfig

logger = logging.getLogger(__name__)


def _validate_query(query: str) -> Optional[str]:
    """
    Validate that query is read-only.

    Returns error message if invalid, None if valid.
    """
    query_upper = query.upper()

    for keyword in settings.blocked_keywords_list:
        # Check for keyword as whole word
        if re.search(rf'\b{keyword}\b', query_upper):
            return f"Query contains blocked keyword: {keyword}"

    return None


async def db_query(
    database_name: str,
    query: str,
    tenant_id: str,
    params: Optional[List[Any]] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Execute a read-only SQL query on an external database.

    Use this tool when you need to retrieve data from an external database.
    SECURITY: Only SELECT queries are allowed. INSERT, UPDATE, DELETE are blocked.

    Args:
        database_name: Name of the configured database
        query: SQL query to execute (must be SELECT only)
        tenant_id: Tenant identifier for access control
        params: Optional query parameters (for parameterized queries)
        limit: Maximum rows to return (default 100, max 1000)

    Returns:
        Query result with:
        - rows: List of result rows as dicts
        - columns: Column names
        - row_count: Number of rows returned
    """
    databases = get_databases()

    if database_name not in databases:
        return {
            "success": False,
            "error": f"Unknown database: {database_name}",
            "available_databases": list(databases.keys()),
        }

    db = databases[database_name]

    if not db.is_accessible_by_tenant(tenant_id):
        return {
            "success": False,
            "error": f"Access denied to database {database_name}",
        }

    # Validate query is read-only
    error = _validate_query(query)
    if error:
        return {
            "success": False,
            "error": error,
        }

    # Enforce limit
    limit = min(limit, db.max_rows)

    # Add LIMIT if not present
    if "LIMIT" not in query.upper():
        query = f"{query.rstrip(';')} LIMIT {limit}"

    try:
        if db.db_type == "postgresql":
            return await _query_postgres(db, query, params)
        else:
            return {
                "success": False,
                "error": f"Database type {db.db_type} not yet supported",
            }

    except Exception as e:
        logger.error(f"Database query failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


async def _query_postgres(
    db: DatabaseConfig,
    query: str,
    params: Optional[List[Any]] = None
) -> Dict[str, Any]:
    """Execute query on PostgreSQL."""
    conn = await asyncpg.connect(
        host=db.host,
        port=db.port,
        user=db.username,
        password=db.password,
        database=db.database,
        timeout=db.timeout_seconds,
    )

    try:
        if params:
            rows = await conn.fetch(query, *params)
        else:
            rows = await conn.fetch(query)

        if rows:
            columns = list(rows[0].keys())
            data = [dict(row) for row in rows]
        else:
            columns = []
            data = []

        return {
            "success": True,
            "rows": data,
            "columns": columns,
            "row_count": len(data),
        }

    finally:
        await conn.close()


async def db_list_tables(
    database_name: str,
    tenant_id: str,
    schema: str = "public",
) -> Dict[str, Any]:
    """
    List tables in an external database.

    Use this tool to discover what tables are available in the database.

    Args:
        database_name: Name of the configured database
        tenant_id: Tenant identifier
        schema: Database schema (default: public)

    Returns:
        List of tables with:
        - tables: List of table names
        - schema: The schema queried
    """
    databases = get_databases()

    if database_name not in databases:
        return {"success": False, "error": f"Unknown database: {database_name}"}

    db = databases[database_name]

    if not db.is_accessible_by_tenant(tenant_id):
        return {"success": False, "error": "Access denied"}

    try:
        if db.db_type == "postgresql":
            query = """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = $1
                ORDER BY table_name
            """
            conn = await asyncpg.connect(
                host=db.host, port=db.port,
                user=db.username, password=db.password,
                database=db.database,
            )
            try:
                rows = await conn.fetch(query, schema)
                tables = [row['table_name'] for row in rows]
            finally:
                await conn.close()

            return {
                "success": True,
                "tables": tables,
                "schema": schema,
                "count": len(tables),
            }
        else:
            return {"success": False, "error": f"Unsupported: {db.db_type}"}

    except Exception as e:
        logger.error(f"List tables failed: {e}")
        return {"success": False, "error": str(e)}


async def db_describe_table(
    database_name: str,
    table_name: str,
    tenant_id: str,
    schema: str = "public",
) -> Dict[str, Any]:
    """
    Describe the structure of a table.

    Use this tool to understand the columns and types in a table
    before writing queries.

    Args:
        database_name: Name of the configured database
        table_name: Table to describe
        tenant_id: Tenant identifier
        schema: Database schema (default: public)

    Returns:
        Table structure with:
        - columns: List of column definitions (name, type, nullable)
        - table_name: The described table
    """
    databases = get_databases()

    if database_name not in databases:
        return {"success": False, "error": f"Unknown database: {database_name}"}

    db = databases[database_name]

    if not db.is_accessible_by_tenant(tenant_id):
        return {"success": False, "error": "Access denied"}

    try:
        if db.db_type == "postgresql":
            query = """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = $1 AND table_name = $2
                ORDER BY ordinal_position
            """
            conn = await asyncpg.connect(
                host=db.host, port=db.port,
                user=db.username, password=db.password,
                database=db.database,
            )
            try:
                rows = await conn.fetch(query, schema, table_name)
                columns = [
                    {
                        "name": row['column_name'],
                        "type": row['data_type'],
                        "nullable": row['is_nullable'] == 'YES',
                        "default": row['column_default'],
                    }
                    for row in rows
                ]
            finally:
                await conn.close()

            return {
                "success": True,
                "table_name": table_name,
                "schema": schema,
                "columns": columns,
                "column_count": len(columns),
            }
        else:
            return {"success": False, "error": f"Unsupported: {db.db_type}"}

    except Exception as e:
        logger.error(f"Describe table failed: {e}")
        return {"success": False, "error": str(e)}


async def list_databases(tenant_id: str) -> Dict[str, Any]:
    """
    List available databases for a tenant.

    Use this tool to discover what databases are accessible.

    Args:
        tenant_id: Tenant identifier

    Returns:
        List of databases with:
        - databases: List of database info (name, type)
    """
    databases = get_databases()

    available = []
    for name, db in databases.items():
        if db.is_accessible_by_tenant(tenant_id):
            available.append({
                "name": name,
                "type": db.db_type,
                "database": db.database,
            })

    return {
        "success": True,
        "databases": available,
        "count": len(available),
    }
