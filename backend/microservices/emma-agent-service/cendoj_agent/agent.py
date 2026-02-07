"""
CENDOJ Reference Agent — Ephemeral Browser Search

Runs inside a Docker container with Playwright (headless Chromium).
Navigates CENDOJ's search form like a human, extracts references
from search results, and outputs structured JSON to stdout.

The container is destroyed after each run — nothing persists.

With --with-content N, the agent also downloads PDFs for the top N
results, extracts text in memory (PyPDF2), and includes legal_grounds
+ ruling sections in the JSON output. This text is used as ephemeral
LLM context — never stored in any database.

Architecture:
    Docker container starts → Playwright opens Chromium → navigates CENDOJ →
    fills search form → submits → extracts references from results page →
    [optional: httpx downloads top N PDFs → PyPDF2 extracts text in memory] →
    outputs JSON to stdout → container exits and is removed

Usage (inside container):
    python agent.py --query "despido improcedente" --court TS --max-results 10
    python agent.py --query "blanqueo capitales" --court AN --max-results 5
    python agent.py --query "acoso escolar" --court TS --with-content 3

Output: JSON array of references to stdout, logs to stderr.
"""

import argparse
import asyncio
import io
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,  # Logs to stderr, results to stdout
)
logger = logging.getLogger(__name__)

CENDOJ_BASE_URL = "https://www.poderjudicial.es/search"
CENDOJ_SEARCH_URL = f"{CENDOJ_BASE_URL}/indexAN.jsp"

# PDF download URL (validated — works without CAPTCHA or cookies)
PDF_URL_TEMPLATE = (
    "{base}/contenidos.action"
    "?action=accessToPDF"
    "&publicinterface=true"
    "&tab={db}"
    "&reference={reference}"
    "&encode=true"
    "&optimize={optimize}"
    "&databasematch={db}"
)

# TIPOORGANOPUB select values for each court
# (indexAN.jsp uses databasematch="AN" for ALL courts — "AN" is the database, not the court)
# Court filtering is done via the TIPOORGANOPUB multiselect dropdown
COURT_ORGAN_VALUES = {
    "TS": "11|12|13|14|15|16",                       # Tribunal Supremo (all salas)
    "AN": "22|2264|23|24|25|26|27|28|29",             # Audiencia Nacional (all salas)
    "TSJ": "31|31201202|33|34",                       # Tribunal Superior de Justicia
    "AP": "37|38",                                     # Audiencia Provincial
}

# Section markers for splitting sentence text
SECTION_PATTERNS = {
    "facts": re.compile(
        r'(?:ANTECEDENTES\s+DE\s+HECHO|RESULTANDO|HECHOS\s+PROBADOS)',
        re.IGNORECASE,
    ),
    "legal_grounds": re.compile(
        r'(?:FUNDAMENTOS\s+DE\s+DERECHO|CONSIDERANDO|RAZONAMIENTOS\s+JUR[IÍ]DICOS)',
        re.IGNORECASE,
    ),
    "ruling": re.compile(
        r'(?:FALL[OA]MOS|PARTE\s+DISPOSITIVA)',
        re.IGNORECASE,
    ),
}

# Rate limit between PDF downloads (seconds)
PDF_DOWNLOAD_DELAY = 2.0


@dataclass
class SentenceReference:
    """A reference to a CENDOJ sentence — metadata only, no full text stored."""
    roj: str = ""
    ecli: str = ""
    court: str = ""
    chamber: str = ""
    date: str = ""
    summary: str = ""
    cendoj_url: str = ""
    resolution_type: str = ""
    ponente: str = ""
    resolution_number: str = ""
    municipality: str = ""
    appeal_number: str = ""
    # Only populated when --with-content is used. Ephemeral — never stored.
    content: Optional[Dict[str, str]] = field(default=None)


