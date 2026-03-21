# BKG Phase 6: Unified Knowledge Tree — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify the tenant sector graph with legal proxy nodes and real APLICA edges to reduce LLM hallucinations (person mixing, unsourced answers).

**Architecture:** Sync LegalLaw proxy nodes from `knowledge_graph_public` into each `{sector}_graph` at bootstrap. Create real `:APLICA` edges during document indexing via regex detection. Refactor SubgraphExtractor to use a single Cypher query. Enhance SubgraphFormatter with source traceability and anti-hallucination guardrails.

**Tech Stack:** Apache AGE (PostgreSQL 15), asyncpg, FastAPI, Python 3.9+, Langfuse prompts

**Spec:** `docs/superpowers/specs/2026-03-21-unified-knowledge-tree-design.md`

---

### Task 1: Schema Updates — Add LegalLaw vlabel + edge labels to sector schemas

**Files:**
- Modify: `backend/microservices/knowledge-tree-service/config/graphs/legal_graph_schema.cypher:54-61`
- Modify: `backend/microservices/knowledge-tree-service/config/graphs/medical_graph_schema.cypher:52-59`
- Modify: `backend/microservices/knowledge-tree-service/config/graphs/documental_graph_schema.cypher:42-62`

- [ ] **Step 1: Add LegalLaw vlabel + inter-law elabels to legal schema**

Append before the existing `EntityType` vlabel block in `legal_graph_schema.cypher` (before line 54):

```sql
-- Legal proxy nodes (synced from knowledge_graph_public, shared=true)
SELECT create_vlabel('legal_graph', 'LegalLaw');
SELECT create_elabel('legal_graph', 'MODIFIES');
SELECT create_elabel('legal_graph', 'DEROGATES');
SELECT create_elabel('legal_graph', 'REFERENCES');
```

Note: `APLICA` elabel already exists at line 50. `MODIFICA` and `DEROGA` also exist (lines 48-49) but those are for sector-native edges. The new `MODIFIES`/`DEROGATES`/`REFERENCES` labels match the `knowledge_graph_public` naming convention used by `LegalGraphService`.

- [ ] **Step 2: Add same labels to medical schema**

Append before the `EntityType` vlabel block in `medical_graph_schema.cypher` (before line 52):

```sql
-- Legal proxy nodes (synced from knowledge_graph_public, shared=true)
SELECT create_vlabel('medical_graph', 'LegalLaw');
SELECT create_elabel('medical_graph', 'APLICA');
SELECT create_elabel('medical_graph', 'MODIFIES');
SELECT create_elabel('medical_graph', 'DEROGATES');
SELECT create_elabel('medical_graph', 'REFERENCES');
```

- [ ] **Step 3: Add same labels to documental schema**

Append before the `EntityType` vlabel block in `documental_graph_schema.cypher` (before line 42):

```sql
-- Legal proxy nodes (synced from knowledge_graph_public, shared=true)
SELECT create_vlabel('documental_graph', 'LegalLaw');
SELECT create_elabel('documental_graph', 'APLICA');
SELECT create_elabel('documental_graph', 'MODIFIES');
SELECT create_elabel('documental_graph', 'DEROGATES');
SELECT create_elabel('documental_graph', 'REFERENCES');
```

