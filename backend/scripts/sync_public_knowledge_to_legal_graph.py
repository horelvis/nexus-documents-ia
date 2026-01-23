#!/usr/bin/env python3
"""
Sync Public Knowledge to Legal Graph

Migrates existing documents in PublicKnowledge (Weaviate) to legal_law nodes
in Apache AGE. This script should be run once to synchronize historical data.

Features:
- Scans PublicKnowledge for documents with boe_id
- Creates corresponding legal_law nodes in Apache AGE
- Links both via weaviate_uuid field
- Detects and creates law-to-law references
- Idempotent: safe to run multiple times

Usage:
    cd backend
    python scripts/sync_public_knowledge_to_legal_graph.py

    # Options:
    python scripts/sync_public_knowledge_to_legal_graph.py --dry-run    # Preview only
    python scripts/sync_public_knowledge_to_legal_graph.py --limit 10   # Limit documents
    python scripts/sync_public_knowledge_to_legal_graph.py --detect-refs # Also detect references
"""

import asyncio
import argparse
import logging
import re
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'microservices', 'weaviate-service'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Known law short names (same as in boe_legislation.py)
LAW_SHORT_NAMES = {
    "BOE-A-2015-11430": "ET",
    "BOE-A-2020-11043": "LTD",
    "BOE-A-1995-24292": "LPRL",
    "BOE-A-2015-11724": "LISOS",
    "BOE-A-2007-6115": "LOI",
    "BOE-A-2007-13409": "LETA",
    "BOE-A-2015-11723": "LGSS",
    "BOE-A-2018-16673": "LOPDGDD",
    "BOE-A-2003-23186": "LGT",
    "BOE-A-2006-20764": "LIRPF",
    "BOE-A-2014-12328": "LIS",
    "BOE-A-1992-28740": "LIVA",
    "BOE-A-2010-10544": "LSC",
    "BOE-A-1885-6627": "CCom",
    "BOE-A-1889-4763": "CC",
    "BOE-A-2000-323": "LEC",
    "BOE-A-2015-10565": "LPACAP",
    "BOE-A-2015-10566": "LRJSP",
    "BOE-A-2017-12902": "LCSP",
    "BOE-A-2010-6737": "LPBC",
    "BOE-A-1995-25444": "CP",
    "BOE-A-2020-11218": "LC",
    "BOE-A-2019-2364": "LSE",
    "BOE-A-1996-8930": "LPI",
    "BOE-A-2001-23093": "LM",
    "BOE-A-2015-11929": "LP",
    "BOE-A-2007-20555": "LGDCU",
    "BOE-A-1991-628": "LCD",
    "BOE-A-2002-13758": "LSSI",
    "BOE-A-2013-10074": "LE",
    "BOE-A-2022-15818": "LCC",
    "BOE-A-2022-23042": "LS",
    "BOE-A-1994-26003": "LAU",
    "BOE-A-1960-10906": "LPH",
    "BOE-A-1946-2453": "LH",
    "BOE-A-2007-19884": "PGC",
    "BOE-A-2020-17264": "LOMLOE",
    "BOE-A-2001-24515": "LOU",
}


def extract_law_short_name(title: str, boe_id: str) -> str:
    """Extract short name from law title."""
    if boe_id in LAW_SHORT_NAMES:
        return LAW_SHORT_NAMES[boe_id]

    paren_match = re.search(r'\(([A-Z]{2,10})\)', title)
    if paren_match:
        return paren_match.group(1)

    if "Ley" in title:
        words = re.findall(r'\b[A-Z][a-záéíóú]+\b', title)
        if words and len(words) >= 2:
            skip_words = {'Ley', 'Real', 'Decreto', 'Orgánica', 'General', 'De', 'Del', 'La', 'El', 'Los', 'Las'}
            acronym = ''.join([w[0] for w in words if w not in skip_words][:4])
            if len(acronym) >= 2:
                return acronym

    return boe_id.split('-')[-1][:6]


