"""
CENDOJ Scraper Prototype — Judicial Sentences (TS + AN)

Validates technical viability of downloading judicial sentences from CENDOJ
(Centro de Documentación Judicial) for the NouxCubeIA system.

Architecture (validated by testing):
  1. Search via POST to search.action (no CAPTCHA!) → returns HTML with document refs
  2. Parse search results: extract reference hashes from data-clipboard-text attributes
  3. PDF download via contenidos.action?action=accessToPDF&reference={hash}&optimize={date}
  4. Text extraction from PDF via PyPDF2 (metadata in PDF + page 1 header)
  5. Section splitting: ANTECEDENTES DE HECHO → FUNDAMENTOS DE DERECHO → FALLO

Technical findings:
  - POST search works without CAPTCHA (GET triggers "Control de grandes paginaciones")
  - openDocument page embeds PDF via <object data="contenidos.action?...">
  - PDF Content-Type includes filename: application/pdf; name="STS_216_2023.pdf"
  - PDF metadata has: Title, Author=CENDOJ, Subject=Court+Jurisdiction, Keywords
  - Page 1 of PDF is a structured header with ROJ, ECLI, Cendoj ID, court, date, etc.
  - Text extraction yields ~100K+ chars per sentence with all sections

Usage:
    # SEARCH mode: discover and download sentences automatically
    python3 scripts/cendoj_prototype.py --search --court TS --jurisdiction social --limit 5
    python3 scripts/cendoj_prototype.py --search --court AN --date-from 01/01/2024 --limit 10
    python3 scripts/cendoj_prototype.py --search --court TS --text "despido improcedente" --limit 3

    # PRESET mode: download from curated list
    python3 scripts/cendoj_prototype.py --preset test --limit 3

    # SINGLE mode: download a known sentence by its document reference
    python3 scripts/cendoj_prototype.py --ref 4003dd21ec9dfd2fa0a8778d75e36f0d --date 20230210 --court AN

    # Save results to JSON
    python3 scripts/cendoj_prototype.py --search --court TS --jurisdiction civil --limit 5 --output results.json

    # Dry run (no downloads)
    python3 scripts/cendoj_prototype.py --search --court TS --dry-run

Rate limit: CENDOJ prohibits >100 downloads/day. This script defaults to 80 max.

Dependencies: pip install httpx PyPDF2 beautifulsoup4
"""

import asyncio
import argparse
import hashlib
import io
import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

CENDOJ_BASE_URL = "https://www.poderjudicial.es/search"

# PDF download URL (validated — works without CAPTCHA)
PDF_URL_TEMPLATE = (
    "{base}/contenidos.action"
    "?action=accessToPDF"
    "&publicinterface=true"
    "&tab={court}"
    "&reference={reference}"
    "&encode=true"
    "&optimize={optimize}"
    "&databasematch={court}"
)

# Search form parameters (from frmBusquedajurisprudencia)
SEARCH_ACTION_URL = f"{CENDOJ_BASE_URL}/search.action"

# Court organ codes for TIPOORGANOPUB (from form select options)
COURT_ORGAN_CODES = {
    # Tribunal Supremo
    "TS": "11|12|13|14|15|16",        # All TS chambers
    "TS_CIVIL": "11",                  # Sala de lo Civil
    "TS_PENAL": "12",                  # Sala de lo Penal
    "TS_CONTENCIOSO": "13",            # Sala de lo Contencioso
    "TS_SOCIAL": "14",                 # Sala de lo Social
    "TS_MILITAR": "15",                # Sala de lo Militar
    # Audiencia Nacional
    "AN": "22|2264|23|24|25|26|27|28|29",  # All AN chambers
    "AN_PENAL": "22",                  # Sala de lo Penal
    "AN_CONTENCIOSO": "23",            # Sala de lo Contencioso
    "AN_SOCIAL": "24",                 # Sala de lo Social
}

# Rate limiting
MAX_REQUESTS_PER_DAY = 80
MIN_REQUEST_DELAY = 3.0  # seconds

COURT_NAMES = {
    "TS": "Tribunal Supremo",
    "AN": "Audiencia Nacional",
}

JURISDICTIONS = {
    "civil": "CIVIL",
    "penal": "PENAL",
    "contencioso": "CONTENCIOSO",
    "social": "SOCIAL",
    "militar": "MILITAR",
}


# =============================================================================
# Curated Sentence Presets (known document references)
#
# Alternative to search mode: use curated lists of known sentences.
# Each entry has the document hash (reference) and date (optimize)
# from the openDocument URL pattern.
#
# These can be populated from:
#   - Search mode output (--search generates these references)
#   - Manual browser search + copy openDocument URLs
#   - cendoj-extractor Chrome extension output
#   - Legal databases that reference CENDOJ
# =============================================================================