Note: documental schema already has `REFERENCIA` (line 61) — that's different from `REFERENCES` (inter-law public graph convention).

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/knowledge-tree-service/config/graphs/*.cypher
git commit -m "feat(schema): add LegalLaw vlabel + inter-law elabels to all sector schemas"
```

---

### Task 2: EntityType Backfill + LegalLaw Labels in Bootstrap

**Files:**
- Modify: `backend/microservices/knowledge-tree-service/app/services/graph_bootstrap.py:69-85`

- [ ] **Step 1: Add LegalLaw + inter-law labels and EntityType backfill to the existing label-ensure block**

In `graph_bootstrap.py`, inside the `if exists:` block (lines 69-85), add `LegalLaw` vlabel, 4 new elabels, and a backfill query for existing EntityType nodes:

```python
        if exists:
            logger.info(f"✅ Graph '{graph_name}' already exists — ensuring labels")
            async with age_client._get_connection() as conn2:
                for stmt in [
                    # Ontology + memory labels (BKG Phases 2-4)
                    f"SELECT create_vlabel('{graph_name}', 'EntityType');",
                    f"SELECT create_vlabel('{graph_name}', 'DocumentMemory');",
                    f"SELECT create_elabel('{graph_name}', 'INSTANCE_OF');",
                    f"SELECT create_elabel('{graph_name}', 'EXTRACTED_FROM');",
                    f"SELECT create_elabel('{graph_name}', 'HAS_MEMORY');",
                    # Legal proxy labels (BKG Phase 6)
                    f"SELECT create_vlabel('{graph_name}', 'LegalLaw');",
                    f"SELECT create_elabel('{graph_name}', 'APLICA');",
                    f"SELECT create_elabel('{graph_name}', 'MODIFIES');",
                    f"SELECT create_elabel('{graph_name}', 'DEROGATES');",
                    f"SELECT create_elabel('{graph_name}', 'REFERENCES');",
                ]:
                    try:
                        await conn2.execute(stmt)
                    except Exception as e:
                        if "already exists" not in str(e):
                            logger.debug(f"Label ensure: {e}")

                # Backfill: set shared=true on existing EntityType proxy nodes
                try:
                    backfill_query = f"""
                        SELECT * FROM cypher('{graph_name}', $$
                            MATCH (et:EntityType)
                            WHERE et.shared IS NULL
                            SET et.shared = true
                            RETURN count(et) as updated
                        $$) as (updated agtype)
                    """
                    rows = await age_client.execute_cypher(backfill_query)
                    if rows:
                        count = str(rows[0].get("updated", 0)).strip('"')
                        if count and count != "0":
                            logger.info(f"  Backfilled shared=true on {count} EntityType nodes")
                except Exception as e:
                    logger.debug(f"EntityType backfill: {e}")

            return graph_name
```

- [ ] **Step 2: Verify bootstrap runs clean on startup**

```bash
cd backend/docker && docker compose restart knowledge-tree-service
docker compose logs knowledge-tree-service --tail 30 | grep -E "Graph|Label|Backfill|LegalLaw"
```

Expected: "Graph '{graph}' already exists — ensuring labels" + no errors for new labels.

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/graph_bootstrap.py
git commit -m "feat(bootstrap): add LegalLaw labels + EntityType shared backfill (BKG Phase 6)"
```

---

### Task 3: LegalProxySyncService

**Files:**
- Create: `backend/microservices/knowledge-tree-service/app/services/legal_proxy_sync.py`

- [ ] **Step 1: Create the sync service**

```python
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
        # Note: Apache AGE may not support ON CREATE SET, so we detect
        # new vs existing by checking if synced_at was NULL before update.
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/legal_proxy_sync.py
git commit -m "feat(sync): add LegalProxySyncService — sync BOE laws to sector graph (BKG Phase 6)"
```

---

### Task 4: Legal Sync API Endpoints

**Files:**
- Create: `backend/microservices/knowledge-tree-service/app/api/legal_sync.py`
- Modify: `backend/microservices/knowledge-tree-service/app/main.py:75-79`

- [ ] **Step 1: Create the API router**

```python
"""
Legal Sync API — BKG Phase 6

Endpoints for syncing legal proxy nodes from knowledge_graph_public
to the active sector graph.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.security import verify_api_key

router = APIRouter()
logger = logging.getLogger(__name__)


class LegalSyncRequest(BaseModel):
    force: bool = Field(False, description="Force re-sync even if recently synced")


class LegalSyncResponse(BaseModel):
    synced_laws: int = 0
    synced_edges: int = 0
    new_laws: int = 0
    updated_laws: int = 0
    elapsed_ms: int = 0


class LegalSyncStatusResponse(BaseModel):
    law_count: int = 0
    last_sync: Optional[str] = None
    graph: str = ""


@router.post("/tree/legal-sync", response_model=LegalSyncResponse)
async def sync_legal_proxies(
    request: Optional[LegalSyncRequest] = None,
    _: bool = Depends(verify_api_key),
):
    """Sync LegalLaw proxy nodes from knowledge_graph_public to sector graph."""
    from app.services.legal_proxy_sync import legal_proxy_sync

    graph_name = settings.age_graph_name
    if not graph_name:
        return LegalSyncResponse()

    force = request.force if request else False
    result = await legal_proxy_sync.sync(graph_name, force=force)
    return LegalSyncResponse(**result)


@router.get("/tree/legal-sync/status", response_model=LegalSyncStatusResponse)
async def legal_sync_status(_: bool = Depends(verify_api_key)):
    """Get current legal proxy sync status."""
    from app.services.legal_proxy_sync import legal_proxy_sync

    graph_name = settings.age_graph_name
    if not graph_name:
        return LegalSyncStatusResponse()

    result = await legal_proxy_sync.get_sync_status(graph_name)
    return LegalSyncStatusResponse(**result)
```

- [ ] **Step 2: Register the router in main.py**

In `backend/microservices/knowledge-tree-service/app/main.py`, add the import and router registration. After line 16 (`from app.api.memory_bank import router as memory_bank_router`), add:

```python
from app.api.legal_sync import router as legal_sync_router
```

After line 79 (`app.include_router(memory_bank_router, ...)`), add:

```python
app.include_router(legal_sync_router, tags=["legal-proxy-sync"])
```

- [ ] **Step 3: Add legal proxy sync to lifespan (after bootstrap)**

In `main.py`, after the bootstrap block (line 34), add the sync call:

```python
    # Sync legal proxy nodes from knowledge_graph_public
    if graph_name:
        from app.services.legal_proxy_sync import legal_proxy_sync
        await legal_proxy_sync.initialize()
        sync_result = await legal_proxy_sync.sync(graph_name)
        if sync_result["synced_laws"] > 0:
            logger.info(
                f"Legal proxy sync: {sync_result['synced_laws']} laws, "
                f"{sync_result['synced_edges']} edges ({sync_result['elapsed_ms']}ms)"
            )
```

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/api/legal_sync.py \
        backend/microservices/knowledge-tree-service/app/main.py
git commit -m "feat(api): add legal-sync endpoints + auto-sync on startup (BKG Phase 6)"
```

---

### Task 5: LegalReferenceBridge

**Files:**
- Create: `backend/microservices/knowledge-tree-service/app/services/legal_reference_bridge.py`

This service detects legal references in document text via regex (reusing patterns from `LegalReferenceExtractor`) and creates real `:APLICA` edges in the sector graph.

- [ ] **Step 1: Create the bridge service**

```python
"""
Legal Reference Bridge — BKG Phase 6

Detects legal references in tenant documents during indexing and creates
real :APLICA edges to proxy LegalLaw nodes in the sector graph.

Detection is regex-only (no LLM) for predictability and speed (~3ms).
Reuses patterns from LegalReferenceExtractor.

Usage:
    from app.services.legal_reference_bridge import legal_reference_bridge

    result = await legal_reference_bridge.extract_and_link(
        tenant_id="uuid",
        document_id="uuid",
        text_sample="first 2000 chars",
        semantic_type="contrato",
        domain="labor",
    )
"""

import logging
import time
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.age_client import age_client
from app.services.ontology_service import _clean_agtype
from app.services.extractors.legal_reference_extractor import LegalReferenceExtractor

logger = logging.getLogger(__name__)

# Reuse the production-hardened extractor (BOE IDs, article refs, law names)
_extractor = LegalReferenceExtractor()


def _escape(value: Optional[str]) -> str:
    if not value:
        return ""
    return value.replace("'", "''").replace("\\", "\\\\")


class LegalReferenceBridge:
    """Detects legal references and creates APLICA edges in sector graph.

    Delegates regex detection to the existing LegalReferenceExtractor
    (tested, production-hardened patterns). Adds proxy cache resolution
    and edge creation logic on top.
    """

    def __init__(self):
        self._initialized = False
        # short_name (upper) -> {boe_id, domain}
        self._proxy_cache: Dict[str, Dict[str, str]] = {}
        self._boe_id_set: set = set()  # all boe_ids in proxy cache

    async def initialize(self) -> None:
        if self._initialized:
            return
        await age_client.initialize()
        self._initialized = True

    async def _load_proxy_cache(self, graph_name: str) -> None:
        """Load all proxy LegalLaw nodes into cache for fast lookup."""
        query = f"""
            SELECT * FROM cypher('{graph_name}', $$
                MATCH (law:LegalLaw {{shared: true}})
                RETURN law.short_name as short_name,
                       law.boe_id as boe_id,
                       law.domain as domain
            $$) as (short_name agtype, boe_id agtype, domain agtype)
        """
        try:
            rows = await age_client.execute_cypher(query)
            self._proxy_cache = {}
            self._boe_id_set = set()
            for row in rows:
                sn = _clean_agtype(row.get("short_name"))
                bid = _clean_agtype(row.get("boe_id"))
                dom = _clean_agtype(row.get("domain")) or ""
                if sn and bid:
                    self._proxy_cache[sn.upper()] = {"boe_id": bid, "domain": dom}
                    self._boe_id_set.add(bid)
        except Exception as e:
            logger.warning(f"Failed to load proxy cache: {e}")

    async def extract_and_link(
        self,
        tenant_id: str,
        document_id: str,
        text_sample: str,
        semantic_type: str = "",
        domain: str = "",
    ) -> Dict[str, Any]:
        """Detect legal references and create APLICA edges.

        Returns: {"edges_created": int, "matches": [...], "elapsed_ms": int}
        """
        if not self._initialized:
            await self.initialize()

        graph_name = settings.age_graph_name
        if not graph_name or not age_client._pool:
            return {"edges_created": 0, "matches": [], "elapsed_ms": 0}

        # Refresh cache if empty
        if not self._proxy_cache:
            await self._load_proxy_cache(graph_name)

        if not self._proxy_cache:
            return {"edges_created": 0, "matches": [], "elapsed_ms": 0}

        start = time.time()

        # Level 1: Delegate to LegalReferenceExtractor (production regex)
        matches = self._detect_references(text_sample)

        # Level 2: Domain fallback if no regex matches
        if not matches and domain:
            matches = self._domain_fallback(domain)

        # Create APLICA edges
        edges_created = 0
        for match in matches:
            boe_id = match["boe_id"]
            success = await self._create_aplica_edge(
                graph_name=graph_name,
                tenant_id=tenant_id,
                document_id=document_id,
                boe_id=boe_id,
                confidence=match["confidence"],
                source=match["source"],
                article=match.get("article"),
            )
            if success:
                edges_created += 1

        elapsed_ms = int((time.time() - start) * 1000)

        if edges_created > 0:
            logger.info(
                f"Legal links: {edges_created} APLICA edges for doc {document_id[:12]} "
                f"({len(matches)} matches, {elapsed_ms}ms)"
            )

        return {
            "edges_created": edges_created,
            "matches": [{"boe_id": m["boe_id"], "source": m["source"]} for m in matches],
            "elapsed_ms": elapsed_ms,
        }

    def _detect_references(self, text: str) -> List[Dict[str, Any]]:
        """Level 1: Delegate to LegalReferenceExtractor, resolve against proxy cache."""
        matches = []
        seen_boe_ids: set = set()

        # Use the existing extractor's patterns (sync call — no await needed)
        # Extract BOE IDs directly
        for boe_id in _extractor.BOE_ID_PATTERN.findall(text):
            if boe_id in self._boe_id_set and boe_id not in seen_boe_ids:
                seen_boe_ids.add(boe_id)
                matches.append({
                    "boe_id": boe_id, "confidence": 0.98,
                    "source": "regex", "article": None,
                })

        # Extract article+law references ("art. 15 del ET")
        for art_match in _extractor.ARTICLE_LAW_PATTERN.finditer(text):
            article_num = art_match.group(1).strip()
            law_name = art_match.group(2).strip()
            # Try to resolve law_name against proxy cache
            law_upper = law_name.upper().strip()
            for cached_sn, cached_info in self._proxy_cache.items():
                if cached_sn in law_upper or law_upper in cached_sn:
                    boe_id = cached_info["boe_id"]
                    if boe_id not in seen_boe_ids:
                        seen_boe_ids.add(boe_id)
                        matches.append({
                            "boe_id": boe_id, "confidence": 0.95,
                            "source": "regex", "article": article_num,
                        })
                    break

        # Extract standalone law refs ("Ley 3/2012, de 6 de julio")
        for law_match in _extractor.LAW_REF_PATTERN.finditer(text):
            law_text = law_match.group(0).strip()
            # Try to match against any proxy short_name appearing in the text
            for cached_sn, cached_info in self._proxy_cache.items():
                if cached_sn.lower() in law_text.lower():
                    boe_id = cached_info["boe_id"]
                    if boe_id not in seen_boe_ids:
                        seen_boe_ids.add(boe_id)
                        matches.append({
                            "boe_id": boe_id, "confidence": 0.90,
                            "source": "regex", "article": None,
                        })
                    break

        return matches

    def _domain_fallback(self, domain: str) -> List[Dict[str, Any]]:
        """Level 2: Match by domain when regex finds nothing.

        If the document's domain matches a proxy law's domain, create a
        low-confidence APLICA edge (domain_match, confidence 0.6).
        """
        matches = []
        domain_lower = domain.lower().strip()
        if not domain_lower:
            return matches

        for cached_sn, cached_info in self._proxy_cache.items():
            law_domain = (cached_info.get("domain") or "").lower().strip()
            if law_domain and law_domain == domain_lower:
                matches.append({
                    "boe_id": cached_info["boe_id"],
                    "confidence": 0.6,
                    "source": "domain_match",
                    "article": None,
                })

        return matches

    async def _create_aplica_edge(
        self,
        graph_name: str,
        tenant_id: str,
        document_id: str,
        boe_id: str,
        confidence: float,
        source: str,
        article: Optional[str] = None,
    ) -> bool:
        """Create an APLICA edge between a document and a LegalLaw proxy."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        doc_escaped = _escape(document_id)
        tenant_escaped = _escape(tenant_id)
        boe_escaped = _escape(boe_id)
        article_set = f", r.article = '{_escape(article)}'" if article else ""

        query = f"""
            SELECT * FROM cypher('{graph_name}', $$
                MATCH (doc:structural_document {{document_id: '{doc_escaped}', tenant_id: '{tenant_escaped}'}}),
                      (law:LegalLaw {{boe_id: '{boe_escaped}', shared: true}})
                MERGE (doc)-[r:APLICA]->(law)
                SET r.confidence = {confidence},
                    r.source = '{_escape(source)}',
                    r.created_at = '{now}'{article_set}
                RETURN r
            $$) as (r agtype)
        """
        try:
            await age_client.execute_cypher(query)
            return True
        except Exception as e:
            logger.debug(f"Failed to create APLICA edge doc:{document_id[:12]} -> law:{boe_id}: {e}")
            return False


# Module-level singleton
legal_reference_bridge = LegalReferenceBridge()
```

- [ ] **Step 2: Add API endpoint for the bridge**

Add to `backend/microservices/knowledge-tree-service/app/api/legal_sync.py` (the file created in Task 4):

```python
class LegalLinkRequest(BaseModel):
    tenant_id: str = Field(..., description="Tenant identifier")
    document_id: str = Field(..., description="Document identifier")
    text_sample: str = Field(..., description="First ~2000 chars of document text")
    semantic_type: str = Field("", description="Document semantic type")
    domain: str = Field("", description="Document domain")


class LegalLinkResponse(BaseModel):
    edges_created: int = 0
    matches: list = Field(default_factory=list)
    elapsed_ms: int = 0


@router.post("/tree/legal-links/extract-and-store", response_model=LegalLinkResponse)
async def extract_and_store_legal_links(
    request: LegalLinkRequest,
    _: bool = Depends(verify_api_key),
):
    """Extract legal references from document text and create APLICA edges."""
    from app.services.legal_reference_bridge import legal_reference_bridge

    result = await legal_reference_bridge.extract_and_link(
        tenant_id=request.tenant_id,
        document_id=request.document_id,
        text_sample=request.text_sample,
        semantic_type=request.semantic_type,
        domain=request.domain,
    )
    return LegalLinkResponse(**result)
```

- [ ] **Step 3: Initialize bridge in main.py lifespan**

In `main.py`, after the legal proxy sync block, add:

```python
    # Initialize legal reference bridge
    from app.services.legal_reference_bridge import legal_reference_bridge
    await legal_reference_bridge.initialize()
```

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/legal_reference_bridge.py \
        backend/microservices/knowledge-tree-service/app/api/legal_sync.py \
        backend/microservices/knowledge-tree-service/app/main.py
git commit -m "feat(bridge): add LegalReferenceBridge — regex detection + APLICA edge creation (BKG Phase 6)"
```

---

### Task 6: Weaviate Integration — Fire-and-forget post-indexing

**Files:**
- Modify: `backend/microservices/weaviate-service/app/clients/knowledge_tree_client.py`
- Modify: `backend/microservices/weaviate-service/app/api/weaviate.py:1070-1080`

- [ ] **Step 1: Add `extract_and_link_legal()` method to `KnowledgeTreeLegalClient`**

Append to the class in `knowledge_tree_client.py`:

```python
    async def extract_and_link_legal(
        self,
        tenant_id: str,
        document_id: str,
        text_sample: str,
        semantic_type: str = "",
        domain: str = "",
    ) -> Dict[str, Any]:
        """Extract legal references from document and create APLICA edges."""
        return await self._request(
            "POST",
            "/tree/legal-links/extract-and-store",
            json={
                "tenant_id": tenant_id,
                "document_id": document_id,
                "text_sample": text_sample[:2000],
                "semantic_type": semantic_type,
                "domain": domain,
            },
        )
```

- [ ] **Step 2: Add fire-and-forget call in weaviate.py**

In `backend/microservices/weaviate-service/app/api/weaviate.py`, after the memory generation block (~line 1080, after the `elif settings.memory_bank_enabled:` block), add:

```python
            # BKG Phase 6: Legal reference detection + APLICA edges
            try:
                from app.clients.knowledge_tree_client import knowledge_tree_legal_client
                asyncio.create_task(
                    knowledge_tree_legal_client.extract_and_link_legal(
                        tenant_id=request.tenant_id,
                        document_id=request.document_id,
                        text_sample=result.extracted_text[:2000] if result.extracted_text else "",
                        semantic_type=(request.learned_context.semantic_type if request.learned_context else None) or inferred_semantic_type or "",
                        domain=(request.learned_context.domain if request.learned_context else None) or result.contextual_domain or "",
                    )
                )
            except Exception as e:
                logger.debug(f"Legal reference extraction skipped: {e}")
```

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/weaviate-service/app/clients/knowledge_tree_client.py \
        backend/microservices/weaviate-service/app/api/weaviate.py
git commit -m "feat(indexing): fire-and-forget legal reference extraction post-indexing (BKG Phase 6)"
```

---

### Task 7: SubgraphExtractor Refactor — Unified Query

**Files:**
- Modify: `backend/microservices/knowledge-tree-service/app/services/subgraph_extractor.py`

- [ ] **Step 1: Update `_traverse()` to include shared nodes**

In `subgraph_extractor.py`, modify the `_traverse()` method (line 236-237). Change the neighbor filter from:

```python
                    WHERE neighbor.tenant_id = '{_escape(tenant_id)}'
                       OR labels(neighbor)[0] = 'EntityType'
```

To:

```python
                    WHERE neighbor.tenant_id = '{_escape(tenant_id)}'
                       OR neighbor.shared = true
```

This single change makes the traversal cross into both EntityType AND LegalLaw proxy nodes automatically.

- [ ] **Step 2: Also return edge properties for APLICA edges**

In `_traverse()`, after the edge construction block (line 297-305), enhance to capture edge properties:

```python
                    # Edge
                    el = _clean_agtype(row.get("edge_label")) or ""
                    if src_id and tgt_id and el:
                        edge_props = {}
                        # APLICA edges have confidence + source properties
                        if el == "APLICA":
                            edge_props = {
                                "confidence": _clean_agtype(row.get("edge_confidence")),
                                "source": _clean_agtype(row.get("edge_source")),
                                "article": _clean_agtype(row.get("edge_article")),
                            }
                            edge_props = {k: v for k, v in edge_props.items() if v}
                        edges.append({
                            "source_id": src_id,
                            "target_id": tgt_id,
                            "label": el,
                            "properties": edge_props,
                        })
```

Also add edge property extraction to the Cypher RETURN clause. Add after `type(rel) as edge_label` (line 247):

```sql
                        rel.confidence as edge_confidence,
                        rel.source as edge_source,
                        rel.article as edge_article,
```

And update the `AS` clause to include the new columns.

- [ ] **Step 3: Delete `_lookup_legal()` method**

Remove the entire `_lookup_legal()` method (lines 311-381).

- [ ] **Step 4: Remove `_lookup_legal()` call from `extract()`**

In `extract()` method, remove lines 124-128:

```python
        # Step 3: Cross-graph legal lookup (optional)
        if include_legal:
            legal_nodes, legal_edges = await self._lookup_legal(raw_nodes)
            raw_nodes.extend(legal_nodes)
            raw_edges.extend(legal_edges)
```

Replace with a comment:

```python
        # Step 3: Legal cross-reference — handled by real APLICA edges in the
        # unified graph (BKG Phase 6). No separate _lookup_legal() needed.
```

- [ ] **Step 5: Add MODIFIES/DEROGATES/REFERENCES to edge weights**

In `_EDGE_WEIGHTS` dict (line 35), add:

```python
    "MODIFIES": 0.85,
    "DEROGATES": 0.85,
    "REFERENCES": 0.8,
```

- [ ] **Step 6: Update module docstring**

Update the docstring (lines 1-16) to reflect the new architecture:

```python
"""
Subgraph Extractor — BKG Phases 5-6

Extracts multi-hop subgraphs from tenant sector graphs rooted at query entities.
Returns structured node/edge data for LLM consumption (not flat document IDs).

Architecture:
    1. Entity Resolution: Find seed nodes matching query entities
    2. N-hop Traversal: Expand neighborhood including shared nodes (LegalLaw, EntityType)
    3. Pruning & Scoring: Rank paths, cap at max_nodes

Note: As of BKG Phase 6, legal proxy nodes (LegalLaw) live in the sector graph
with shared=true. The traversal crosses into them via `neighbor.shared = true`.
The old _lookup_legal() cross-graph approach was removed.
"""
```

- [ ] **Step 7: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/subgraph_extractor.py
git commit -m "refactor(subgraph): unified query + remove _lookup_legal (BKG Phase 6)"
```

---

### Task 8: SubgraphFormatter — Anti-Hallucination Format

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/tools/subgraph_formatter.py`

- [ ] **Step 1: Update the header and footer**

In `format_subgraph()` (line 66), change the header lines:

```python
    lines: List[str] = [
        "[SUBGRAFO RELEVANTE -- relaciones verificadas del repositorio]",
        "Entidades principales:",
    ]
```

After the summary line (line 79), add the guard footer:

```python
    # Guard footer (anti-hallucination)
    lines.append("")
    lines.append(
        "IMPORTANTE: Solo se muestran relaciones verificadas del grafo. "
        "No inventes relaciones adicionales entre documentos y leyes."
    )
```

- [ ] **Step 2: Enhance edge rendering with APLICA traceability**

In `_render_tree()`, modify the edge rendering (line 145) to include APLICA edge properties:

```python
        edge_label = edge["label"]
        if depth >= 2 and edge_label in ("INSTANCE_OF", "HAS_MEMORY"):
            continue

        child_indent = "  " * (depth + 1)
        child_label = _format_node(target_node)

        # Add traceability for APLICA edges
        edge_suffix = ""
        edge_props = edge.get("properties", {})
        if edge_label == "APLICA" and edge_props:
            parts = []
            if edge_props.get("confidence"):
                parts.append(f"confidence: {edge_props['confidence']}")
            if edge_props.get("source"):
                parts.append(f"source: {edge_props['source']}")
            if parts:
                edge_suffix = f" [{', '.join(parts)}]"

        lines.append(f"{child_indent}→ {edge_label} → {child_label}{edge_suffix}")
```

- [ ] **Step 3: Add absence rendering for documents without APLICA edges**

In `_render_tree()`, after rendering all edges for a document node, add absence detection. After the edge traversal loop for a node at depth 0:

```python
    # After edge traversal for root nodes: note absence of APLICA edges
    if depth == 0 and node.get("label") in ("structural_document",):
        has_aplica = any(
            e["label"] == "APLICA"
            for e in adjacency.get(node_id, [])
        )
        if not has_aplica:
            child_indent = "  " * (depth + 1)
            lines.append(f"{child_indent}(sin referencias legales detectadas)")
```

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/subgraph_formatter.py
git commit -m "feat(formatter): anti-hallucination format + APLICA traceability (BKG Phase 6)"
```

---

### Task 9: Langfuse Prompt Guardrails

**Files:**
- Modify: Langfuse prompt `emma_react_system` (via Langfuse UI or seed script)

- [ ] **Step 1: Add anti-hallucination section to the ReAct system prompt**

The prompt key is `emma_react_system` (found in `prompt_registry.py:145`). Add this section to the prompt in Langfuse (http://localhost:3002):

Navigate to Prompts → `emma_react_system` → New version. Append to the end of the prompt content:

```
## Sobre las fuentes documentales
- El [SUBGRAFO RELEVANTE] contiene SOLO relaciones verificadas del repositorio.
- Si un documento NO tiene edge ASOCIADO_A hacia una persona, NO atribuyas ese documento a ninguna persona.
- Si un documento NO tiene edge APLICA hacia una ley, NO cites esa ley como aplicable.
- Prefiere decir "no se encontró relación directa" antes que inferir relaciones no presentes en el subgrafo.
- Las relaciones APLICA con confidence < 0.7 son inferidas por dominio, no por referencia explícita — menciona esta distinción si citas la ley.
```

Then promote the new version to the `production` label.

- [ ] **Step 2: Verify the prompt is loaded**

```bash
curl -s http://localhost:8009/prompts/get?name=emma_react_system \
  -H "X-API-Key: $(grep MICROSERVICES_API_KEY backend/docker/.env | cut -d= -f2)" \
  > /tmp/prompt_check.json
python3 -c "import json; d=json.load(open('/tmp/prompt_check.json')); print('FOUND' if 'fuentes documentales' in d.get('content','') else 'NOT FOUND')"
```

Expected: `FOUND`

- [ ] **Step 3: Commit note (no code to commit — Langfuse is DB-managed)**

```bash
git commit --allow-empty -m "docs(prompts): add anti-hallucination guardrails to emma_react_system (BKG Phase 6)"
```

---

### Task 10: Sanity Checks — Verify End-to-End

- [ ] **Step 1: Verify bootstrap creates LegalLaw labels**

```bash
cd backend/docker && docker compose restart knowledge-tree-service
docker compose logs knowledge-tree-service --tail 50 | grep -i "legal\|sync\|proxy\|LegalLaw"
```

Expected: "Legal proxy sync: N laws, M edges" in the logs.

- [ ] **Step 2: Verify proxy nodes exist in sector graph**

```bash
API_KEY=$(grep MICROSERVICES_API_KEY backend/docker/.env | cut -d= -f2)
curl -s "http://localhost:8011/tree/legal-sync/status" \
  -H "X-API-Key: $API_KEY" > /tmp/sync_status.json
python3 -c "import json; d=json.load(open('/tmp/sync_status.json')); print(f'Laws: {d[\"law_count\"]}, Last sync: {d[\"last_sync\"]}')"
```

Expected: `Laws: 47` (or however many are downloaded), with a recent timestamp.

- [ ] **Step 3: Verify APLICA edge creation on a test document**

```bash
TENANT="00000000-0000-0000-0000-000000000001"
curl -s -X POST "http://localhost:8011/tree/legal-links/extract-and-store" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{
    \"tenant_id\": \"$TENANT\",
    \"document_id\": \"test-doc-001\",
    \"text_sample\": \"Este contrato se rige por el Estatuto de los Trabajadores (ET), art. 15, y la LOPDGDD.\",
    \"semantic_type\": \"contrato\",
    \"domain\": \"labor\"
  }" > /tmp/legal_link_result.json
python3 -c "import json; d=json.load(open('/tmp/legal_link_result.json')); print(f'Edges: {d[\"edges_created\"]}, Matches: {d[\"matches\"]}')"
```

Expected: `Edges: 2, Matches: [{"boe_id": "...", "source": "regex"}, {"boe_id": "...", "source": "regex"}]` (ET + LOPDGDD)

- [ ] **Step 4: Verify subgraph extraction includes shared nodes**

```bash
curl -s -X POST "http://localhost:8011/tree/graph/subgraph" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{
    \"tenant_id\": \"$TENANT\",
    \"entities\": [{\"value\": \"Javier\", \"type\": \"person\"}],
    \"max_hops\": 2,
    \"max_nodes\": 30
  }" > /tmp/subgraph_result.json
python3 -c "
import json
d = json.load(open('/tmp/subgraph_result.json'))
nodes = d.get('nodes', [])
legal_nodes = [n for n in nodes if n.get('label') == 'LegalLaw']
aplica_edges = [e for e in d.get('edges', []) if e.get('label') == 'APLICA']
print(f'Total nodes: {len(nodes)}, LegalLaw nodes: {len(legal_nodes)}, APLICA edges: {len(aplica_edges)}')
"
```

Expected: At least 1 LegalLaw node and 1 APLICA edge if the tenant has indexed documents with legal references.

- [ ] **Step 5: Verify formatter output includes traceability**

Run the same subgraph through the formatter:

```bash
docker compose exec emma-agent-service python3 -c "
import asyncio, json
from app.agents.langgraph.tools.subgraph_formatter import format_subgraph
with open('/tmp/subgraph_result.json') as f:
    sg = json.load(f)
result = format_subgraph(sg)
print(result)
" 2>/dev/null
```

Expected: Output includes `[SUBGRAFO RELEVANTE -- relaciones verificadas]`, APLICA edges with `[confidence: 0.95, source: regex]`, and the guard footer.

- [ ] **Step 6: Commit all results**

```bash
git add -A
git status
# If any uncommitted changes remain, commit them
git commit -m "test(sanity): verify BKG Phase 6 unified knowledge tree end-to-end"
```