async def search_cendoj(
    query: str,
    court: str = "TS",
    max_results: int = 10,
    date_from: str = "",
    date_to: str = "",
) -> List[SentenceReference]:
    """Navigate CENDOJ search and extract references from results."""
    from playwright.async_api import async_playwright

    results: List[SentenceReference] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            locale="es-ES",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) "
                "Gecko/20100101 Firefox/128.0"
            ),
        )
        page = await context.new_page()

        try:
            # Step 1: Navigate to search form
            logger.info("Navigating to CENDOJ search page...")
            await page.goto(CENDOJ_SEARCH_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(1000)

            # Step 2: Dismiss the legal notice modal (blocks all interaction)
            try:
                modal = page.locator('#modalAvisoLegal')
                modal_close = page.locator(
                    '#modalAvisoLegal .close, '
                    '#modalAvisoLegal button[data-dismiss="modal"], '
                    '#modalAvisoLegal .btn'
                ).first
                await modal_close.wait_for(state="visible", timeout=5000)
                await modal_close.click()
                # Wait for modal to fully disappear (Bootstrap fade animation)
                await modal.wait_for(state="hidden", timeout=5000)
                logger.info("Dismissed legal notice modal")
                await page.wait_for_timeout(300)
            except Exception:
                # Modal might not appear (e.g., cookies already accepted)
                logger.debug("No legal notice modal found (or already dismissed)")

            # Step 3: Fill search query ONLY (no other field modifications)
            # Using Playwright type() to trigger full keyboard events
            text_input = page.locator('#frmBusquedajurisprudencia_TEXT')
            await text_input.click()
            await text_input.fill("")  # Clear first
            await text_input.type(query, delay=50)
            logger.info(f"Query typed: '{query}'")

            # Step 5: Fill optional date range (via UI interactions)
            if date_from:
                date_from_input = page.locator(
                    '#frmBusquedajurisprudencia_FECHARESOLUCIONDESDE'
                )
                await date_from_input.fill(date_from)
                logger.info(f"Date from: {date_from}")

            if date_to:
                date_to_input = page.locator(
                    '#frmBusquedajurisprudencia_FECHARESOLUCIONHASTA'
                )
                await date_to_input.fill(date_to)
                logger.info(f"Date to: {date_to}")

            # Step 6: Leave recordsPerPage at default (10)

            # Step 7: Intercept AJAX to debug, then submit via CENDOJ's JS
            ajax_data = {}
            async def on_request(request):
                if "search.action" in request.url:
                    ajax_data["url"] = request.url
                    ajax_data["method"] = request.method
                    ajax_data["post_data"] = request.post_data
                    logger.info(f"AJAX intercepted: {request.method} {request.url}")
                    logger.info(f"AJAX post data: {request.post_data[:500] if request.post_data else 'none'}")
            page.on("request", on_request)

            logger.info("Submitting search via launchSearch()...")
            await page.evaluate("launchSearch()")

            # Step 8: Wait for AJAX results to appear in the DOM
            try:
                await page.wait_for_selector(
                    '#jurisprudenciaresults .searchresults, '
                    '#jurisprudenciaresults .searchresult, '
                    '#jurisprudenciaresults .noresults, '
                    '#jurisprudenciaresults .alert',
                    timeout=15000,
                )
                logger.info("Search results loaded")
            except Exception:
                logger.warning("Timeout waiting for results selector, continuing...")
            await page.wait_for_timeout(1000)

            # Check AJAX results div content
            results_html = await page.evaluate("""() => {
                const el = document.getElementById('jurisprudenciaresults');
                return el ? el.innerText.substring(0, 500) : 'DIV NOT FOUND';
            }""")
            logger.info(f"Results div content: {results_html[:300]}")

            # Step 9: Check for errors or CAPTCHA
            page_text = await page.text_content("body") or ""
            page_url = page.url
            logger.info(f"Results page URL: {page_url}")

            if not page_text.strip():
                logger.error("Empty page received")
                return results

            if "captcha" in page_text.lower():
                logger.error("CAPTCHA triggered — aborting")
                return results

            if "no se ha podido atender" in page_text.lower():
                # Extract the specific error message for debugging
                idx = page_text.lower().index("no se ha podido atender")
                context_start = max(0, idx - 100)
                context_end = min(len(page_text), idx + 300)
                error_context = page_text[context_start:context_end].strip().replace("\n", " ")
                logger.error(f"CENDOJ error: ...{error_context}...")
                return results

            if "resultados" not in page_text.lower() and len(page_text) < 500:
                logger.warning(f"Unexpected page content (len={len(page_text)}): "
                              f"{page_text[:300].strip()}")
                return results

            # Step 10: Extract HTML structure for debugging, then extract references
            logger.info("Extracting references from results page...")

            # First, dump the HTML structure of the first result item
            first_result_html = await page.evaluate("""() => {
                const resultsDiv = document.getElementById('jurisprudenciaresults');
                if (!resultsDiv) return 'NO results div';

                const firstItem = resultsDiv.querySelector('.searchresult');
                if (firstItem) return firstItem.outerHTML.substring(0, 1500);

                // Fallback: show the first 2000 chars of results HTML
                return resultsDiv.innerHTML.substring(0, 2000);
            }""")
            logger.info(f"Results HTML structure: {first_result_html[:800]}")

            # Extract results from div.searchresult containers
            raw_results = await page.evaluate(r"""() => {
                const entries = [];
                const resultsDiv = document.getElementById('jurisprudenciaresults');
                if (!resultsDiv) return entries;

                // Each result is a div.searchresult with structured children
                const resultDivs = resultsDiv.querySelectorAll('.searchresult');
                resultDivs.forEach(div => {
                    // Main link: <a> inside div.title with data-roj attribute
                    const titleLink = div.querySelector('.title a[data-roj]');
                    if (!titleLink) return;

                    const url = titleLink.href || '';
                    const roj = titleLink.getAttribute('data-roj') || '';
                    const ref = titleLink.getAttribute('data-reference') || '';
                    const fechares = titleLink.getAttribute('data-fechares') || '';
                    const dbMatch = titleLink.getAttribute('data-databasematch') || '';

                    // Metadata: ECLI, Sala, Ponente, etc. from div.metadatos li b
                    const metaItems = div.querySelectorAll('.metadatos li b');
                    let ecli = '';
                    let chamber = '';
                    let ponente = '';
                    let resolution_number = '';
                    let municipality = '';
                    let appeal_number = '';

                    metaItems.forEach(b => {
                        const text = b.textContent.trim();
                        const parentText = (b.parentElement && b.parentElement.textContent) || '';

                        if (text.startsWith('ECLI:')) {
                            ecli = text;
                        } else if (text.startsWith('Sala ') || text.startsWith('Juzgado ')) {
                            chamber = text;
                        } else if (parentText.includes('Ponente')) {
                            ponente = text;
                        } else if (parentText.includes('Resolución')) {
                            resolution_number = text;
                        } else if (parentText.includes('Municipio')) {
                            municipality = text;
                        } else if (parentText.includes('Recurso')) {
                            appeal_number = text;
                        }
                    });

                    // Summary: prefer full hidden summary, fallback to visible
                    const hiddenSummary = div.querySelector('.hddnsummary');
                    const visibleSummary = div.querySelector('.summary');
                    let summary = '';
                    if (hiddenSummary) {
                        summary = hiddenSummary.textContent.trim();
                    } else if (visibleSummary) {
                        summary = visibleSummary.textContent.trim();
                        // Remove "Resumen Automático:" prefix
                        summary = summary.replace(/^Resumen Autom[aá]tico:\s*/i, '');
                    }

                    entries.push({
                        url,
                        data_roj: roj,
                        data_ref: ref,
                        data_fechares: fechares,
                        data_db: dbMatch,
                        ecli,
                        chamber,
                        ponente,
                        resolution_number,
                        municipality,
                        appeal_number,
                        summary: summary.substring(0, 500),
                        link_text: titleLink.textContent.trim(),
                    });
                });

                return entries;
            }""")

            logger.info(f"Found {len(raw_results)} raw results")

            # Debug: log first raw result to understand structure
            if raw_results:
                sample = raw_results[0]
                logger.info(f"Sample: ROJ={sample.get('data_roj', 'N/A')} "
                           f"ECLI={sample.get('ecli', 'N/A')} "
                           f"chamber={sample.get('chamber', 'N/A')}")
                logger.info(f"Sample summary: {sample.get('summary', 'N/A')[:200]}")

            # Step 11: Parse each result into a SentenceReference
            for raw in raw_results[:max_results]:
                ref = _parse_result_entry(raw, court)
                if ref.roj or ref.ecli or ref.cendoj_url:
                    results.append(ref)

            logger.info(f"Parsed {len(results)} valid references")

        except Exception as e:
            logger.error(f"Browser agent error: {e}")

        finally:
            await browser.close()

    return results


def _parse_result_entry(raw: dict, court: str) -> SentenceReference:
    """Parse a raw result entry into a SentenceReference.

    Uses structured data extracted from div.searchresult DOM elements:
    - data_roj, ecli, chamber, ponente: directly from DOM attributes/elements
    - summary: from div.hddnsummary (full) or div.summary (truncated)
    - link_text: title link text containing date and ROJ
    """
    ref = SentenceReference()

    # CENDOJ URL
    ref.cendoj_url = raw.get("url", "")

    # ROJ — from data-roj attribute (reliable)
    ref.roj = raw.get("data_roj", "")

    # ECLI — extracted directly from div.metadatos
    ref.ecli = raw.get("ecli", "")

    # Chamber (Sala)
    ref.chamber = raw.get("chamber", "")

    # Date — from data-fechares (YYYYMMDD format) or parse from link_text
    fechares = raw.get("data_fechares", "")
    if fechares and len(fechares) == 8:
        # Convert YYYYMMDD → DD/MM/YYYY
        ref.date = f"{fechares[6:8]}/{fechares[4:6]}/{fechares[:4]}"
    else:
        # Fallback: parse "a DD de MES de YYYY" from link text
        link_text = raw.get("link_text", "")
        spanish_date = re.search(
            r'a?\s*(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})',
            link_text, re.IGNORECASE,
        )
        if spanish_date:
            day, month_name, year = spanish_date.groups()
            MONTHS = {
                "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
                "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
                "septiembre": "09", "octubre": "10", "noviembre": "11",
                "diciembre": "12",
            }
            month = MONTHS.get(month_name.lower(), "00")
            ref.date = f"{int(day):02d}/{month}/{year}"

    # Court — extract court code from ROJ prefix via regex
    # ROJ format: {resolution_prefix}{court_code} {region} {number}/{year}
    #   Resolution prefixes: S (Sentencia), A (Auto), AA (Auto Aclaración), P (Providencia)
    #   Court codes: TS, AN, TSJ, AP
    # Examples: STS 216/2026, AAP NA 81/2026, STSJ ICAN 4330/2025, AAN 45/2026
    roj = ref.roj
    court_match = re.match(r'^[SAP]{1,2}(TS|AN|TSJ|AP)\b', roj, re.IGNORECASE)
    if court_match:
        court_code = court_match.group(1).upper()
        if court_code == "TS":
            ref.court = "Tribunal Supremo"
        elif court_code == "AN":
            ref.court = "Audiencia Nacional"
        elif court_code == "TSJ":
            ref.court = "TSJ"
            # Extract autonomous community from link_text: "STSJ Canarias, a 22..."
            link_text = raw.get("link_text", "")
            tsj_match = re.search(r'(?:STSJ|TSJ|ATSJ)\s+(\w[\w\s]+?),', link_text)
            if tsj_match:
                ref.court = f"TSJ {tsj_match.group(1).strip()}"
        elif court_code == "AP":
            ref.court = "Audiencia Provincial"
    else:
        ref.court = raw.get("data_db", court)

    # Resolution type — from ROJ prefix letter
    if roj:
        first_char = roj[0].upper()
        if first_char == "S":
            ref.resolution_type = "Sentencia"
        elif first_char == "A":
            ref.resolution_type = "Auto"
        elif first_char == "P":
            ref.resolution_type = "Providencia"

    # Summary — already extracted from DOM (hddnsummary or summary div)
    summary = raw.get("summary", "")
    if summary:
        # Clean up: remove "Resumen Automático:" if present, truncate
        summary = re.sub(r'^(?:RESUMEN|Resumen\s+Autom[aá]tico)\s*:\s*', '', summary)
        ref.summary = summary[:300]

    # Extra metadata from div.metadatos
    ref.ponente = raw.get("ponente", "")
    ref.resolution_number = raw.get("resolution_number", "")
    ref.municipality = raw.get("municipality", "")
    ref.appeal_number = raw.get("appeal_number", "")

    return ref


# =============================================================================
# PDF Download & Text Extraction (ephemeral — nothing stored)
# =============================================================================

def _parse_open_document_url(url: str) -> Optional[Tuple[str, str, str]]:
    """Extract (db, reference_hash, optimize_date) from an openDocument URL.

    URL pattern: https://www.poderjudicial.es/search/{DB}/openDocument/{HASH}/{DATE}
    Returns: (db, hash, date) or None
    """
    match = re.search(r'/search/(\w+)/openDocument/([a-f0-9]+)/(\d{8})', url)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None


def _extract_pdf_content(pdf_bytes: bytes) -> Dict[str, str]:
    """Extract text and sections from a CENDOJ PDF in memory.

    Returns dict with legal_grounds, ruling, facts_summary, and full_text_length.
    Text is size-limited for LLM context windows.
    Nothing is written to disk.
    """
    from PyPDF2 import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))

    all_text = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        all_text.append(page_text)
    full_text = "\n".join(all_text)

    # Split into sections
    facts, legal_grounds, ruling = _split_sections(full_text)

    return {
        "legal_grounds": legal_grounds[:5000] if legal_grounds else "",
        "ruling": ruling[:2000] if ruling else "",
        "facts_summary": facts[:1000] if facts else "",
        "full_text_length": str(len(full_text)),
    }


