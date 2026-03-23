"""
Bootstrap FalkorDB graph schema on service startup.

Ensures the knowledge graph exists with all required indexes and
constraints. Idempotent -- safe to run on every startup.
"""

import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


async def bootstrap_sector_graph() -> Optional[str]:
    """
    Bootstrap the FalkorDB graph schema.

    Returns:
        Graph name if bootstrapped/verified, None if disabled.
    """
    if not settings.rag_knowledge_graph_enabled:
        logger.info("Knowledge graph disabled -- skipping bootstrap")
        return None

    graph_name = settings.falkordb_graph_name

    try:
        from app.services.falkordb_client import falkordb_client

        await falkordb_client.initialize()
        await falkordb_client.bootstrap_schema()

        logger.info(f"FalkorDB graph '{graph_name}' bootstrapped successfully")
        return graph_name

    except Exception as e:
        logger.error(f"FalkorDB graph bootstrap failed: {e}")
        return None
