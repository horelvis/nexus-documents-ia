#!/usr/bin/env python3
"""
Connect Orphan Laws

Adds logical REFERENCES connections between orphan laws and hub laws
based on actual legal domain relationships.

Run from weaviate-service container:
    cd /app && python scripts/connect_orphan_laws.py
"""

import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Domain-specific connections based on legal relationships
# Format: (source_boe_id, target_boe_id, relationship_type, context)
ORPHAN_CONNECTIONS = [
    # LGSS (Ley General de la Seguridad Social) - connects to labor law hub
    ("BOE-A-2015-11723", "BOE-A-2015-11700", "REFERENCES",
     "LGSS complementa el Estatuto de los Trabajadores en materia de cotizaciones"),

    # LISOS (Ley sobre Infracciones y Sanciones en el Orden Social)
    ("BOE-A-2015-11724", "BOE-A-2015-11700", "REFERENCES",
     "LISOS tipifica infracciones laborales del ET"),
    ("BOE-A-2015-11724", "BOE-A-2015-11723", "REFERENCES",
     "LISOS sanciona incumplimientos de la LGSS"),

    # LSP (Ley de Sociedades Profesionales) - connects to mercantile hub
    ("BOE-A-2007-5909", "BOE-A-2010-10544", "REFERENCES",
     "LSP como forma especial de sociedad, complementa la LSC"),
    ("BOE-A-2007-5909", "BOE-A-1885-6627", "REFERENCES",
     "LSP regula sociedades en marco del Código de Comercio"),

    # LP (Ley de Patentes) - IP domain
    ("BOE-A-2015-11929", "BOE-A-2001-23093", "REFERENCES",
     "LP y LM conforman el sistema de propiedad industrial"),
    ("BOE-A-2015-11929", "BOE-A-1885-6627", "REFERENCES",
     "LP regula activos intangibles mercantiles"),

    # LM (Ley de Marcas) - IP domain
    ("BOE-A-2001-23093", "BOE-A-1885-6627", "REFERENCES",
     "LM protege signos distintivos en el comercio"),

    # CP (Código Penal) - compliance hub
    ("BOE-A-1995-25444", "BOE-A-1889-4763", "REFERENCES",
     "CP complementa responsabilidad civil del CC"),
    ("BOE-A-1995-25444", "BOE-A-2010-10544", "REFERENCES",
     "CP art.31bis tipifica responsabilidad penal de personas jurídicas (LSC)"),

    # LC (Ley Concursal) - mercantile/compliance
    ("BOE-A-2020-11218", "BOE-A-2010-10544", "REFERENCES",
     "LC regula insolvencia de sociedades de capital"),
    ("BOE-A-2020-11218", "BOE-A-1885-6627", "REFERENCES",
     "LC complementa obligaciones mercantiles del CCom"),
    ("BOE-A-2020-11218", "BOE-A-1889-4763", "REFERENCES",
     "LC afecta obligaciones civiles reguladas en el CC"),

    # RD Infantil (Real Decreto educación infantil) - education
    ("BOE-A-2022-2296", "BOE-A-2006-7899", "REFERENCES",
     "RD Infantil desarrolla primera etapa educativa de la LOE"),
    ("BOE-A-2022-2296", "BOE-A-2020-17264", "REFERENCES",
     "RD Infantil se adapta a modificaciones de la LOMLOE"),
]


async def connect_orphans():
    """Add REFERENCES connections for orphan laws."""
    from app.services.sil.legal_graph_service import legal_graph

    await legal_graph.initialize()

    logger.info("🔗 Connecting orphan laws to hub laws...")

    success_count = 0
    skip_count = 0
    error_count = 0

    for source_boe, target_boe, rel_type, context in ORPHAN_CONNECTIONS:
        try:
            # Check if source and target exist
            result = await legal_graph.add_reference(
                source_boe_id=source_boe,
                target_boe_id=target_boe,
                relationship_type=rel_type,
                context_snippet=context,
            )

            if result:
                logger.info(f"  ✅ {source_boe} -{rel_type}-> {target_boe}")
                success_count += 1
            else:
                logger.info(f"  ⏭️ {source_boe} -{rel_type}-> {target_boe} (exists or failed)")
                skip_count += 1

        except Exception as e:
            logger.error(f"  ❌ {source_boe} → {target_boe}: {e}")
            error_count += 1

    logger.info(f"\n📊 Results:")
    logger.info(f"   ✅ Created: {success_count}")
    logger.info(f"   ⏭️ Skipped: {skip_count}")
    logger.info(f"   ❌ Errors: {error_count}")

    # Verify by getting stats
    stats = await legal_graph.get_graph_stats()
    logger.info(f"\n📈 Updated Graph Stats:")
    logger.info(f"   Total laws: {stats.get('total_laws', 0)}")
    logger.info(f"   Total edges: {stats.get('total_edges', 0)}")


async def verify_connections():
    """Verify no more orphans exist."""
    from collections import defaultdict
    from app.services.sil.legal_graph_service import legal_graph

    await legal_graph.initialize()
    graph = await legal_graph.get_graph_structure()
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    connections = defaultdict(int)
    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src:
            connections[src] += 1
        if tgt:
            connections[tgt] += 1

    orphans = [
        node.get("id") for node in nodes
        if connections.get(node.get("id"), 0) == 0
    ]

    if orphans:
        logger.warning(f"\n⚠️ Still {len(orphans)} orphan laws:")
        for boe_id in orphans:
            logger.warning(f"   - {boe_id}")
    else:
        logger.info("\n✅ All laws are now connected!")

    return orphans


async def main():
    logger.info("=" * 60)
    logger.info("🔗 ORPHAN LAW CONNECTION SCRIPT")
    logger.info("=" * 60)

    await connect_orphans()
    await verify_connections()


if __name__ == "__main__":
    asyncio.run(main())
