"""
Legal Reference Extractor

Extracts cross-references between Spanish laws from BOE document text:
- BOE identifiers (BOE-A-2015-11430)
- Article references (Art. 54 del ET)
- Law references (Ley 3/2012, de 6 de julio)
- Modifications ("modificado por...")
- Derogations ("derogado por...")

Also enriches with BOE /analisis API for posterior references.

Usage:
    from app.services.knowledge.legal_reference_extractor import legal_reference_extractor

    refs = await legal_reference_extractor.extract(
        text=law_text,
        boe_id="BOE-A-2015-11430"
    )
    # refs.cited_boe_ids, refs.article_refs, refs.modifications, refs.derogations
"""

import re
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ArticleRef:
    """Reference to a specific article in a law."""
    article_number: str  # e.g., "54", "34.1", "54 bis"
    law_name: Optional[str] = None  # e.g., "ET", "Ley 3/2012"
    context_snippet: str = ""


@dataclass
class Modification:
    """A modification relationship between laws."""
    modifying_text: str  # The raw matched text
    modifying_law: Optional[str] = None  # Parsed law name
    articles_affected: List[str] = field(default_factory=list)
    modification_type: str = "modification"  # modification, addition, new_wording


@dataclass
class Derogation:
    """A derogation relationship."""
    derogating_text: str
    derogating_law: Optional[str] = None
    partial: bool = False
    articles_affected: List[str] = field(default_factory=list)


@dataclass
class LegalReferences:
    """All extracted legal references from a document."""
    boe_id: str
    cited_boe_ids: List[str] = field(default_factory=list)
    article_refs: List[ArticleRef] = field(default_factory=list)
    law_refs: List[str] = field(default_factory=list)
    modifications: List[Modification] = field(default_factory=list)
    derogations: List[Derogation] = field(default_factory=list)

    @property
    def total_references(self) -> int:
        return (
            len(self.cited_boe_ids)
            + len(self.article_refs)
            + len(self.law_refs)
            + len(self.modifications)
            + len(self.derogations)
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "boe_id": self.boe_id,
            "cited_boe_ids": self.cited_boe_ids,
            "article_refs_count": len(self.article_refs),
            "law_refs": self.law_refs,
            "modifications_count": len(self.modifications),
            "derogations_count": len(self.derogations),
            "total_references": self.total_references,
        }


@dataclass
class BOEAnalysis:
    """Result from BOE /analisis API enrichment."""
    posterior_references: List[Dict[str, str]] = field(default_factory=list)
    anterior_references: List[Dict[str, str]] = field(default_factory=list)
    materias: List[str] = field(default_factory=list)