SENTENCE_PRESETS: Dict[str, Dict[str, Any]] = {
    "laboral_ts": {
        "description": "Sentencias clave del Tribunal Supremo en materia laboral",
        "sentences": [
            # STS 216/2023 - Contencioso-Administrativo (test sentence)
            {"reference": "4003dd21ec9dfd2fa0a8778d75e36f0d", "date": "20230210", "court": "AN",
             "hint": "STS 216/2023 - Contencioso"},
        ],
    },
    "test": {
        "description": "Test preset with a single known sentence",
        "sentences": [
            {"reference": "4003dd21ec9dfd2fa0a8778d75e36f0d", "date": "20230210", "court": "AN",
             "hint": "STS 216/2023 - ECLI:ES:TS:2023:216 - Contencioso-Administrativo"},
        ],
    },
}


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class SentenceMetadata:
    """Metadata extracted from CENDOJ PDF."""
    roj: str = ""                          # e.g., "STS 216/2023"
    ecli: str = ""                         # e.g., "ECLI:ES:TS:2023:216"
    cendoj_id: str = ""                    # e.g., "28079130022023100019"
    court: str = ""                        # "Tribunal Supremo. Sala de lo Contencioso"
    court_code: str = ""                   # "TS"
    chamber: str = ""                      # "Sala de lo Contencioso"
    section: str = ""                      # "2"
    jurisdiction: str = ""                 # "contencioso-administrativo"
    resolution_type: str = ""              # "Sentencia"
    resolution_date: str = ""              # "02/02/2023"
    resolution_number: str = ""            # "131/2023"
    appeal_number: str = ""                # "7918/2020"
    procedure_type: str = ""               # "Recurso de Casación Contencioso-Administrativo"
    judge_rapporteur: str = ""             # "FRANCISCO JOSE NAVARRO SANCHIS"
    language: str = "es"
    # PDF info
    pdf_url: str = ""
    pdf_filename: str = ""                 # "STS_216_2023.pdf" (from Content-Type)
    pdf_pages: int = 0
    pdf_bytes: int = 0
    # Content hash (for dedup/change detection)
    content_hash: str = ""


@dataclass
class SentenceContent:
    """Full content of a judicial sentence."""
    metadata: SentenceMetadata
    full_text: str = ""                    # Complete text from PDF
    facts: str = ""                        # Antecedentes de hecho
    legal_grounds: str = ""                # Fundamentos de derecho
    ruling: str = ""                       # Fallo
    # Extracted references
    cited_laws: List[str] = field(default_factory=list)       # Law references
    cited_boe_ids: List[str] = field(default_factory=list)    # BOE IDs
    cited_articles: List[str] = field(default_factory=list)   # Article numbers
    cited_sentences: List[str] = field(default_factory=list)  # ECLIs
    # Keywords from PDF metadata
    keywords: List[str] = field(default_factory=list)


@dataclass
class ScraperStats:
    """Statistics for the scraping session."""
    requests_made: int = 0
    pdfs_downloaded: int = 0
    pdfs_parsed: int = 0
    total_text_chars: int = 0
    total_pages: int = 0
    errors: int = 0
    start_time: float = 0.0

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time if self.start_time else 0

    @property
    def requests_remaining(self) -> int:
        return MAX_REQUESTS_PER_DAY - self.requests_made


@dataclass
class SearchResultEntry:
    """A single entry from a CENDOJ search result page."""
    reference: str = ""      # Document hash (for PDF download)
    date: str = ""           # Date string YYYYMMDD (for PDF download)
    court: str = ""          # Court code (AN, TS)
    title: str = ""          # e.g., "STS 216/2023 - ECLI:ES:TS:2023:216"
    roj: str = ""            # ROJ identifier
    open_document_url: str = ""  # Full openDocument URL


# =============================================================================
# Rate Limiter
# =============================================================================

class RateLimiter:
    """Simple rate limiter for CENDOJ requests."""

    def __init__(self, max_per_day: int = MAX_REQUESTS_PER_DAY, min_delay: float = MIN_REQUEST_DELAY):
        self.max_per_day = max_per_day
        self.min_delay = min_delay
        self._count = 0
        self._last_request_time = 0.0
        self._day_start = time.time()

    @property
    def requests_remaining(self) -> int:
        if time.time() - self._day_start > 86400:
            self._count = 0
            self._day_start = time.time()
        return self.max_per_day - self._count

    async def acquire(self) -> bool:
        """Wait for rate limit slot. Returns False if daily limit reached."""
        if self.requests_remaining <= 0:
            logger.warning("Daily request limit reached (%d). Stopping.", self.max_per_day)
            return False

        elapsed = time.time() - self._last_request_time
        if elapsed < self.min_delay:
            wait = self.min_delay - elapsed
            logger.debug("Rate limit: waiting %.1fs", wait)
            await asyncio.sleep(wait)

        self._count += 1
        self._last_request_time = time.time()
        return True


# =============================================================================
# CENDOJ PDF Client
# =============================================================================

# Index pages per court (for establishing session + getting form structure)
COURT_INDEX_PAGES = {
    "AN": f"{CENDOJ_BASE_URL}/indexAN.jsp",
    "TS": f"{CENDOJ_BASE_URL}/indexAN.jsp",  # TS uses same form, different databasematch
}


