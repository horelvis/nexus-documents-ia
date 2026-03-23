"""
Claim Extractor — Phase 3 GraphRAG Enhancement

Extracts structured Claims from document text using regex patterns.
Claims are stored as :Claim nodes in FalkorDB with :EXTRACTED_FROM,
:ABOUT, and :CONTRADICTS edges for evidence assembly.

Architecture:
    Document text -> Regex fast-path (~3ms) -> :Claim nodes + edges

Claim types:
    - temporal: dates (dd/mm/yyyy variants)
    - numeric: monetary amounts, percentages
    - legal_reference: BOE, Ley, Real Decreto references
    - factual: NIF/CIF, IBAN identifiers
"""

import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from app.services.falkordb_client import falkordb_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns -> claim_type mapping
# ---------------------------------------------------------------------------

_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Dates: dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy (2 or 4 digit year)
    (re.compile(r"\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})\b"), "temporal"),
    # Monetary: amount + currency
    (re.compile(r"\b(\d[\d.,]*\s*(?:EUR|euros?|USD))\b", re.IGNORECASE), "numeric"),
    # Monetary: currency symbol variants
    (re.compile(r"(\d[\d.,]*\s*[€$])"), "numeric"),
    (re.compile(r"([€$]\s*\d[\d.,]*)"), "numeric"),
    # Percentages
    (re.compile(r"\b(\d+[.,]?\d*\s*%)"), "numeric"),
    # BOE / Law references
    (re.compile(
        r"((?:BOE|Ley\s+Org[aá]nica|Ley|Real\s+Decreto[-\s]?Ley|Real\s+Decreto|RD|Orden)\s+[\w/\-]+)",
        re.IGNORECASE,
    ), "legal_reference"),
    # NIF/CIF
    (re.compile(r"\b([A-Z]\d{7}[A-Z0-9])\b"), "factual"),
    # IBAN
    (re.compile(r"\b([A-Z]{2}\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4})\b"), "factual"),
]

# Context window: characters before/after match to capture as source_chunk
_CONTEXT_CHARS = 100