class LegalReferenceExtractor:
    """Extract legal cross-references from BOE document text."""

    # Regex patterns
    BOE_ID_PATTERN = re.compile(r'BOE-[A-Z]-\d{4}-\d+')

    ARTICLE_PATTERN = re.compile(
        r'[Aa]rt(?:ículo)?\.?\s*(\d+(?:\.\d+)?(?:\s*(?:bis|ter|quater|quinquies|sexies|septies|octies))?)',
        re.UNICODE,
    )

    # Capture "del ET", "de la LPRL", "del Estatuto de los Trabajadores" after article ref
    ARTICLE_LAW_PATTERN = re.compile(
        r'[Aa]rt(?:ículo)?\.?\s*(\d+(?:\.\d+)?(?:\s*(?:bis|ter|quater))?)'
        r'\s+(?:del?|de\s+la)\s+([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ\s]{1,60})',
        re.UNICODE,
    )

    LAW_REF_PATTERN = re.compile(
        r'(?:Ley(?:\s+Orgánica)?|Real\s+Decreto(?:-ley)?|Decreto(?:-ley)?)'
        r'[^,\.;]{5,80}'
        r'(?:de\s+\d{1,2}\s+de\s+\w+(?:\s+de\s+\d{4})?)',
        re.UNICODE,
    )

    MODIFICATION_PATTERNS = [
        (re.compile(r'modificad[oa]\s+por\s+(.{10,100}?)(?:\.|,|;)', re.UNICODE), "modification"),
        (re.compile(r'según\s+(?:la\s+)?redacción\s+(?:dada|introducida)\s+por\s+(.{10,100}?)(?:\.|,|;)', re.UNICODE), "new_wording"),
        (re.compile(r'añadid[oa]\s+por\s+(.{10,100}?)(?:\.|,|;)', re.UNICODE), "addition"),
        (re.compile(r'introducid[oa]\s+por\s+(.{10,100}?)(?:\.|,|;)', re.UNICODE), "addition"),
    ]

    DEROGATION_PATTERNS = [
        re.compile(r'derogad[oa]\s+por\s+(.{10,100}?)(?:\.|,|;)', re.UNICODE),
        re.compile(r'queda(?:n)?\s+(?:sin\s+efecto|derogad[oa]s?)', re.UNICODE),
        re.compile(r'se\s+suprime(?:n)?', re.UNICODE),
        re.compile(r'deja(?:n)?\s+de\s+estar\s+vigente', re.UNICODE),
    ]

    BOE_API_BASE = "https://www.boe.es/datosabiertos/api"

    async def extract(self, text: str, boe_id: str) -> LegalReferences:
        """
        Extract all legal references from document text.

        Args:
            text: Full document text
            boe_id: BOE identifier of the source document

        Returns:
            LegalReferences with all detected cross-references
        """
        refs = LegalReferences(boe_id=boe_id)

        # 1. Extract cited BOE IDs (exclude self)
        cited_ids = set(self.BOE_ID_PATTERN.findall(text))
        cited_ids.discard(boe_id)
        refs.cited_boe_ids = sorted(cited_ids)

        # 2. Extract article references with law context
        for match in self.ARTICLE_LAW_PATTERN.finditer(text):
            article_num = match.group(1).strip()
            law_name = match.group(2).strip()
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            refs.article_refs.append(ArticleRef(
                article_number=article_num,
                law_name=law_name,
                context_snippet=text[start:end].strip(),
            ))

        # Also get standalone article refs (without law context)
        standalone_articles = set()
        for match in self.ARTICLE_PATTERN.finditer(text):
            standalone_articles.add(match.group(1).strip())

        # 3. Extract law references
        law_refs = set()
        for match in self.LAW_REF_PATTERN.finditer(text):
            law_refs.add(match.group(0).strip())
        refs.law_refs = sorted(law_refs)

        # 4. Extract modifications
        for pattern, mod_type in self.MODIFICATION_PATTERNS:
            for match in pattern.finditer(text):
                modifying_text = match.group(0).strip()
                modifying_law = match.group(1).strip() if match.lastindex >= 1 else None

                # Try to find affected articles nearby (within 200 chars before the match)
                context_before = text[max(0, match.start() - 200):match.start()]
                affected = [m.group(1) for m in self.ARTICLE_PATTERN.finditer(context_before)]

                refs.modifications.append(Modification(
                    modifying_text=modifying_text,
                    modifying_law=modifying_law,
                    articles_affected=affected[-3:],  # Last 3 articles mentioned
                    modification_type=mod_type,
                ))

        # 5. Extract derogations
        for pattern in self.DEROGATION_PATTERNS:
            for match in pattern.finditer(text):
                derogating_text = match.group(0).strip()
                derogating_law = match.group(1).strip() if match.lastindex and match.lastindex >= 1 else None

                # Check if partial (article-level) derogation
                context_before = text[max(0, match.start() - 200):match.start()]
                affected = [m.group(1) for m in self.ARTICLE_PATTERN.finditer(context_before)]
                partial = len(affected) > 0

                refs.derogations.append(Derogation(
                    derogating_text=derogating_text,
                    derogating_law=derogating_law,
                    partial=partial,
                    articles_affected=affected[-3:],
                ))

        logger.info(
            f"[{boe_id}] Extracted legal references: "
            f"{len(refs.cited_boe_ids)} BOE IDs, "
            f"{len(refs.article_refs)} article refs, "
            f"{len(refs.law_refs)} law refs, "
            f"{len(refs.modifications)} modifications, "
            f"{len(refs.derogations)} derogations"
        )

        return refs

    async def enrich_from_boe_api(self, boe_id: str) -> BOEAnalysis:
        """
        Fetch BOE /analisis endpoint for posterior/anterior references.

        Args:
            boe_id: BOE identifier

        Returns:
            BOEAnalysis with references from the API
        """
        import xml.etree.ElementTree as ET

        result = BOEAnalysis()
        url = f"{self.BOE_API_BASE}/legislacion-consolidada/id/{boe_id}/analisis"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers={"Accept": "application/xml"})
                if response.status_code != 200:
                    logger.warning(f"BOE /analisis returned {response.status_code} for {boe_id}")
                    return result

                root = ET.fromstring(response.text)

                # Extract posterior references (laws that modify this one)
                for ref in root.findall('.//referencias_posteriores/referencia'):
                    ref_data = {}
                    for child in ref:
                        if child.text:
                            ref_data[child.tag] = child.text
                    if ref_data:
                        result.posterior_references.append(ref_data)

                # Extract anterior references (laws this one modifies)
                for ref in root.findall('.//referencias_anteriores/referencia'):
                    ref_data = {}
                    for child in ref:
                        if child.text:
                            ref_data[child.tag] = child.text
                    if ref_data:
                        result.anterior_references.append(ref_data)

                # Extract materias
                for materia in root.findall('.//materias/materia'):
                    if materia.text:
                        result.materias.append(materia.text)

                logger.info(
                    f"[{boe_id}] BOE /analisis: "
                    f"{len(result.posterior_references)} posterior refs, "
                    f"{len(result.anterior_references)} anterior refs"
                )

        except Exception as e:
            logger.warning(f"Failed to fetch BOE /analisis for {boe_id}: {e}")

        return result


# Global singleton
legal_reference_extractor = LegalReferenceExtractor()