class CENDOJClient:
    """HTTP client for CENDOJ with rate limiting and session management.

    CENDOJ requires:
    1. A JSESSIONID cookie (obtained by visiting the search form page)
    2. POST to search.action with correct form fields (from indexAN.jsp)
    3. Specific form fields differ from what the CAPTCHA page shows

    Validated form fields (from indexAN.jsp HTML analysis):
        action, sort, recordsPerPage, databasematch, start, TEXT,
        TIPORESOLUCION, SUBTIPORESOLUCION, SECCION, ROJ, ECLI,
        FECHARESOLUCIONDESDE, FECHARESOLUCIONHASTA, NUMERORESOLUCION,
        NUMERORECURSO, PONENTE, NORMA, VALUESCOMUNIDAD, ANYO
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.5",
        "Connection": "keep-alive",
    }

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.rate_limiter = rate_limiter or RateLimiter()
        self._client: Optional[httpx.AsyncClient] = None
        self._session_initialized = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=60.0,
                follow_redirects=True,
                headers=self.HEADERS,
            )
        return self._client

    async def _ensure_session(self, court: str = "AN"):
        """Visit the CENDOJ search form page to obtain a JSESSIONID cookie.
        Required before any search POST request."""
        if self._session_initialized:
            return

        client = await self._get_client()
        index_url = COURT_INDEX_PAGES.get(court, COURT_INDEX_PAGES["AN"])
        try:
            response = await client.get(index_url)
            if response.status_code in (200, 404):
                # Even a 404 sets the JSESSIONID cookie
                self._session_initialized = True
                logger.debug("Session initialized (JSESSIONID obtained)")
            else:
                logger.warning("Session init returned %d", response.status_code)
        except httpx.HTTPError as e:
            logger.error("Failed to initialize session: %s", e)

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def download_pdf(self, reference: str, date: str, court: str = "AN") -> Optional[Tuple[bytes, str]]:
        """Download a sentence PDF. Returns (pdf_bytes, filename) or None."""
        if not await self.rate_limiter.acquire():
            return None

        pdf_url = PDF_URL_TEMPLATE.format(
            base=CENDOJ_BASE_URL,
            court=court,
            reference=reference,
            optimize=date,
        )

        client = await self._get_client()
        try:
            response = await client.get(pdf_url)

            if response.status_code != 200:
                logger.error("PDF download failed: %d for ref=%s", response.status_code, reference[:20])
                return None

            # Check it's actually a PDF
            content_type = response.headers.get("content-type", "")
            if not response.content[:5] == b"%PDF-":
                logger.error("Response is not a PDF (content-type: %s)", content_type)
                return None

            # Extract filename from Content-Type: application/pdf; name="STS_216_2023.pdf"
            filename = ""
            name_match = re.search(r'name="([^"]+)"', content_type)
            if name_match:
                filename = name_match.group(1)

            logger.debug(
                "PDF downloaded: %s (%d KB, file=%s)",
                reference[:16], len(response.content) // 1024, filename
            )
            return response.content, filename

        except httpx.HTTPError as e:
            logger.error("HTTP error downloading PDF ref=%s: %s", reference[:20], e)
            return None

    async def search(
        self,
        court: str = "TS",
        jurisdiction: str = "",
        text: str = "",
        date_from: str = "",
        date_to: str = "",
        ponente: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[SearchResultEntry], int]:
        """
        Search CENDOJ via POST to search.action.

        Requires:
        - JSESSIONID cookie (obtained automatically via _ensure_session)
        - At least one search criterion (TEXT, date range, ROJ, ECLI, etc.)

        Returns (results, total_count).

        Args:
            court: Court key (e.g., "TS", "AN") — maps to databasematch
            jurisdiction: Currently unused (indexAN.jsp form doesn't have this field)
            text: Free-text search query (TEXT field — main search criterion)
            date_from: Start date DD/MM/YYYY (FECHARESOLUCIONDESDE)
            date_to: End date DD/MM/YYYY (FECHARESOLUCIONHASTA)
            ponente: Judge name filter (PONENTE)
            page: Page number (1-based, maps to 'start')
            page_size: Results per page (max 50)
        """
        from bs4 import BeautifulSoup

        if not await self.rate_limiter.acquire():
            return [], 0

        # Determine databasematch: AN or TS based on court prefix
        db_match = "AN" if court.startswith("AN") else "TS"

        # Ensure session cookie exists (JSESSIONID required for POST)
        await self._ensure_session(db_match)

        # Build form data matching the ACTUAL indexAN.jsp form structure.
        # Important: the real form does NOT have JURISDICCION or TIPOORGANOPUB.
        # Those appear only in the CAPTCHA re-submit form.
        form_data = {
            "djrae": "",
            "action": "query",
            "sort": "IN_FECHARESOLUCION:decreasing",
            "recordsPerPage": str(min(page_size, 50)),
            "lastsentences": "",
            "databasematch": db_match,
            "ANYO": "",
            "start": str(page),
            "maxresults": "",
            "page": "",
            "ID_NORMA": "",
            "ARTICULO": "",
            "org": "",
            "ccaa": "",
            "land": "",
            "TIPOINTERES_INSTITUCIONES": "",
            "INSTITUCION": "",
            "landing": "",
            "landingtype": "",
            "repetitivas": "",
            "FECHAENTRADA": "",
            "TEXT": text,
            "TIPORESOLUCION": "",
            "SUBTIPORESOLUCION": "",
            "SECCION": "",
            "VALUESCOMUNIDAD": "",
            "ROJ": "",
            "ECLI": "",
            "FECHARESOLUCIONDESDE": date_from,
            "NUMERORESOLUCION": "",
            "FECHARESOLUCIONHASTA": date_to,
            "NUMERORECURSO": "",
            "PONENTE": ponente,
            "NORMA": "",
        }

        # CENDOJ requires at least one search criterion
        has_criteria = any([text, date_from, date_to, ponente])
        if not has_criteria:
            logger.error(
                "CENDOJ requires at least one search criterion. "
                "Use --text, --date-from/to, or ponente."
            )
            return [], 0

        index_url = COURT_INDEX_PAGES.get(db_match, COURT_INDEX_PAGES["AN"])
        client = await self._get_client()
        try:
            response = await client.post(
                SEARCH_ACTION_URL,
                data=form_data,
                headers={
                    **self.HEADERS,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": index_url,
                },
            )

            if response.status_code != 200:
                logger.error("Search failed with status %d", response.status_code)
                return [], 0

            html = response.text

            # Check for CAPTCHA
            if "captchacontent" in html:
                logger.error("CAPTCHA triggered on search.")
                return [], 0

            # Check for validation errors
            if "errorMessage" in html:
                err_match = re.search(r'errorMessage">(.*?)</span>', html, re.DOTALL)
                err_msg = err_match.group(1).strip() if err_match else "unknown"
                logger.error("CENDOJ search error: %s", err_msg)
                return [], 0

            # Parse results
            soup = BeautifulSoup(html, "html.parser")
            results: List[SearchResultEntry] = []

            # Extract total count from "X resultados" text
            total_count = 0
            count_el = soup.select_one(".num-results, .numresultados, #numResul")
            if count_el:
                count_match = re.search(r'([\d.]+)\s*resultado', count_el.get_text())
                if count_match:
                    total_count = int(count_match.group(1).replace(".", ""))

            # Fallback: extract from any text on the page
            if not total_count:
                body_text = soup.get_text()
                count_match = re.search(r'([\d.]+)\s+resultado', body_text)
                if count_match:
                    total_count = int(count_match.group(1).replace(".", ""))

            # Extract document references from data-clipboard-text attributes
            # These contain openDocument URLs like:
            # https://www.poderjudicial.es/search/AN/openDocument/{hash}/{date}
            clipboard_elements = soup.find_all(attrs={"data-clipboard-text": True})
            for el in clipboard_elements:
                url = el["data-clipboard-text"]
                entry = self._parse_open_document_url(url, db_match)
                if entry:
                    # Try to extract title/ROJ from nearby elements
                    parent = el.find_parent("div", class_="result") or el.find_parent("li")
                    if parent:
                        title_el = parent.select_one("a, .title, h3, h4")
                        if title_el:
                            entry.title = title_el.get_text(strip=True)
                        roj_match = re.search(r'(S\w+\s+\d+/\d{4})', parent.get_text())
                        if roj_match:
                            entry.roj = roj_match.group(1)
                    results.append(entry)

            logger.info(
                "Search: %d results (total: %d) court=%s text='%s'",
                len(results), total_count, court, text[:30] if text else "(none)",
            )
            return results, total_count

        except httpx.HTTPError as e:
            logger.error("HTTP error during search: %s", e)
            return [], 0

    @staticmethod
    def _parse_open_document_url(url: str, default_court: str = "AN") -> Optional[SearchResultEntry]:
        """Parse an openDocument URL into a SearchResultEntry.

        URL pattern: https://www.poderjudicial.es/search/{COURT}/openDocument/{HASH}/{DATE}
        """
        match = re.search(
            r'/search/(\w+)/openDocument/([a-f0-9]+)/(\d{8})',
            url,
        )
        if not match:
            return None

        court_code = match.group(1)
        reference = match.group(2)
        date = match.group(3)

        return SearchResultEntry(
            reference=reference,
            date=date,
            court=court_code,
            open_document_url=url,
        )


# =============================================================================
# PDF Parser
# =============================================================================

class CENDOJPDFParser:
    """Extracts text and metadata from CENDOJ sentence PDFs."""

    # Page 1 header field patterns
    HEADER_PATTERNS = {
        "roj": re.compile(r'Roj:\s*(S\w+\s+\d+/\d{4})'),
        "ecli": re.compile(r'ECLI:ES:\w+:\d{4}:\d+'),
        "cendoj_id": re.compile(r'Id\s+Cendoj:\s*(\d+)'),
        "court": re.compile(r'[ÓO]rgano:\s*(.+?)(?:\n|$)'),
        "section": re.compile(r'Secci[oó]n:\s*(\w+)'),
        "date": re.compile(r'Fecha:\s*(\d{2}/\d{2}/\d{4})'),
        "appeal_number": re.compile(r'N[ºo°]\s+de\s+Recurso:\s*(\S+)'),
        "resolution_number": re.compile(r'N[ºo°]\s+de\s+Resoluci[oó]n:\s*(\S+)'),
        "procedure": re.compile(r'Procedimiento:\s*(.+?)(?:\n|$)'),
        "ponente": re.compile(r'Ponente:\s*(.+?)(?:\n|$)'),
        "resolution_type": re.compile(r'Tipo\s+de\s+Resoluci[oó]n:\s*(\w+)'),
    }

    # Section markers
    SECTION_PATTERNS = {
        "facts": re.compile(
            r'(?:ANTECEDENTES\s+DE\s+HECHO|RESULTANDO|HECHOS\s+PROBADOS)',
            re.IGNORECASE
        ),
        "legal_grounds": re.compile(
            r'(?:FUNDAMENTOS\s+DE\s+DERECHO|CONSIDERANDO|RAZONAMIENTOS\s+JUR[IÍ]DICOS)',
            re.IGNORECASE
        ),
        "ruling": re.compile(
            r'(?:FALL[OA]MOS|PARTE\s+DISPOSITIVA)',
            re.IGNORECASE
        ),
    }

    # Legal reference patterns
    BOE_ID_PATTERN = re.compile(r'BOE-[A-Z]-\d{4}-\d+')
    ECLI_CITE_PATTERN = re.compile(r'ECLI:ES:\w+:\d{4}:\d+')
    LAW_REF_PATTERN = re.compile(
        r'(?:Ley\s+(?:Org[aá]nica\s+)?\d+/\d{4}'
        r'|Real\s+Decreto(?:\s+Legislativo)?\s+\d+/\d{4}'
        r'|Decreto-[Ll]ey\s+\d+/\d{4})',
        re.IGNORECASE
    )
    ARTICLE_PATTERN = re.compile(
        r'(?:art[ií]culo|art\.?)\s+(\d+(?:\.\d+)?(?:\s*(?:bis|ter|quater|quinquies))?)',
        re.IGNORECASE
    )

    # Chamber → Jurisdiction mapping
    CHAMBER_JURISDICTION = {
        "civil": "civil",
        "primera": "civil",
        "penal": "penal",
        "segunda": "penal",
        "contencioso": "contencioso-administrativo",
        "tercera": "contencioso-administrativo",
        "social": "social",
        "cuarta": "social",
        "militar": "militar",
        "quinta": "militar",
    }

    @staticmethod
    def parse(pdf_bytes: bytes, pdf_filename: str = "") -> SentenceContent:
        """Parse a CENDOJ sentence PDF into structured content."""
        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        metadata = SentenceMetadata(
            pdf_filename=pdf_filename,
            pdf_pages=len(reader.pages),
            pdf_bytes=len(pdf_bytes),
        )

        # 1. Extract PDF-level metadata
        pdf_meta = reader.metadata or {}
        keywords_str = pdf_meta.get("/Keywords", "")
        if keywords_str:
            keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
        else:
            keywords = []

        # PDF Subject often contains "Court - Jurisdiction"
        subject = pdf_meta.get("/Subject", "")

        # 2. Extract full text from all pages
        all_text = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            all_text.append(page_text)
        full_text = "\n".join(all_text)

        # 3. Parse structured header from page 1
        page1_text = all_text[0] if all_text else ""
        CENDOJPDFParser._parse_header(page1_text, metadata)

        # If header parsing missed ECLI, try PDF title
        if not metadata.ecli:
            title = pdf_meta.get("/Title", "")
            ecli_match = re.search(r'ECLI:ES:\w+:\d{4}:\d+', title)
            if ecli_match:
                metadata.ecli = ecli_match.group(0)

        # Derive jurisdiction from court/chamber name
        if not metadata.jurisdiction and metadata.court:
            court_lower = metadata.court.lower()
            for key, jurisdiction in CENDOJPDFParser.CHAMBER_JURISDICTION.items():
                if key in court_lower:
                    metadata.jurisdiction = jurisdiction
                    break

        # Extract chamber from court name
        if not metadata.chamber and metadata.court:
            sala_match = re.search(
                r'(Sala\s+(?:Primera|Segunda|Tercera|Cuarta|Quinta|de\s+lo\s+\w+[-\w]*))',
                metadata.court, re.IGNORECASE
            )
            if sala_match:
                metadata.chamber = sala_match.group(1)

        # Derive court_code from ECLI or ROJ
        if not metadata.court_code:
            if metadata.ecli:
                parts = metadata.ecli.split(":")
                if len(parts) >= 3:
                    metadata.court_code = parts[2]
            elif metadata.roj:
                # STS → TS, SAN → AN
                roj_prefix = metadata.roj.split()[0] if metadata.roj else ""
                if roj_prefix.startswith("S"):
                    metadata.court_code = roj_prefix[1:]  # STS → TS

        # Content hash
        metadata.content_hash = hashlib.sha256(full_text.encode()).hexdigest()[:16]

        # 4. Split into sections
        facts, legal_grounds, ruling = CENDOJPDFParser._split_sections(full_text)

        # 5. Extract legal references
        cited_boe_ids = list(set(CENDOJPDFParser.BOE_ID_PATTERN.findall(full_text)))
        cited_laws = list(set(CENDOJPDFParser.LAW_REF_PATTERN.findall(full_text)))
        cited_articles = list(set(CENDOJPDFParser.ARTICLE_PATTERN.findall(full_text)))
        cited_sentences = list(set(CENDOJPDFParser.ECLI_CITE_PATTERN.findall(full_text)))

        # Remove self-citation
        if metadata.ecli and metadata.ecli in cited_sentences:
            cited_sentences.remove(metadata.ecli)

        return SentenceContent(
            metadata=metadata,
            full_text=full_text,
            facts=facts,
            legal_grounds=legal_grounds,
            ruling=ruling,
            cited_laws=cited_laws,
            cited_boe_ids=cited_boe_ids,
            cited_articles=cited_articles,
            cited_sentences=cited_sentences,
            keywords=keywords,
        )

    @staticmethod
    def _parse_header(page1_text: str, metadata: SentenceMetadata):
        """Parse the structured header on page 1 of a CENDOJ PDF."""
        for field_name, pattern in CENDOJPDFParser.HEADER_PATTERNS.items():
            match = pattern.search(page1_text)
            if not match:
                continue

            value = match.group(1) if match.lastindex else match.group(0)
            value = value.strip()

            if field_name == "roj" and not metadata.roj:
                metadata.roj = value
            elif field_name == "ecli" and not metadata.ecli:
                metadata.ecli = value
            elif field_name == "cendoj_id" and not metadata.cendoj_id:
                metadata.cendoj_id = value
            elif field_name == "court" and not metadata.court:
                metadata.court = value
            elif field_name == "section" and not metadata.section:
                metadata.section = value
            elif field_name == "date" and not metadata.resolution_date:
                metadata.resolution_date = value
            elif field_name == "appeal_number" and not metadata.appeal_number:
                metadata.appeal_number = value
            elif field_name == "resolution_number" and not metadata.resolution_number:
                metadata.resolution_number = value
            elif field_name == "procedure" and not metadata.procedure_type:
                metadata.procedure_type = value
            elif field_name == "ponente" and not metadata.judge_rapporteur:
                metadata.judge_rapporteur = value
            elif field_name == "resolution_type" and not metadata.resolution_type:
                metadata.resolution_type = value

    @staticmethod
    def _split_sections(text: str) -> Tuple[str, str, str]:
        """Split sentence text into facts, legal grounds, and ruling."""
        facts = ""
        legal_grounds = ""
        ruling = ""

        positions = {}
        for section_name, pattern in CENDOJPDFParser.SECTION_PATTERNS.items():
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


# =============================================================================
# CENDOJ Scraper (orchestrator)
# =============================================================================

class CENDOJScraper:
    """Main scraper: download PDFs from CENDOJ and extract structured content."""

    def __init__(self, dry_run: bool = False):
        self.rate_limiter = RateLimiter()
        self.client = CENDOJClient(self.rate_limiter)
        self.stats = ScraperStats(start_time=time.time())
        self.dry_run = dry_run

    async def close(self):
        await self.client.close()

    async def download_sentence(
        self, reference: str, date: str, court: str = "AN"
    ) -> Optional[SentenceContent]:
        """Download and parse a single sentence by its document reference."""
        pdf_url = PDF_URL_TEMPLATE.format(
            base=CENDOJ_BASE_URL, court=court,
            reference=reference, optimize=date,
        )
        logger.info("📄 Downloading PDF: ref=%s... court=%s", reference[:16], court)

        if self.dry_run:
            logger.info("[DRY RUN] Would download: %s", pdf_url[:100])
            return None

        result = await self.client.download_pdf(reference, date, court)
        if not result:
            self.stats.errors += 1
            return None

        pdf_bytes, filename = result
        self.stats.requests_made += 1
        self.stats.pdfs_downloaded += 1

        # Parse the PDF
        try:
            content = CENDOJPDFParser.parse(pdf_bytes, filename)
            self.stats.pdfs_parsed += 1
            self.stats.total_text_chars += len(content.full_text)
            self.stats.total_pages += content.metadata.pdf_pages

            m = content.metadata
            logger.info(
                "  ✅ %s | ECLI:%s | %d pages | %d chars | %d law refs | %d ECLI cites",
                m.roj, m.ecli, m.pdf_pages, len(content.full_text),
                len(content.cited_laws), len(content.cited_sentences),
            )
            return content

        except Exception as e:
            logger.error("  ❌ PDF parse error for ref=%s: %s", reference[:16], e)
            self.stats.errors += 1
            return None

    async def search_and_download(
        self,
        court: str = "TS",
        jurisdiction: str = "",
        text: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 10,
    ) -> List[SentenceContent]:
        """Search CENDOJ and download matching sentences.

        This is the primary automated pipeline:
        1. POST search → get document references
        2. For each result, download PDF + extract content
        3. Respect rate limits throughout
        """
        logger.info(
            "🔍 Searching CENDOJ: court=%s jurisdiction=%s text='%s' date=%s→%s limit=%d",
            court, jurisdiction or "ALL", text, date_from or "∞", date_to or "∞", limit,
        )

        if self.dry_run:
            logger.info("[DRY RUN] Would search with above parameters")
            return []

        # Phase 1: Search for document references
        all_search_results: List[SearchResultEntry] = []
        page = 1
        page_size = min(limit, 50)

        while len(all_search_results) < limit:
            search_results, total_count = await self.client.search(
                court=court,
                jurisdiction=jurisdiction,
                text=text,
                date_from=date_from,
                date_to=date_to,
                page=page,
                page_size=page_size,
            )
            self.stats.requests_made += 1

            if not search_results:
                break

            all_search_results.extend(search_results)
            logger.info(
                "  Page %d: got %d results (total available: %d, collected: %d/%d)",
                page, len(search_results), total_count, len(all_search_results), limit,
            )

            # Stop if we've collected enough or no more pages
            if len(all_search_results) >= limit or len(search_results) < page_size:
                break

            page += 1
            # Note: client.search() already calls rate_limiter.acquire()

        # Trim to limit
        all_search_results = all_search_results[:limit]
        logger.info("📋 Found %d sentences to download", len(all_search_results))

        # Phase 2: Download and parse each PDF
        results: List[SentenceContent] = []
        for i, entry in enumerate(all_search_results, 1):
            logger.info(
                "  [%d/%d] %s (ref=%s...)",
                i, len(all_search_results),
                entry.roj or entry.title or "unknown",
                entry.reference[:16],
            )
            content = await self.download_sentence(
                reference=entry.reference,
                date=entry.date,
                court=entry.court,
            )
            if content:
                results.append(content)

        return results

    async def download_preset(
        self, preset_name: str, limit: int = 50
    ) -> List[SentenceContent]:
        """Download all sentences in a preset."""
        preset = SENTENCE_PRESETS.get(preset_name)
        if not preset:
            logger.error("Unknown preset: %s (available: %s)",
                        preset_name, ", ".join(SENTENCE_PRESETS.keys()))
            return []

        sentences = preset["sentences"][:limit]
        logger.info(
            "📋 Downloading preset '%s': %s (%d sentences)",
            preset_name, preset["description"], len(sentences),
        )

        results = []
        for entry in sentences:
            content = await self.download_sentence(
                reference=entry["reference"],
                date=entry["date"],
                court=entry.get("court", "AN"),
            )
            if content:
                results.append(content)

        return results

    def print_stats(self):
        s = self.stats
        print("\n" + "=" * 60)
        print("📊 CENDOJ Scraper Prototype — Session Statistics")
        print("=" * 60)
        print(f"  Requests made:        {s.requests_made}")
        print(f"  Requests remaining:   {s.requests_remaining} (daily limit: {MAX_REQUESTS_PER_DAY})")
        print(f"  PDFs downloaded:      {s.pdfs_downloaded}")
        print(f"  PDFs parsed:          {s.pdfs_parsed}")
        print(f"  Total text:           {s.total_text_chars:,} chars")
        print(f"  Total pages:          {s.total_pages}")
        print(f"  Errors:               {s.errors}")
        print(f"  Elapsed:              {s.elapsed_seconds:.1f}s")
        print("=" * 60)


# =============================================================================
# Serialization
# =============================================================================

def sentence_to_dict(content: SentenceContent) -> Dict[str, Any]:
    """Convert SentenceContent to JSON-serializable dict."""
    d = asdict(content)
    # Truncate full_text in output for readability
    if len(d.get("full_text", "")) > 500:
        d["full_text_length"] = len(d["full_text"])
        d["full_text_preview"] = d["full_text"][:500] + "..."
        d["full_text"] = d["full_text"]  # Keep full text in JSON
    return d


def print_sentence_summary(content: SentenceContent):
    """Print a human-readable summary of a parsed sentence."""
    m = content.metadata
    print(f"\n  {'─' * 60}")
    print(f"  ROJ:              {m.roj}")
    print(f"  ECLI:             {m.ecli}")
    print(f"  CENDOJ ID:        {m.cendoj_id}")
    print(f"  Court:            {m.court}")
    print(f"  Court code:       {m.court_code}")
    print(f"  Chamber:          {m.chamber}")
    print(f"  Jurisdiction:     {m.jurisdiction}")
    print(f"  Section:          {m.section}")
    print(f"  Resolution type:  {m.resolution_type}")
    print(f"  Resolution date:  {m.resolution_date}")
    print(f"  Resolution num:   {m.resolution_number}")
    print(f"  Appeal num:       {m.appeal_number}")
    print(f"  Procedure:        {m.procedure_type}")
    print(f"  Ponente:          {m.judge_rapporteur}")
    print(f"  PDF:              {m.pdf_filename} ({m.pdf_pages} pages, {m.pdf_bytes//1024} KB)")
    print(f"  Text length:      {len(content.full_text):,} chars")
    print(f"  Content hash:     {m.content_hash}")
    print(f"  ─── Sections ───")
    print(f"  Antecedentes:     {len(content.facts):,} chars")
    print(f"  Fundamentos:      {len(content.legal_grounds):,} chars")
    print(f"  Fallo:            {len(content.ruling):,} chars")
    print(f"  ─── References ─")
    print(f"  BOE IDs:          {content.cited_boe_ids[:5]}")
    print(f"  Laws cited:       {content.cited_laws[:5]}")
    print(f"  Articles cited:   {content.cited_articles[:10]}")
    print(f"  Sentences cited:  {content.cited_sentences[:5]}")
    print(f"  Keywords:         {content.keywords}")


# =============================================================================
# CLI Entry Point
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(
        description="CENDOJ Scraper Prototype — Judicial Sentences (TS + AN)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # SEARCH mode (automated discovery + download)
  %(prog)s --search --court TS --jurisdiction social --limit 5
  %(prog)s --search --court AN --date-from 01/01/2024 --limit 10
  %(prog)s --search --court TS --text "despido improcedente" --limit 3
  %(prog)s --search --court TS_CIVIL --limit 20 --output sentencias_civil.json

  # SEARCH-ONLY mode (discover without downloading PDFs)
  %(prog)s --search-only --court TS --jurisdiction penal --limit 50

  # PRESET mode (curated list)
  %(prog)s --preset test

  # SINGLE mode (known reference)
  %(prog)s --ref 4003dd21ec9dfd2fa0a8778d75e36f0d --date 20230210 --court AN
        """,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--search", action="store_true",
                      help="Search CENDOJ and download matching sentences")
    mode.add_argument("--search-only", action="store_true",
                      help="Search CENDOJ and list results (no PDF download)")
    mode.add_argument("--preset", choices=list(SENTENCE_PRESETS.keys()),
                      help="Download sentences from a preset list")
    mode.add_argument("--ref", help="Document reference hash (from openDocument URL)")

    # Search parameters
    parser.add_argument("--court", default="TS",
                       choices=list(COURT_ORGAN_CODES.keys()),
                       help="Court code (default: TS)")
    parser.add_argument("--jurisdiction", default="",
                       choices=["", "civil", "penal", "contencioso", "social", "militar"],
                       help="Filter by jurisdiction")
    parser.add_argument("--text", default="", help="Free-text search query")
    parser.add_argument("--date-from", default="", help="Start date DD/MM/YYYY")
    parser.add_argument("--date-to", default="", help="End date DD/MM/YYYY")

    # Download parameters
    parser.add_argument("--date", default="", help="Document date YYYYMMDD (for --ref mode)")
    parser.add_argument("--limit", type=int, default=10,
                       help="Max sentences (default: 10)")
    parser.add_argument("--output", default="", help="Output JSON file path")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be fetched without making requests")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    scraper = CENDOJScraper(dry_run=args.dry_run)

    try:
        all_content: List[SentenceContent] = []

        if args.search or args.search_only:
            jurisdiction = JURISDICTIONS.get(args.jurisdiction, "")

            if args.search_only:
                # Search-only mode: just list results without downloading
                results, total = await scraper.client.search(
                    court=args.court,
                    jurisdiction=jurisdiction,
                    text=args.text,
                    date_from=args.date_from,
                    date_to=args.date_to,
                    page_size=min(args.limit, 50),
                )
                scraper.stats.requests_made += 1
                print(f"\n🔍 Search results: {len(results)} shown / {total} total")
                print(f"{'─' * 70}")
                for i, entry in enumerate(results[:args.limit], 1):
                    print(f"  {i:3d}. {entry.roj or 'N/A':20s} | ref={entry.reference[:20]}... | date={entry.date}")
                    if entry.title:
                        print(f"       {entry.title[:65]}")
                print(f"{'─' * 70}")

                # Save search results if --output
                if args.output:
                    output_data = [asdict(r) for r in results[:args.limit]]
                    Path(args.output).write_text(
                        json.dumps(output_data, ensure_ascii=False, indent=2)
                    )
                    print(f"💾 Saved {len(output_data)} search results to {args.output}")

            else:
                # Full search + download mode
                all_content = await scraper.search_and_download(
                    court=args.court,
                    jurisdiction=jurisdiction,
                    text=args.text,
                    date_from=args.date_from,
                    date_to=args.date_to,
                    limit=args.limit,
                )

        elif args.preset:
            all_content = await scraper.download_preset(args.preset, args.limit)

        elif args.ref:
            if not args.date:
                parser.error("--date is required when using --ref")
            content = await scraper.download_sentence(args.ref, args.date, args.court)
            if content:
                all_content.append(content)

        # Output downloaded sentences
        if all_content:
            print(f"\n📄 Successfully parsed {len(all_content)} sentences:")
            for c in all_content:
                print_sentence_summary(c)

            if args.output:
                output_data = [sentence_to_dict(c) for c in all_content]
                output_path = Path(args.output)
                output_path.write_text(json.dumps(output_data, ensure_ascii=False, indent=2))
                print(f"\n💾 Saved {len(output_data)} sentences to {output_path}")

        scraper.print_stats()

    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
