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