def _split_sections(text: str) -> Tuple[str, str, str]:
    """Split sentence text into (facts, legal_grounds, ruling)."""
    facts = ""
    legal_grounds = ""
    ruling = ""

    positions = {}
    for section_name, pattern in SECTION_PATTERNS.items():
        match = pattern.search(text)
        if match:
            positions[section_name] = match.start()

    if not positions:
        return facts, legal_grounds, ruling

    sorted_sections = sorted(positions.items(), key=lambda x: x[1])

    for i, (name, start) in enumerate(sorted_sections):
        end = sorted_sections[i + 1][1] if i + 1 < len(sorted_sections) else len(text)
        section_text = text[start:end].strip()

        if name == "facts":
            facts = section_text
        elif name == "legal_grounds":
            legal_grounds = section_text
        elif name == "ruling":
            ruling = section_text

    return facts, legal_grounds, ruling


async def download_and_extract_pdfs(
    references: List[SentenceReference],
    max_content: int = 3,
) -> None:
    """Download PDFs for top N references and extract text in memory.

    Modifies references in-place, adding content dict to each.
    All data is ephemeral — PDFs live in memory only and are
    garbage collected when the container exits.
    """
    import httpx

    to_process = [r for r in references[:max_content] if r.cendoj_url]
    if not to_process:
        return

    logger.info(f"Downloading PDFs for top {len(to_process)} results...")

    async with httpx.AsyncClient(
        timeout=60.0,
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) "
                "Gecko/20100101 Firefox/128.0"
            ),
        },
    ) as client:
        for idx, ref in enumerate(to_process):
            parsed = _parse_open_document_url(ref.cendoj_url)
            if not parsed:
                logger.warning(f"Cannot parse URL for PDF: {ref.cendoj_url[:60]}")
                continue

            db, doc_hash, optimize = parsed
            pdf_url = PDF_URL_TEMPLATE.format(
                base=CENDOJ_BASE_URL,
                db=db,
                reference=doc_hash,
                optimize=optimize,
            )

            try:
                logger.info(f"  [{idx+1}/{len(to_process)}] Downloading: {ref.roj}")
                response = await client.get(pdf_url)

                if response.status_code != 200:
                    logger.error(f"  PDF download failed ({response.status_code}): {ref.roj}")
                    continue

                if not response.content[:5] == b"%PDF-":
                    logger.error(f"  Response is not a PDF: {ref.roj}")
                    continue

                # Extract text in memory — nothing written to disk
                content = _extract_pdf_content(response.content)
                ref.content = content
                logger.info(
                    f"  Extracted: {content.get('full_text_length', '0')} chars, "
                    f"legal_grounds={len(content.get('legal_grounds', ''))} chars, "
                    f"ruling={len(content.get('ruling', ''))} chars"
                )

                # Rate limit between downloads
                if idx < len(to_process) - 1:
                    await asyncio.sleep(PDF_DOWNLOAD_DELAY)

            except Exception as e:
                logger.error(f"  PDF extraction failed for {ref.roj}: {e}")