class ClaimExtractor:
    """Extract structured Claims from document text.

    Two-stage extraction:
    1. Regex fast-path: dates, monetary amounts, BOE/law references, percentages, IDs
    2. Optional LLM: complex factual claims (disabled, placeholder for future)
    """

    async def extract_claims(
        self,
        tenant_id: str,
        document_id: str,
        text: str,
        domain: str = "",
        semantic_type: str = "",
    ) -> List[Dict[str, Any]]:
        """Extract claims and store them in FalkorDB.

        Returns list of created claims with their IDs.
        """
        if not text or not text.strip():
            return []

        await falkordb_client.initialize()

        # Step 1: Regex extraction
        raw_claims = self._extract_regex(text)
        if not raw_claims:
            return []

        logger.info(
            f"Extracted {len(raw_claims)} raw claims from document {document_id} "
            f"(tenant={tenant_id})"
        )

        # Step 2: Deduplicate by (statement, claim_type)
        seen: Set[Tuple[str, str]] = set()
        unique_claims: List[Dict[str, Any]] = []
        for claim in raw_claims:
            key = (claim["match_value"], claim["claim_type"])
            if key not in seen:
                seen.add(key)
                unique_claims.append(claim)

        # Step 3: Store claims in FalkorDB
        created = await self._store_claims(
            tenant_id, document_id, unique_claims, domain, semantic_type,
        )

        # Step 4: Detect contradictions with existing claims
        if created:
            await self._detect_contradictions(tenant_id, document_id)

        return created

    def _extract_regex(self, text: str) -> List[Dict[str, Any]]:
        """Extract claims using regex patterns.

        Returns list of raw claim dicts with match_value, claim_type,
        source_chunk, and char_offset.
        """
        results: List[Dict[str, Any]] = []
        text_len = len(text)

        for pattern, claim_type in _PATTERNS:
            for match in pattern.finditer(text):
                match_value = match.group(1) if match.lastindex else match.group(0)
                match_value = match_value.strip()

                if not match_value or len(match_value) < 2:
                    continue

                # Extract surrounding context
                start = max(0, match.start() - _CONTEXT_CHARS)
                end = min(text_len, match.end() + _CONTEXT_CHARS)
                source_chunk = text[start:end].strip()

                # Build statement from match + brief context
                statement = match_value

                results.append({
                    "match_value": match_value,
                    "claim_type": claim_type,
                    "statement": statement,
                    "source_chunk": source_chunk,
                    "char_offset": match.start(),
                })

        return results

    async def _store_claims(
        self,
        tenant_id: str,
        document_id: str,
        claims: List[Dict[str, Any]],
        domain: str,
        semantic_type: str,
    ) -> List[Dict[str, Any]]:
        """Create :Claim nodes with :EXTRACTED_FROM and :ABOUT edges."""
        created: List[Dict[str, Any]] = []

        for claim in claims:
            claim_id = str(uuid.uuid4())

            # Create Claim node + EXTRACTED_FROM edge to Document
            cypher = """
                MATCH (d:Document {tenant_id: $tenant_id, document_id: $document_id})
                CREATE (c:Claim {
                    claim_id: $claim_id,
                    tenant_id: $tenant_id,
                    statement: $statement,
                    claim_type: $claim_type,
                    confidence: $confidence,
                    source_chunk: $source_chunk,
                    verified: false,
                    created_at: timestamp()
                })
                CREATE (c)-[:EXTRACTED_FROM {
                    extraction_method: 'regex',
                    char_offset: $char_offset
                }]->(d)
                RETURN c.claim_id AS claim_id
            """
            # Regex claims get a baseline confidence based on type
            confidence = _claim_type_confidence(claim["claim_type"])

            params = {
                "tenant_id": tenant_id,
                "document_id": document_id,
                "claim_id": claim_id,
                "statement": claim["statement"],
                "claim_type": claim["claim_type"],
                "confidence": confidence,
                "source_chunk": claim["source_chunk"],
                "char_offset": claim["char_offset"],
            }

            try:
                rows = await falkordb_client.execute_cypher(cypher, params)
                if not rows:
                    # Document node may not exist yet — create claim without edge
                    logger.debug(
                        f"Document {document_id} not found in graph, "
                        f"creating standalone claim"
                    )
                    continue

                # Try to link ABOUT to entities mentioned in the same chunk
                await self._link_claim_to_entities(
                    tenant_id, claim_id, claim["source_chunk"],
                )

                created.append({
                    "claim_id": claim_id,
                    "statement": claim["statement"],
                    "claim_type": claim["claim_type"],
                    "confidence": confidence,
                })
            except Exception as e:
                logger.warning(
                    f"Failed to store claim '{claim['statement'][:50]}': {e}"
                )

        logger.info(
            f"Stored {len(created)}/{len(claims)} claims for document {document_id}"
        )
        return created

    async def _link_claim_to_entities(
        self,
        tenant_id: str,
        claim_id: str,
        source_chunk: str,
    ) -> None:
        """Create :ABOUT edges from a Claim to entities mentioned in its chunk."""
        if not source_chunk:
            return

        # Find entities whose name appears in the source chunk
        cypher = """
            MATCH (e:Entity)
            WHERE (e.tenant_id = $tenant_id OR e.shared = true)
              AND e.name IS NOT NULL
            WITH e
            WHERE $source_chunk CONTAINS e.name
            MATCH (c:Claim {claim_id: $claim_id, tenant_id: $tenant_id})
            MERGE (c)-[:ABOUT]->(e)
        """
        try:
            await falkordb_client.execute_cypher(cypher, {
                "tenant_id": tenant_id,
                "claim_id": claim_id,
                "source_chunk": source_chunk,
            })
        except Exception as e:
            logger.debug(f"Failed to link claim to entities: {e}")

    async def _detect_contradictions(
        self,
        tenant_id: str,
        document_id: str,
    ) -> None:
        """Detect contradictions between claims about the same entity.

        Simple regex-based comparison:
        - Two temporal claims about the same entity with different dates
        - Two numeric claims about the same entity with different amounts
        """
        # Find pairs of claims about the same entity with the same type
        # but from different documents (or different values in the same doc)
        cypher = """
            MATCH (c1:Claim {tenant_id: $tenant_id})-[:ABOUT]->(e:Entity)<-[:ABOUT]-(c2:Claim {tenant_id: $tenant_id})
            MATCH (c1)-[:EXTRACTED_FROM]->(d1:Document {document_id: $document_id})
            MATCH (c2)-[:EXTRACTED_FROM]->(d2:Document)
            WHERE c1.claim_type = c2.claim_type
              AND c1.claim_type IN ['temporal', 'numeric']
              AND c1.claim_id <> c2.claim_id
              AND c1.statement <> c2.statement
              AND NOT (c1)-[:CONTRADICTS]->(c2)
              AND NOT (c2)-[:CONTRADICTS]->(c1)
            RETURN c1.claim_id AS c1_id, c2.claim_id AS c2_id,
                   c1.claim_type AS claim_type,
                   c1.statement AS s1, c2.statement AS s2,
                   c1.confidence AS conf1, c2.confidence AS conf2
        """
        try:
            rows = await falkordb_client.execute_cypher(
                cypher, {"tenant_id": tenant_id, "document_id": document_id}
            )
        except Exception as e:
            logger.debug(f"Contradiction detection query failed: {e}")
            return

        if not rows:
            return

        # Create CONTRADICTS edges for detected contradictions
        created_count = 0
        seen_pairs: Set[Tuple[str, str]] = set()

        for row in rows:
            c1_id = row["c1_id"]
            c2_id = row["c2_id"]
            claim_type = row["claim_type"]

            # Normalize pair ordering to avoid duplicates
            pair = tuple(sorted([c1_id, c2_id]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            # Verify the values actually differ (not just formatting)
            s1 = row["s1"]
            s2 = row["s2"]
            if not _values_contradict(s1, s2, claim_type):
                continue

            # Higher confidence claim is the "source" of contradiction
            if (row.get("conf1") or 0) >= (row.get("conf2") or 0):
                src_id, tgt_id = c1_id, c2_id
            else:
                src_id, tgt_id = c2_id, c1_id

            contra_cypher = """
                MATCH (c1:Claim {claim_id: $src_id, tenant_id: $tenant_id})
                MATCH (c2:Claim {claim_id: $tgt_id, tenant_id: $tenant_id})
                MERGE (c1)-[:CONTRADICTS {contradiction_type: $contradiction_type}]->(c2)
            """
            try:
                await falkordb_client.execute_cypher(contra_cypher, {
                    "tenant_id": tenant_id,
                    "src_id": src_id,
                    "tgt_id": tgt_id,
                    "contradiction_type": claim_type,
                })
                created_count += 1
            except Exception as e:
                logger.debug(f"Failed to create contradiction edge: {e}")

        if created_count:
            logger.info(
                f"Detected {created_count} contradictions for document {document_id}"
            )


def _claim_type_confidence(claim_type: str) -> float:
    """Baseline confidence by claim type for regex extraction."""
    return {
        "temporal": 0.85,
        "numeric": 0.90,
        "legal_reference": 0.95,
        "factual": 0.90,
    }.get(claim_type, 0.80)


def _values_contradict(s1: str, s2: str, claim_type: str) -> bool:
    """Check if two claim statements actually contradict each other.

    Simple normalization-based comparison — not LLM.
    """
    # Normalize: remove whitespace, lowercase
    n1 = re.sub(r"\s+", "", s1.lower())
    n2 = re.sub(r"\s+", "", s2.lower())

    # If normalized values are equal, no contradiction
    if n1 == n2:
        return False

    if claim_type == "temporal":
        # Extract date components and compare
        d1 = _extract_date_parts(s1)
        d2 = _extract_date_parts(s2)
        if d1 and d2 and d1 != d2:
            return True

    elif claim_type == "numeric":
        # Extract numeric values and compare
        v1 = _extract_numeric_value(s1)
        v2 = _extract_numeric_value(s2)
        if v1 is not None and v2 is not None and v1 != v2:
            return True

    return False


def _extract_date_parts(text: str) -> Optional[Tuple[int, ...]]:
    """Extract (day, month, year) from a date string."""
    m = re.search(r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})", text)
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if year < 100:
        year += 2000
    return (day, month, year)


def _extract_numeric_value(text: str) -> Optional[float]:
    """Extract a numeric value from text, normalizing decimal separators."""
    # Remove currency symbols and words
    cleaned = re.sub(r"[€$]", "", text)
    cleaned = re.sub(r"\b(EUR|euros?|USD)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"%", "", cleaned)
    cleaned = cleaned.strip()

    # Handle European format: 45.000,50 -> 45000.50
    if "," in cleaned and "." in cleaned:
        # Determine which is thousands separator vs decimal
        if cleaned.rindex(".") < cleaned.rindex(","):
            # 45.000,50 format
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # 45,000.50 format
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Could be decimal comma (45,50) or thousands (45,000)
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")

    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


# Module-level singleton
claim_extractor = ClaimExtractor()