def detect_legal_domain(keywords: list, title: str) -> str:
    """Detect the legal domain from keywords and title."""
    text = " ".join(keywords + [title]).lower()

    domain_rules = [
        ("labor", ["laboral", "trabajador", "trabajo", "empleo", "despido", "salario", "contrato de trabajo", "seguridad social", "prevención de riesgos"]),
        ("privacy", ["protección de datos", "datos personales", "privacidad", "rgpd", "lopdgdd"]),
        ("fiscal", ["tribut", "fiscal", "impuesto", "irpf", "iva", "hacienda", "tributaria"]),
        ("mercantile", ["mercantil", "sociedad", "comercio", "empresa", "competencia", "consumidor"]),
        ("civil", ["civil", "código civil", "enjuiciamiento", "propiedad", "arrendamiento", "hipoteca"]),
        ("administrative", ["administrativ", "procedimiento", "sector público", "contratación pública"]),
        ("compliance", ["blanqueo", "penal", "concursal", "insolvencia", "auditoría", "secretos"]),
        ("intellectual_property", ["propiedad intelectual", "marca", "patente", "autor"]),
        ("commerce", ["consumidor", "comercio minorista", "publicidad"]),
        ("real_estate", ["inmobiliario", "arrendamiento urbano", "propiedad horizontal", "hipotecaria", "vivienda"]),
        ("education", ["educación", "universidad", "enseñanza", "educativ"]),
    ]

    for domain, keywords_list in domain_rules:
        for keyword in keywords_list:
            if keyword in text:
                return domain

    return "general"


def extract_boe_references(content: str) -> list:
    """Extract BOE references from document content."""
    pattern = r'BOE-[A-Z]-\d{4}-\d+'
    references = re.findall(pattern, content)
    return list(set(references))