async def main():
    parser = argparse.ArgumentParser(
        description="CENDOJ Reference Agent — ephemeral browser search",
    )
    parser.add_argument(
        "--query", required=True,
        help="Search query (e.g., 'despido improcedente periodo de prueba')",
    )
    parser.add_argument(
        "--court", choices=["TS", "AN", "TSJ", "AP"], default="TS",
        help="Court: TS (Tribunal Supremo), AN (Audiencia Nacional), "
             "TSJ (Tribunal Superior de Justicia), AP (Audiencia Provincial)",
    )
    parser.add_argument(
        "--max-results", type=int, default=10,
        help="Maximum references to return (default: 10, max: 50)",
    )
    parser.add_argument(
        "--date-from", default="",
        help="Start date DD/MM/YYYY",
    )
    parser.add_argument(
        "--date-to", default="",
        help="End date DD/MM/YYYY",
    )
    parser.add_argument(
        "--with-content", type=int, default=0, metavar="N",
        help=(
            "Download PDFs for top N results and extract text as ephemeral "
            "LLM context. Text is never stored — only lives in memory until "
            "the container exits. (default: 0 = references only)"
        ),
    )
    args = parser.parse_args()

    results = await search_cendoj(
        query=args.query,
        court=args.court,
        max_results=args.max_results,
        date_from=args.date_from,
        date_to=args.date_to,
    )

    # Optional: download PDFs and extract text for top N results
    if args.with_content > 0 and results:
        await download_and_extract_pdfs(results, max_content=args.with_content)

    # Output JSON to stdout (logs go to stderr)
    output = [asdict(r) for r in results]
    print(json.dumps(output, ensure_ascii=False, indent=2))

    content_count = sum(1 for r in results if r.content)
    logger.info(f"Done — {len(results)} references, {content_count} with content")


if __name__ == "__main__":
    asyncio.run(main())
