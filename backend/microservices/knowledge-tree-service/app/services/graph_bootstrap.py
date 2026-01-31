"""
Bootstrap Apache AGE graph schema on service startup.

Ensures the graph for the active sector exists with all required
node labels (vlabels) and edge labels (elabels). Idempotent — safe
to run on every startup.
"""

import logging
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

VALID_SECTORS = {"legal", "medical", "documental"}

SCHEMA_DIR = Path(__file__).parent.parent.parent / "config" / "graphs"

SECTOR_SCHEMA_FILES = {
    "legal": "legal_graph_schema.cypher",
    "medical": "medical_graph_schema.cypher",
    "documental": "documental_graph_schema.cypher",
}


async def bootstrap_sector_graph() -> Optional[str]:
    """
    Ensure the Apache AGE graph for the active sector exists.

    Reads ACTIVE_SECTOR from config, checks if the graph exists,
    and creates it from the .cypher schema file if missing.

    Returns:
        Graph name if bootstrapped/verified, None if no sector active.
    """
    sector = settings.active_sector
    if not sector:
        logger.info("No ACTIVE_SECTOR configured — skipping graph bootstrap")
        return None

    if sector not in VALID_SECTORS:
        logger.warning(f"Invalid ACTIVE_SECTOR='{sector}'. Valid: {', '.join(VALID_SECTORS)}")
        return None

    if not settings.rag_knowledge_graph_enabled:
        logger.info("Knowledge graph disabled — skipping bootstrap")
        return None

    graph_name = settings.age_graph_name or f"{sector}_graph"

    try:
        from app.services.age_client import age_client

        await age_client.initialize()
        if not age_client._pool:
            logger.warning("AGE client pool not available — skipping bootstrap")
            return None

        # Check if graph already exists
        async with age_client._get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT count(*) as cnt FROM ag_catalog.ag_graph WHERE name = $1",
                graph_name,
            )
            exists = row and row["cnt"] > 0

        if exists:
            logger.info(f"✅ Graph '{graph_name}' already exists — bootstrap OK")
            return graph_name

        # Graph doesn't exist — create from schema file
        schema_file = SCHEMA_DIR / SECTOR_SCHEMA_FILES.get(sector, "")
        if not schema_file.exists():
            logger.error(f"Schema file not found: {schema_file}")
            return None

        logger.info(f"🏗️  Creating graph '{graph_name}' from {schema_file.name}...")

        content = schema_file.read_text()
        statements = [
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("--") and line.strip().endswith(";")
        ]

        async with age_client._get_connection() as conn:
            for stmt in statements:
                try:
                    await conn.execute(stmt)
                    logger.info(f"  ✅ {stmt[:80]}")
                except Exception as e:
                    if "already exists" in str(e):
                        logger.debug(f"  ⏭️  {stmt[:60]}... (already exists)")
                    else:
                        logger.error(f"  ❌ {stmt[:60]}... ERROR: {e}")

        logger.info(f"✅ Graph '{graph_name}' bootstrapped successfully")
        return graph_name

    except Exception as e:
        logger.error(f"❌ Graph bootstrap failed: {e}")
        return None