async def migrate_documents(dry_run: bool = False, limit: int = 1000, detect_refs: bool = False):
    """
    Migrate PublicKnowledge documents to legal_law nodes.

    Args:
        dry_run: If True, only preview changes without writing
        limit: Maximum number of documents to process
        detect_refs: If True, also detect and create law-to-law references
    """
    from app.services.public_knowledge_service import public_knowledge_service
    from app.schemas.public_knowledge import PublicSearchRequest, PublicDocumentCategory
    from app.services.sil.legal_graph_service import (
        legal_graph,
        LegalLaw,
        LegalDomain,
        LawStatus,
    )

    logger.info("=" * 60)
    logger.info("Public Knowledge → Legal Graph Migration")
    logger.info("=" * 60)
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    logger.info(f"Limit: {limit}")
    logger.info(f"Detect references: {detect_refs}")
    logger.info("")

    # Initialize services
    await public_knowledge_service.initialize()
    await legal_graph.initialize()

    # Statistics
    stats = {
        "total_scanned": 0,
        "with_boe_id": 0,
        "already_in_graph": 0,
        "created": 0,
        "updated": 0,
        "references_found": 0,
        "references_created": 0,
        "errors": 0,
    }

    # Search for legislation documents
    search_request = PublicSearchRequest(
        query="*",
        limit=limit,
        categories=[PublicDocumentCategory.LEGISLATION, PublicDocumentCategory.REGULATION],
        search_type="keyword"
    )

    logger.info("🔍 Searching PublicKnowledge for legislation...")
    search_result = await public_knowledge_service.search(search_request)
    stats["total_scanned"] = len(search_result.results)
    logger.info(f"   Found {stats['total_scanned']} documents")

    # Track all BOE IDs for reference detection
    all_boe_ids = set()

    # Process each document
    for doc in search_result.results:
        try:
            boe_id = getattr(doc, 'boe_id', None) or getattr(doc, 'legal_reference', None)

            if not boe_id or not boe_id.startswith("BOE-"):
                continue

            stats["with_boe_id"] += 1
            all_boe_ids.add(boe_id)

            # Check if already exists in graph
            existing = await legal_graph.get_law(boe_id)

            if existing:
                # Check if weaviate_uuid needs updating
                current_uuid = existing.get("weaviate_uuid", "")
                if not current_uuid or current_uuid != doc.id:
                    if dry_run:
                        logger.info(f"   [DRY RUN] Would update weaviate_uuid for {boe_id}")
                    else:
                        await legal_graph.update_law_weaviate_uuid(boe_id, doc.id)
                        logger.info(f"   ✅ Updated weaviate_uuid for {boe_id}")
                    stats["updated"] += 1
                else:
                    stats["already_in_graph"] += 1
                continue

            # Create new legal_law node
            title = doc.title or ""
            keywords = doc.keywords or []

            # Detect domain
            domain_str = detect_legal_domain(keywords, title)
            try:
                domain = LegalDomain(domain_str)
            except ValueError:
                domain = LegalDomain.GENERAL

            # Extract short name
            short_name = extract_law_short_name(title, boe_id)

            # Determine status
            legal_status = getattr(doc, 'legal_status', 'vigente') or 'vigente'
            status = LawStatus.DEROGADA if legal_status == "derogada" else LawStatus.VIGENTE

            law = LegalLaw(
                boe_id=boe_id,
                title=title,
                short_name=short_name,
                domain=domain,
                status=status,
                publication_date=None,
                effective_date=None,
                eli_uri=getattr(doc, 'eli_uri', None),
                summary=title[:500] if title else "",
                keywords=keywords[:10],
                weaviate_uuid=doc.id,
            )

            if dry_run:
                logger.info(f"   [DRY RUN] Would create: {short_name} ({boe_id}) - domain: {domain.value}")
            else:
                success = await legal_graph.add_law(law)
                if success:
                    logger.info(f"   ✅ Created: {short_name} ({boe_id}) - domain: {domain.value}")
                    stats["created"] += 1
                else:
                    logger.warning(f"   ⚠️ Failed to create: {boe_id}")
                    stats["errors"] += 1

        except Exception as e:
            logger.error(f"   ❌ Error processing {doc.id}: {e}")
            stats["errors"] += 1

    # Detect and create law-to-law references
    if detect_refs and not dry_run:
        logger.info("")
        logger.info("🔗 Detecting law-to-law references...")

        for doc in search_result.results:
            try:
                boe_id = getattr(doc, 'boe_id', None) or getattr(doc, 'legal_reference', None)
                if not boe_id or not boe_id.startswith("BOE-"):
                    continue

                content = doc.content or ""
                references = extract_boe_references(content)

                for ref_boe_id in references:
                    if ref_boe_id != boe_id and ref_boe_id in all_boe_ids:
                        stats["references_found"] += 1

                        # Check if reference already exists (would need to query graph)
                        success = await legal_graph.add_law_reference(
                            source_boe_id=boe_id,
                            target_boe_id=ref_boe_id,
                            reference_type="references"
                        )
                        if success:
                            stats["references_created"] += 1
                            logger.info(f"   ✅ Reference: {boe_id} → {ref_boe_id}")

            except Exception as e:
                logger.warning(f"   ⚠️ Error detecting references for {doc.id}: {e}")

    # Print summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("Migration Summary")
    logger.info("=" * 60)
    logger.info(f"  Total scanned:        {stats['total_scanned']}")
    logger.info(f"  With BOE ID:          {stats['with_boe_id']}")
    logger.info(f"  Already in graph:     {stats['already_in_graph']}")
    logger.info(f"  Created:              {stats['created']}")
    logger.info(f"  Updated:              {stats['updated']}")
    if detect_refs:
        logger.info(f"  References found:     {stats['references_found']}")
        logger.info(f"  References created:   {stats['references_created']}")
    logger.info(f"  Errors:               {stats['errors']}")
    logger.info("")

    if dry_run:
        logger.info("⚠️  DRY RUN - No changes were made")
        logger.info("   Run without --dry-run to apply changes")

    return stats


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sync PublicKnowledge documents to Legal Graph in Apache AGE"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum documents to process (default: 1000)"
    )
    parser.add_argument(
        "--detect-refs",
        action="store_true",
        help="Also detect and create law-to-law references"
    )

    args = parser.parse_args()

    try:
        await migrate_documents(
            dry_run=args.dry_run,
            limit=args.limit,
            detect_refs=args.detect_refs
        )
    except KeyboardInterrupt:
        logger.info("\n⚠️  Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
