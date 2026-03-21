"""
Legal Proxy Sync Service — BKG Phase 6

Syncs LegalLaw nodes + inter-law relations from knowledge_graph_public
to the tenant's sector graph as proxy nodes with shared=true.

All operations are MERGE (idempotent). Safe to run repeatedly.

Usage:
    from app.services.legal_proxy_sync import legal_proxy_sync

    result = await legal_proxy_sync.sync("legal_graph")
"""

import logging
import time
from typing import Any, Dict, List, Optional

from app.services.age_client import age_client
from app.services.ontology_service import _clean_agtype

logger = logging.getLogger(__name__)

_VALID_INTER_LAW_RELATIONS = frozenset({"MODIFIES", "DEROGATES", "REFERENCES"})


def _escape(value: Optional[str]) -> str:
    if not value:
        return ""
    return value.replace("'", "''").replace("\\", "\\\\")


class LegalProxySyncService:
    """Syncs legal proxy nodes from knowledge_graph_public to sector graph."""

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        await age_client.initialize()
        self._initialized = True

    async def sync(self, target_graph: str, force: bool = False) -> Dict[str, Any]:
        """Sync all LegalLaw nodes + inter-law edges to the target sector graph.

        Args:
            target_graph: Name of the sector graph (e.g., 'legal_graph')
            force: If True, re-sync even if synced_at is recent

        Returns:
            {"synced_laws": int, "synced_edges": int, "new_laws": int, "updated_laws": int, "elapsed_ms": int}
        """
        if not self._initialized:
            await self.initialize()

        if not age_client._pool:
            logger.warning("AGE pool not available — skipping legal proxy sync")
            return {"synced_laws": 0, "synced_edges": 0, "new_laws": 0, "updated_laws": 0, "elapsed_ms": 0}

        start = time.time()

        # Check if knowledge_graph_public exists
        if not await self._graph_exists("knowledge_graph_public"):
            logger.info("knowledge_graph_public does not exist — skipping sync (no BOE downloaded yet)")
            return {"synced_laws": 0, "synced_edges": 0, "new_laws": 0, "updated_laws": 0, "elapsed_ms": 0}

        # Step 1: Fetch all laws from knowledge_graph_public
        laws = await self._fetch_public_laws()
        if not laws:
            logger.info("No laws found in knowledge_graph_public — skipping sync")
            return {"synced_laws": 0, "synced_edges": 0, "new_laws": 0, "updated_laws": 0, "elapsed_ms": 0}

        # Step 2: MERGE proxy nodes into target graph
        new_laws = 0
        updated_laws = 0
        for law in laws:
            is_new = await self._merge_proxy_law(target_graph, law)
            if is_new:
                new_laws += 1
            else:
                updated_laws += 1

        # Step 3: Fetch and sync inter-law relations
        relations = await self._fetch_inter_law_relations(
            [law["boe_id"] for law in laws]
        )
        synced_edges = 0
        for rel in relations:
            if rel["type"] not in _VALID_INTER_LAW_RELATIONS:
                logger.warning(f"Skipping invalid relation type: {rel['type']}")
                continue
            if await self._merge_inter_law_edge(target_graph, rel):
                synced_edges += 1

        elapsed_ms = int((time.time() - start) * 1000)

        logger.info(
            f"Legal proxy sync complete: {len(laws)} laws ({new_laws} new, {updated_laws} updated), "
            f"{synced_edges} edges, {elapsed_ms}ms"
        )

        return {
            "synced_laws": len(laws),
            "synced_edges": synced_edges,
            "new_laws": new_laws,
            "updated_laws": updated_laws,
            "elapsed_ms": elapsed_ms,
        }

    async def _graph_exists(self, graph_name: str) -> bool:
        try:
            async with age_client._get_connection() as conn:
                row = await conn.fetchrow(
                    "SELECT count(*) as cnt FROM ag_catalog.ag_graph WHERE name = $1",
                    graph_name,
                )
                return bool(row and row["cnt"] > 0)
        except Exception:
            return False

    async def _fetch_public_laws(self) -> List[Dict[str, str]]:
        query = """
            SELECT * FROM cypher('knowledge_graph_public', $$
                MATCH (law:LegalLaw)
                RETURN law.boe_id as boe_id,
                       law.short_name as short_name,
                       law.title as title,
                       law.domain as domain,
                       law.status as status
            $$) as (boe_id agtype, short_name agtype, title agtype, domain agtype, status agtype)
        """
        try:
            rows = await age_client.execute_cypher(query)
            laws = []
            for row in rows:
                boe_id = _clean_agtype(row.get("boe_id"))
                if not boe_id:
                    continue
                laws.append({
                    "boe_id": boe_id,
                    "short_name": _clean_agtype(row.get("short_name")) or "",
                    "title": _clean_agtype(row.get("title")) or "",
                    "domain": _clean_agtype(row.get("domain")) or "",
                    "status": _clean_agtype(row.get("status")) or "vigente",
                })
            return laws
        except Exception as e:
            logger.error(f"Failed to fetch public laws: {e}")
            return []

    async def _merge_proxy_law(self, target_graph: str, law: Dict[str, str]) -> bool:
        """MERGE a proxy LegalLaw node. Returns True if newly created."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        boe_id = _escape(law["boe_id"])
        query = f"""
            SELECT * FROM cypher('{target_graph}', $$
                MERGE (law:LegalLaw {{boe_id: '{boe_id}', shared: true}})
                SET law.short_name = '{_escape(law["short_name"])}',
                    law.domain = '{_escape(law["domain"])}',
                    law.status = '{_escape(law["status"])}',
                    law.title = '{_escape(law["title"])}',
                    law.synced_at = '{now}'
                RETURN law.synced_at = '{now}' as is_new
            $$) as (is_new agtype)
        """
        try:
            rows = await age_client.execute_cypher(query)
            if rows:
                return str(rows[0].get("is_new", "")).strip('"') == "true"
            return False
        except Exception as e:
            logger.warning(f"Failed to merge proxy law {law['boe_id']}: {e}")
            return False

    async def _fetch_inter_law_relations(self, boe_ids: List[str]) -> List[Dict[str, str]]:
        if not boe_ids:
            return []

        ids_list = ", ".join(f"'{_escape(bid)}'" for bid in boe_ids)
        query = f"""
            SELECT * FROM cypher('knowledge_graph_public', $$
                MATCH (a:LegalLaw)-[r]->(b:LegalLaw)
                WHERE a.boe_id IN [{ids_list}]
                  AND b.boe_id IN [{ids_list}]
                RETURN a.boe_id as source_boe_id,
                       type(r) as rel_type,
                       b.boe_id as target_boe_id
            $$) as (source_boe_id agtype, rel_type agtype, target_boe_id agtype)
        """
        try:
            rows = await age_client.execute_cypher(query)
            relations = []
            for row in rows:
                source = _clean_agtype(row.get("source_boe_id"))
                target = _clean_agtype(row.get("target_boe_id"))
                rel_type = _clean_agtype(row.get("rel_type"))
                if source and target and rel_type:
                    relations.append({
                        "source_boe_id": source,
                        "target_boe_id": target,
                        "type": rel_type,
                    })
            return relations
        except Exception as e:
            logger.error(f"Failed to fetch inter-law relations: {e}")
            return []

    async def _merge_inter_law_edge(self, target_graph: str, rel: Dict[str, str]) -> bool:
        rel_type = rel["type"]
        if rel_type not in _VALID_INTER_LAW_RELATIONS:
            return False

        source = _escape(rel["source_boe_id"])
        target = _escape(rel["target_boe_id"])
        query = f"""
            SELECT * FROM cypher('{target_graph}', $$
                MATCH (a:LegalLaw {{boe_id: '{source}', shared: true}}),
                      (b:LegalLaw {{boe_id: '{target}', shared: true}})
                MERGE (a)-[r:{rel_type}]->(b)
                RETURN r
            $$) as (r agtype)
        """
        try:
            await age_client.execute_cypher(query)
            return True
        except Exception as e:
            logger.warning(f"Failed to merge edge {source} -[{rel_type}]-> {target}: {e}")
            return False

    async def get_sync_status(self, target_graph: str) -> Dict[str, Any]:
        """Get current sync status for the target graph."""
        if not self._initialized:
            await self.initialize()

        query = f"""
            SELECT * FROM cypher('{target_graph}', $$
                MATCH (law:LegalLaw {{shared: true}})
                RETURN count(law) as law_count,
                       max(law.synced_at) as last_sync
            $$) as (law_count agtype, last_sync agtype)
        """
        try:
            rows = await age_client.execute_cypher(query)
            if rows:
                return {
                    "law_count": int(str(_clean_agtype(rows[0].get("law_count")) or "0")),
                    "last_sync": _clean_agtype(rows[0].get("last_sync")),
                    "graph": target_graph,
                }
        except Exception as e:
            logger.warning(f"Failed to get sync status: {e}")

        return {"law_count": 0, "last_sync": None, "graph": target_graph}


# Module-level singleton
legal_proxy_sync = LegalProxySyncService()
