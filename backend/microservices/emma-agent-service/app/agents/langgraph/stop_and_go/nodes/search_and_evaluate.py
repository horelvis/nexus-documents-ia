"""
Search & Evaluate node — shared evidence search + strategy-specific evaluation.

This node:
1. Searches for evidence (Weaviate + uploads + DOI validation + web) — shared logic
2. Calls strategy.evaluate_item() — mode-specific evaluation
3. Routes accepted/rejected/corrected items via strategy callbacks
4. Collects source references for the final result

The _search_evidence() function is extracted from the identical code
previously duplicated in both services.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.agents.langgraph.stop_and_go.strategy import get_strategy

logger = logging.getLogger(__name__)

# Shared DOI regex — matches standard DOIs per ISO 26324.
# Stops at whitespace, commas, semicolons, brackets, parens, braces.
# Imported by initialize.py for source-document DOI extraction.
DOI_PATTERN = re.compile(r'10\.\d{4,9}/[^\s,;\])}\n]+')


async def search_and_evaluate_node(state: dict) -> dict:
    """Search for evidence, evaluate item, route to accept/reject."""
    strategy = get_strategy(state["mode"])
    item = state.get("current_item")

    # If current_item is None (e.g., duplicate was skipped), pass through
    if item is None:
        return {}

    # Emit verification-started event
    verification_event = {
        "event_type": f"{state['mode']}_verification_started",
        "item_id": item.get("id"),
        "data": {"message": "Searching for supporting documents..."},
    }

    try:
        # Shared: search for evidence (split into source vs external)
        evidence_by_tier = await _search_evidence(
            query_text=item.get("text", ""),
            tenant_id=state["tenant_id"],
            collections=state.get("collections", []),
            uploaded_texts=state.get("uploaded_texts", []),
            mode_config=state.get("mode_config", {}),
            jurisprudence_evidence=state.get("jurisprudence_evidence", []),
            source_document_ids=state.get("source_document_ids", []),
            source_doi_validations=state.get("source_doi_validations", []),
        )

        # Flatten for backwards-compatible source collection
        all_evidence = evidence_by_tier.get("source", []) + evidence_by_tier.get("external", [])

        # Strategy-specific: evaluate item against tiered evidence
        evaluation = await strategy.evaluate_item(item, evidence_by_tier, state)
        status = evaluation.get("status", "rejected")

        events = [verification_event]
        all_items = list(state.get("all_extracted_items", []))
        all_items.append(item)

        updates: Dict[str, Any] = {"all_extracted_items": all_items}

        if status == "accepted":
            event_data = await strategy.on_accepted(item, evaluation, state)
            updates["items_accepted"] = state.get("items_accepted", 0) + 1
            events.append(event_data)
        elif status == "corrected":
            event_data = await strategy.on_accepted(item, evaluation, state)
            updates["items_corrected"] = state.get("items_corrected", 0) + 1
            events.append(event_data)
        else:
            event_data = await strategy.on_rejected(item, evaluation, state)
            updates["items_rejected"] = state.get("items_rejected", 0) + 1
            events.append(event_data)

        # Collect EXTERNAL sources for final result (exclude source documents)
        sources_map = dict(state.get("sources_map", {}))
        for e in all_evidence:
            src_id = e.get("document_id", "")
            src_type = e.get("source", "internal")
            if src_id and src_id not in sources_map and src_type not in ("uploaded", "source_document"):
                source_entry = {
                    "id": src_id,
                    "title": e.get("document_title", ""),
                    "source": e.get("source", "internal"),
                    "url": e.get("url", ""),
                }
                # Include CENDOJ metadata for jurisprudence sources
                if e.get("source") == "jurisprudence":
                    source_entry.update({
                        "roj": e.get("roj", ""),
                        "ecli": e.get("ecli", ""),
                        "date": e.get("date", ""),
                        "resolution_type": e.get("resolution_type", ""),
                        "ponente": e.get("ponente", ""),
                    })
                sources_map[src_id] = source_entry
        updates["sources_map"] = sources_map
        updates["pending_events"] = events
        return updates

    except asyncio.TimeoutError:
        logger.warning(f"Verification timeout for item {item.get('id')}")
        return {
            "all_extracted_items": list(state.get("all_extracted_items", [])) + [item],
            "pending_events": [verification_event, {
                "event_type": f"{state['mode']}_verification_timeout",
                "item_id": item.get("id"),
                "data": {"message": "Verification timed out, skipping item"},
            }],
        }

    except Exception as e:
        import traceback
        logger.error(f"Verification failed: {e}\n{traceback.format_exc()}")
        return {
            "all_extracted_items": list(state.get("all_extracted_items", [])) + [item],
            "items_rejected": state.get("items_rejected", 0) + 1,
            "pending_events": [verification_event, {
                "event_type": "error",
                "item_id": item.get("id"),
                "data": {"error": f"Verification failed: {str(e)}"},
            }],
        }


async def _validate_single_doi(doi: str) -> Dict[str, Any]:
    """Validate a single DOI via CrossRef API + doi.org fallback.

    Two-phase approach:
    1. CrossRef API (primary) — returns existence + metadata in one call.
       Polite pool via mailto header.  Handles ~50 req/s.
    2. doi.org REST API (/api/handles/) — fallback ONLY when CrossRef has
       a network error.  Confirms existence without metadata.

    Returns a dict with:
    - doi: the DOI string
    - valid: True if DOI resolves to a real publication
    - metadata: {title, authors, year, journal, type} if valid
    """
    result: Dict[str, Any] = {"doi": doi, "valid": False, "metadata": {}}

    # Phase 1: CrossRef API — existence + metadata in one call
    crossref_error = False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"https://api.crossref.org/works/{doi}",
                headers={"User-Agent": "NouxCubeIA/1.0 (mailto:support@nouxcube.com)"},
            )
            if response.status_code == 200:
                meta = response.json().get("message", {})
                result["valid"] = True
                result["metadata"] = {
                    "title": meta.get("title", [""])[0] if meta.get("title") else "",
                    "authors": [
                        f"{a.get('given', '')} {a.get('family', '')}".strip()
                        for a in meta.get("author", [])
                    ],
                    "year": str(
                        meta.get("issued", {}).get("date-parts", [[""]])[0][0]
                    ) if meta.get("issued") else "",
                    "journal": (
                        meta.get("container-title", [""])[0]
                        if meta.get("container-title") else ""
                    ),
                    "type": meta.get("type", ""),
                }
                logger.info(f"DOI {doi}: valid (CrossRef)")
                return result
            elif response.status_code == 404:
                logger.info(f"DOI {doi}: not found (CrossRef 404)")
            else:
                logger.warning(f"DOI {doi}: CrossRef unexpected HTTP {response.status_code}")
                crossref_error = True
    except Exception as e:
        logger.warning(f"DOI {doi}: CrossRef network error: {e}")
        crossref_error = True

    # Phase 2: doi.org REST API — fallback only on CrossRef network error
    if crossref_error:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"https://doi.org/api/handles/{doi}")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("responseCode") == 1:
                        result["valid"] = True
                        logger.info(f"DOI {doi}: valid (doi.org fallback, no metadata)")
                    else:
                        logger.info(f"DOI {doi}: not found (doi.org rc={data.get('responseCode')})")
                elif response.status_code == 404:
                    logger.info(f"DOI {doi}: not found (doi.org 404)")
        except Exception as e:
            logger.warning(f"DOI {doi}: doi.org fallback also failed: {e}")

    return result


async def _search_crossref_citation(
    title_query: str,
    author: str = "",
    year: str = "",
) -> Dict[str, Any]:
    """Search CrossRef for a citation by title + optional author/year.

    Used to verify citations that DON'T have a DOI — searches by
    bibliographic query (title + author + year combined).

    CrossRef API: no auth required, 50 req/s with mailto polite pool.

    Returns:
        {"found": bool, "confidence": 0.0-1.0, "metadata": {...}, "doi": str|None}
    """
    result: Dict[str, Any] = {"found": False, "confidence": 0.0, "metadata": {}, "doi": None}

    # Build bibliographic query
    parts = [title_query]
    if author:
        parts.append(author)
    if year:
        parts.append(year)
    bib_query = " ".join(parts)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.crossref.org/works",
                params={
                    "query.bibliographic": bib_query,
                    "rows": 3,
                    "mailto": "verificacion@nouxcube.com",
                },
            )
            if response.status_code != 200:
                return result

            data = response.json()
            items = data.get("message", {}).get("items", [])
            if not items:
                return result

            # Score the top result
            top = items[0]
            top_title = (top.get("title", [""])[0] or "").lower()
            top_authors = [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in top.get("author", [])
            ]
            top_year = ""
            for date_field in ("published-online", "published-print", "issued", "created"):
                dp = top.get(date_field, {}).get("date-parts", [[]])
                if dp and dp[0]:
                    top_year = str(dp[0][0])
                    break

            # Calculate confidence: title similarity + author match + year match
            confidence = 0.0

            # Title similarity (50% weight) — simple word overlap
            query_words = set(title_query.lower().split())
            title_words = set(top_title.split())
            if query_words and title_words:
                overlap = len(query_words & title_words) / max(len(query_words), 1)
                confidence += overlap * 0.50

            # Author match (30% weight)
            if author:
                author_key = author.split()[0].lower()
                author_match = any(author_key in a.lower() for a in top_authors)
                if author_match:
                    confidence += 0.30

            # Year match (20% weight)
            if year and top_year == year:
                confidence += 0.20

            result["confidence"] = round(confidence, 3)
            result["metadata"] = {
                "title": top.get("title", [""])[0] or "",
                "authors": top_authors,
                "year": top_year,
                "journal": (top.get("container-title", [""])[0] or "") if top.get("container-title") else "",
                "type": top.get("type", ""),
            }
            result["doi"] = top.get("DOI")
            result["found"] = confidence >= 0.65

    except Exception as e:
        logger.debug(f"CrossRef search failed for '{bib_query[:60]}': {e}")

    return result


async def _extract_and_validate_dois(claim_text: str) -> List[Dict[str, Any]]:
    """Extract DOIs from claim text and validate them in parallel.

    Returns list of validation results, each containing:
    - doi, valid, metadata (if valid)
    """
    dois = list(set(DOI_PATTERN.findall(claim_text)))
    if not dois:
        return []

    # Clean trailing punctuation from DOIs
    cleaned_dois = []
    for doi in dois:
        doi = doi.rstrip(".")
        cleaned_dois.append(doi)

    logger.info(f"DOI validation: found {len(cleaned_dois)} DOIs in claim text")

    results = await asyncio.gather(
        *[_validate_single_doi(doi) for doi in cleaned_dois],
        return_exceptions=True,
    )

    validated = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning(f"DOI validation exception: {r}")
            continue
        validated.append(r)

    valid_count = sum(1 for v in validated if v.get("valid"))
    invalid_count = len(validated) - valid_count
    logger.info(f"DOI validation results: {valid_count} valid, {invalid_count} invalid")

    return validated


# Pattern to extract "Author et al., 2025" or "Author & Other, 2020" from claim text
_CITATION_PATTERN = re.compile(
    r'([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:et\s+al\.|&\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+))?),?\s*\(?(\d{4})\)?'
)


async def _cross_reference_source_dois(
    claim_text: str,
    source_doi_validations: List[Dict],
    external_evidence: List[Dict],
) -> None:
    """Match citations in claim text against pre-validated DOIs from the source doc.

    Three verification levels:
    1. DOI invalid → negative evidence (source has a broken reference)
    2. DOI valid but metadata mismatch → negative evidence (DOI exists but
       points to a DIFFERENT paper than what the source document claims)
    3. DOI valid and metadata matches → positive evidence

    For citations that don't match any source DOI, searches CrossRef to
    verify the publication exists (covers papers without DOIs and catches
    fabricated references).

    Modifies external_evidence in place.
    """
    # Already-added DOIs (from direct claim text extraction)
    existing_dois = {e.get("document_id", "").replace("doi:", "").replace("doi_invalid:", "")
                     for e in external_evidence if "doi" in e.get("document_id", "")}

    # Extract citations from claim text
    citations = _CITATION_PATTERN.findall(claim_text)
    if not citations:
        return

    matched_citations = set()  # Track which citations found a DOI match

    for author, year in citations:
        # Normalize: "Hosseini et al." → "Hosseini"
        author_key = author.split()[0].lower()
        citation_key = f"{author_key}_{year}"

        for dv in source_doi_validations:
            doi = dv.get("doi", "")
            if doi in existing_dois:
                continue

            # Check if DOI context matches this citation
            ctx = (dv.get("context", "") or "").lower()
            meta = dv.get("metadata", {})

            # Match by context text (author + year near the DOI in source doc)
            ctx_match = author_key in ctx and year in ctx

            if not ctx_match:
                continue

            existing_dois.add(doi)
            matched_citations.add(citation_key)

            if not dv.get("valid"):
                # Level 1: DOI doesn't resolve at all
                external_evidence.append({
                    "document_id": f"doi_invalid:{doi}",
                    "document_title": f"DOI no válido en documento fuente: {doi}",
                    "chunk_id": None,
                    "text_excerpt": (
                        f"El documento fuente cita {author} ({year}) con DOI {doi}, "
                        f"pero este DOI no existe o no se puede resolver. "
                        f"Contexto: «{dv.get('context', '')}»"
                    ),
                    "similarity_score": 0.0,
                    "source": "doi_invalid",
                    "url": "",
                })
                logger.info(f"DOI cross-ref: invalid DOI {doi} for {author} ({year})")
            elif meta:
                # Level 2/3: DOI resolves — check metadata coherence
                meta_authors = " ".join(meta.get("authors", [])).lower()
                meta_year = str(meta.get("year", ""))

                author_matches = author_key in meta_authors
                year_matches = year == meta_year

                if author_matches and year_matches:
                    # Level 3: DOI valid + metadata matches → positive
                    title = meta.get("title", doi)
                    authors_str = ", ".join(meta.get("authors", [])[:3])
                    external_evidence.append({
                        "document_id": f"doi:{doi}",
                        "document_title": f"{title} ({authors_str}, {year})" if authors_str else title,
                        "chunk_id": None,
                        "text_excerpt": (
                            f"DOI {doi} verificado. La cita {author} ({year}) coincide con "
                            f"los metadatos: {title}. Autores: {authors_str}."
                        ),
                        "similarity_score": 0.90,
                        "source": "doi",
                        "url": f"https://doi.org/{doi}",
                        "doi_metadata": meta,
                    })
                else:
                    # Level 2: DOI valid but points to DIFFERENT paper
                    real_title = meta.get("title", "?")
                    real_authors = ", ".join(meta.get("authors", [])[:3])
                    mismatch_parts = []
                    if not author_matches:
                        mismatch_parts.append(
                            f"autores reales: {real_authors} (no '{author}')"
                        )
                    if not year_matches:
                        mismatch_parts.append(
                            f"año real: {meta_year} (no {year})"
                        )
                    external_evidence.append({
                        "document_id": f"doi_mismatch:{doi}",
                        "document_title": f"DOI no corresponde: {doi}",
                        "chunk_id": None,
                        "text_excerpt": (
                            f"El documento fuente cita {author} ({year}) con DOI {doi}, "
                            f"pero este DOI pertenece a OTRA publicación: «{real_title}» "
                            f"({'; '.join(mismatch_parts)}). "
                            f"El DOI existe pero no corresponde a la referencia citada."
                        ),
                        "similarity_score": 0.0,
                        "source": "doi_mismatch",
                        "url": f"https://doi.org/{doi}",
                        "doi_metadata": meta,
                    })
                    logger.info(
                        f"DOI cross-ref: mismatch DOI {doi} for {author} ({year}) "
                        f"→ actual: {real_title} ({meta_year})"
                    )
            break  # One DOI per citation

    # --- CrossRef fallback for unmatched citations ---
    # Citations in the claim that didn't match any source DOI are verified
    # via CrossRef bibliographic search (covers papers without DOIs and
    # catches fabricated references).
    unmatched = [
        (a, y) for a, y in citations
        if f"{a.split()[0].lower()}_{y}" not in matched_citations
    ]
    if unmatched and len(unmatched) <= 3:
        crossref_tasks = []
        for author, year in unmatched:
            # Build a short title hint from the claim text around the citation
            crossref_tasks.append(
                _search_crossref_citation(
                    title_query=claim_text[:120],
                    author=author.split()[0],
                    year=year,
                )
            )
        crossref_results = await asyncio.gather(*crossref_tasks, return_exceptions=True)

        for (author, year), cr in zip(unmatched, crossref_results):
            if isinstance(cr, Exception):
                continue
            if cr.get("found") and cr.get("doi"):
                cr_meta = cr.get("metadata", {})
                title = cr_meta.get("title", "")
                authors_str = ", ".join(cr_meta.get("authors", [])[:3])
                external_evidence.append({
                    "document_id": f"doi:{cr['doi']}",
                    "document_title": f"{title} ({authors_str}, {year})" if authors_str else title,
                    "chunk_id": None,
                    "text_excerpt": (
                        f"Cita {author} ({year}) verificada vía CrossRef. "
                        f"Publicación encontrada: {title}. DOI: {cr['doi']}. "
                        f"Confianza: {cr['confidence']:.0%}"
                    ),
                    "similarity_score": round(cr["confidence"], 3),
                    "source": "crossref",
                    "url": f"https://doi.org/{cr['doi']}",
                    "doi_metadata": cr_meta,
                })
            elif not cr.get("found"):
                external_evidence.append({
                    "document_id": f"citation_unverified:{author}_{year}",
                    "document_title": f"Cita no verificable: {author} ({year})",
                    "chunk_id": None,
                    "text_excerpt": (
                        f"La cita {author} ({year}) no se ha encontrado en CrossRef. "
                        f"Puede ser una referencia incorrecta, un preprint no indexado, "
                        f"o una publicación en un idioma/formato no cubierto."
                    ),
                    "similarity_score": 0.0,
                    "source": "citation_unverified",
                    "url": "",
                })


async def _search_evidence(
    query_text: str,
    tenant_id: str,
    collections: List[str],
    uploaded_texts: List[Dict],
    mode_config: Dict[str, Any],
    jurisprudence_evidence: Optional[List[Dict]] = None,
    source_document_ids: Optional[List[str]] = None,
    source_doi_validations: Optional[List[Dict]] = None,
) -> Dict[str, List[Dict]]:
    """
    Unified evidence search with two-tier separation.

    Returns {"source": [...], "external": [...]} where:
    - "source": Evidence from the same documents used to generate claims
      (uploaded docs matched via RLM). Used for faithfulness checking.
    - "external": Independent evidence from Weaviate (excluding source docs),
      DOI validation, jurisprudence, and web search. Used for corroboration.

    The separation prevents circular verification: claims generated FROM a
    document should not be "verified" AGAINST the same document without
    honest labeling. See SAFE (Google DeepMind, 2024) for the principle.
    """
    similarity_threshold = settings.predictive_similarity_threshold
    source_evidence: List[Dict] = []
    external_evidence: List[Dict] = []
    source_ids_set = set(source_document_ids or [])

    # --- Uploaded documents (RLM-powered filtering) → always "source" tier ---
    if uploaded_texts:
        try:
            from app.services.verified_generation.service import _rlm_filter_evidence
            source_evidence = await _rlm_filter_evidence(
                query_text, uploaded_texts, max_evidence=5
            )
        except Exception as e:
            logger.warning(f"RLM evidence filtering failed: {e}")

    # --- Weaviate search → split by source_document_ids ---
    sanitized_tenant = tenant_id.replace("-", "_")
    safe_tenant = ''.join(c for c in tenant_id if c.isalnum())[:32]
    candidate_collections = (
        [collections[0]] if collections
        else [
            f"Nouxcube_{sanitized_tenant}_documents",
            f"Nouxcube_{safe_tenant}_knowledge",
        ]
    )

    weaviate_found = False
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for collection_name in candidate_collections:
                response = await client.post(
                    f"{settings.weaviate_service_url}/weaviate/collections/{collection_name}/search",
                    headers={
                        "Content-Type": "application/json",
                        "X-API-Key": settings.MICROSERVICES_API_KEY,
                    },
                    json={
                        "query": query_text,
                        "tenant_id": tenant_id,
                        "limit": 10,  # Fetch more to compensate for filtering
                        "search_type": "hybrid",
                        "is_admin": True,
                    },
                )
                if response.status_code == 200:
                    results = response.json().get("results", [])
                    for r in results:
                        distance = r.get("distance", 1.0)
                        similarity = 1.0 - min(distance, 1.0)
                        if similarity >= similarity_threshold:
                            doc_id = r.get("document_id", "")
                            entry = {
                                "document_id": doc_id,
                                "document_title": r.get("title", ""),
                                "chunk_id": r.get("chunk_id"),
                                "text_excerpt": r.get("content", "")[:settings.predictive_evidence_excerpt_limit],
                                "similarity_score": round(similarity, 3),
                                "source": "internal",
                            }
                            # Classify: is this from a source document or independent?
                            if doc_id and doc_id in source_ids_set:
                                source_evidence.append(entry)
                            else:
                                external_evidence.append(entry)
                                weaviate_found = True
                    if weaviate_found:
                        break
    except Exception as e:
        logger.error(f"Weaviate evidence search failed: {e}")

    # --- DOI validation from claim text (always: external tier) ---
    doi_results = await _extract_and_validate_dois(query_text)
    for doi_result in doi_results:
        doi = doi_result["doi"]
        if doi_result["valid"]:
            meta = doi_result.get("metadata", {})
            title = meta.get("title", doi)
            authors = ", ".join(meta.get("authors", [])[:3])
            year = meta.get("year", "")
            external_evidence.append({
                "document_id": f"doi:{doi}",
                "document_title": f"{title} ({authors}, {year})" if authors else title,
                "chunk_id": None,
                "text_excerpt": f"DOI {doi} verificado. Título: {title}. Autores: {authors}. Año: {year}.",
                "similarity_score": 0.95,
                "source": "doi",
                "url": f"https://doi.org/{doi}",
                "doi_metadata": meta,
            })
        else:
            external_evidence.append({
                "document_id": f"doi_invalid:{doi}",
                "document_title": f"DOI no válido: {doi}",
                "chunk_id": None,
                "text_excerpt": f"El DOI {doi} no se ha podido resolver. No existe ninguna publicación registrada con este identificador.",
                "similarity_score": 0.0,
                "source": "doi_invalid",
                "url": "",
            })

    # --- Cross-reference DOIs from source document (pre-validated at init) ---
    # If the claim cites an author/year that matches a DOI context from the
    # source document, include the DOI validation result as external evidence.
    # This catches invalid DOIs that the claim text doesn't contain directly.
    if source_doi_validations:
        await _cross_reference_source_dois(
            query_text, source_doi_validations, external_evidence
        )

    # --- Jurisprudence (CENDOJ, cached from initialization → external) ---
    # Gate on external evidence only — source evidence should NOT prevent
    # external searches (that would re-enable circular verification)
    if jurisprudence_evidence and len(external_evidence) < 5:
        for jur in jurisprudence_evidence:
            external_evidence.append({
                "document_id": jur.get("document_id", ""),
                "document_title": jur.get("document_title", ""),
                "chunk_id": jur.get("chunk_id"),
                "text_excerpt": jur.get("text_excerpt", "")[:settings.predictive_evidence_excerpt_limit],
                "similarity_score": jur.get("similarity_score", 0.80),
                "source": "jurisprudence",
                "url": jur.get("url", ""),
                "roj": jur.get("roj", ""),
                "ecli": jur.get("ecli", ""),
                "date": jur.get("date", ""),
                "resolution_type": jur.get("resolution_type", ""),
                "ponente": jur.get("ponente", ""),
            })
        logger.info(f"Added {len(jurisprudence_evidence)} jurisprudence evidence items")

    # --- Web search (supplementary → external) ---
    # Gate on external evidence only — source evidence should NOT prevent web search
    verification_sources = mode_config.get("verification_sources", [])
    web_enabled = settings.web_search_enabled or "web" in verification_sources
    if web_enabled and len(external_evidence) < 5:
        try:
            from app.services.web_search import get_web_search_client
            web_client = get_web_search_client()
            web_results = await asyncio.wait_for(
                web_client.search(query_text, max_results=3),
                timeout=10.0,
            )
            for wr in web_results:
                url_hash = hashlib.md5(wr.url.encode()).hexdigest()[:12]
                external_evidence.append({
                    "document_id": f"web:{url_hash}",
                    "document_title": wr.title,
                    "chunk_id": None,
                    "text_excerpt": wr.snippet[:settings.predictive_evidence_excerpt_limit],
                    "similarity_score": 0.65,
                    "source": "web",
                    "url": wr.url,
                })
        except asyncio.TimeoutError:
            logger.warning("Web search timed out")
        except Exception as e:
            logger.warning(f"Web search failed (non-fatal): {e}")

    # Cap external evidence — diminishing returns beyond 5 items and
    # longer context hurts LLM attention in the verification prompt.
    MAX_EXTERNAL = 5
    if len(external_evidence) > MAX_EXTERNAL:
        # Prioritize by similarity score (DOI/crossref have fixed scores)
        external_evidence.sort(key=lambda e: e.get("similarity_score", 0), reverse=True)
        external_evidence = external_evidence[:MAX_EXTERNAL]

    logger.info(
        f"Evidence for '{query_text[:60]}...': "
        f"{len(source_evidence)} source, {len(external_evidence)} external"
    )
    return {"source": source_evidence, "external": external_evidence}
