"""
Legal Links API — extract legal references from document text and create
REFERENCES_LAW edges in FalkorDB.

Detects mentions of Spanish laws (BOE identifiers, common abbreviations like
ET, LGT, LISOS, etc.) via regex, then links the Document node to matching
Law nodes in the graph via REFERENCES_LAW edges.
"""
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import verify_api_key
from app.services.falkordb_client import falkordb_client

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Known Spanish law abbreviations → BOE ID mapping ──
_LAW_ABBREVIATIONS: Dict[str, str] = {
    # Laboral
    "estatuto de los trabajadores": "BOE-A-2015-11430",
    "et": "BOE-A-2015-11430",
    "ley de prevención de riesgos laborales": "BOE-A-1995-24292",
    "lprl": "BOE-A-1995-24292",
    "lisos": "BOE-A-2000-15060",
    "lgss": "BOE-A-2015-11724",
    "leta": "BOE-A-2007-13409",
    # Fiscal
    "ley general tributaria": "BOE-A-2003-23186",
    "lgt": "BOE-A-2003-23186",
    "lirpf": "BOE-A-2006-20764",
    "lis": "BOE-A-2014-12328",
    "liva": "BOE-A-1992-28740",
    # Civil
    "código civil": "BOE-A-1889-4763",
    "ley de enjuiciamiento civil": "BOE-A-2000-323",
    "lec": "BOE-A-2000-323",
    # Mercantil
    "ley de sociedades de capital": "BOE-A-2010-10544",
    "lsc": "BOE-A-2010-10544",
    # Compliance
    "lopdgdd": "BOE-A-2018-16673",
    "ley orgánica de protección de datos": "BOE-A-2018-16673",
    "código penal": "BOE-A-1995-25444",
    # Administrativo
    "lpacap": "BOE-A-2015-10565",
    "lrjsp": "BOE-A-2015-10566",
    # Consumidores
    "lgdcu": "BOE-A-2007-20555",
    # Inmobiliario
    "lau": "BOE-A-1994-26003",
    "lph": "BOE-A-1960-10906",
}

# Regex for BOE IDs in text (e.g., "BOE-A-2015-11430")
_BOE_ID_RE = re.compile(r"\bBOE-[A-Z]-\d{4}-\d+\b")

# Regex for article references (e.g., "artículo 52 del ET", "art. 1.1 LEC")
_ART_REF_RE = re.compile(
    r"(?:art(?:ículo)?\.?\s*)(\d+(?:\.\d+)?)\s+(?:del?\s+)?("
    + "|".join(re.escape(k) for k in _LAW_ABBREVIATIONS if len(k) <= 10)
    + r")\b",
    re.IGNORECASE,
)

# Regex for law name mentions
_LAW_NAME_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _LAW_ABBREVIATIONS if len(k) > 4) + r")\b",
    re.IGNORECASE,
)


def _extract_legal_refs(text: str) -> List[Dict[str, Any]]:
    """Extract legal references from text using regex patterns."""
    refs: List[Dict[str, Any]] = []
    seen_boe: set = set()

    # 1. Direct BOE IDs
    for m in _BOE_ID_RE.finditer(text):
        boe_id = m.group(0)
        if boe_id not in seen_boe:
            seen_boe.add(boe_id)
            refs.append({"boe_id": boe_id, "source": "direct", "article": None})

    # 2. Article references (e.g., "art. 52 ET")
    for m in _ART_REF_RE.finditer(text):
        article = m.group(1)
        abbrev = m.group(2).lower().strip()
        boe_id = _LAW_ABBREVIATIONS.get(abbrev)
        if boe_id and boe_id not in seen_boe:
            seen_boe.add(boe_id)
            refs.append({"boe_id": boe_id, "source": "article_ref", "article": article})
        elif boe_id:
            # Update article for already-found law
            for ref in refs:
                if ref["boe_id"] == boe_id and not ref["article"]:
                    ref["article"] = article
                    break

    # 3. Law name mentions
    for m in _LAW_NAME_RE.finditer(text):
        name = m.group(1).lower().strip()
        boe_id = _LAW_ABBREVIATIONS.get(name)
        if boe_id and boe_id not in seen_boe:
            seen_boe.add(boe_id)
            refs.append({"boe_id": boe_id, "source": "name_mention", "article": None})

    return refs


# ── Pydantic models ──

class ExtractAndStoreRequest(BaseModel):
    tenant_id: str = Field(..., description="Tenant identifier")
    document_id: str = Field(..., description="Document identifier")
    text_sample: str = Field(..., description="Document text (up to 2000 chars)")
    semantic_type: str = Field("", description="Document semantic type")
    domain: str = Field("", description="Document domain")


class LegalLinkResult(BaseModel):
    success: bool
    references_found: int = 0
    edges_created: int = 0
    references: List[Dict[str, Any]] = Field(default_factory=list)


# ── Endpoint ──

@router.post("/extract-and-store", response_model=LegalLinkResult)
async def extract_and_store_legal(
    request: ExtractAndStoreRequest,
    _: bool = Depends(verify_api_key),
):
    """
    Extract legal references from document text and create REFERENCES_LAW
    edges to matching Law nodes in the FalkorDB graph.
    """
    await falkordb_client.initialize()

    refs = _extract_legal_refs(request.text_sample)
    if not refs:
        return LegalLinkResult(success=True, references_found=0, edges_created=0)

    edges_created = 0

    for ref in refs:
        try:
            props: Dict[str, Any] = {
                "tenant_id": request.tenant_id,
                "document_id": request.document_id,
                "boe_id": ref["boe_id"],
            }
            set_parts = ["r.source = 'auto_extract'"]
            if ref.get("article"):
                props["article"] = ref["article"]
                set_parts.append("r.article = $article")

            set_stmt = "SET " + ", ".join(set_parts)

            await falkordb_client.execute_cypher(
                f"""
                MATCH (d:Document {{tenant_id: $tenant_id, document_id: $document_id}})
                MATCH (l:Law {{boe_id: $boe_id}})
                MERGE (d)-[r:REFERENCES_LAW]->(l)
                {set_stmt}
                """,
                props,
            )
            edges_created += 1
        except Exception as e:
            logger.debug(f"Could not link {request.document_id} → {ref['boe_id']}: {e}")

    logger.info(
        f"Legal links: {request.document_id} → {edges_created}/{len(refs)} references "
        f"(domain={request.domain}, type={request.semantic_type})"
    )

    return LegalLinkResult(
        success=True,
        references_found=len(refs),
        edges_created=edges_created,
        references=refs,
    )
