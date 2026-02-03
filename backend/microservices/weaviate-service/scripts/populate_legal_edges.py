#!/usr/bin/env python3
"""
Populate Legal Graph Edges

Fetches the BOE /analisis API for each law in the graph and creates
REFERENCES, MODIFIES, and DEROGATES edges between laws that both exist
in the graph.

Usage:
    python scripts/populate_legal_edges.py
    python scripts/populate_legal_edges.py --dry-run
"""

import asyncio
import argparse
import logging
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.sil.legal_graph_service import legal_graph

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BOE_API_BASE = "https://www.boe.es/datosabiertos/api"


async def fetch_boe_analysis(boe_id: str) -> dict:
    """
    Fetch BOE /analisis API for a single law.

    BOE XML structure:
        <anteriores>
            <anterior>
                <id_norma>BOE-A-2014-2219</id_norma>
                <relacion>DEROGA</relacion>
                <texto>Disposición transitoria 2...</texto>
            </anterior>
        </anteriores>
        <posteriores>
            <posterior>
                <id_norma>BOE-A-2021-21788</id_norma>
                <relacion>SE DEROGA</relacion>
                <texto>el art. 12.3...</texto>
            </posterior>
        </posteriores>
    """
    result = {"posterior": [], "anterior": []}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{BOE_API_BASE}/legislacion-consolidada/id/{boe_id}/analisis"
            response = await client.get(url, headers={"Accept": "application/xml"})
            if response.status_code != 200:
                url = f"{BOE_API_BASE}/legislacion/id/{boe_id}/analisis"
                response = await client.get(url, headers={"Accept": "application/xml"})
                if response.status_code != 200:
                    return result

            root = ET.fromstring(response.content)

            for ref in root.findall('.//anterior'):
                data = {c.tag: c.text for c in ref if c.text}
                if data.get("id_norma"):
                    result["anterior"].append(data)

            for ref in root.findall('.//posterior'):
                data = {c.tag: c.text for c in ref if c.text}
                if data.get("id_norma"):
                    result["posterior"].append(data)

    except Exception as e:
        logger.warning(f"  Failed to fetch BOE /analisis for {boe_id}: {e}")

    return result


def classify_relation(relacion: str) -> str:
    """Map BOE relacion field to our edge type."""
    r = (relacion or "").upper()
    if "DEROGA" in r:
        return "DEROGATES"
    if "MODIFICA" in r or "AÑADE" in r or "NUEVA REDACCIÓN" in r:
        return "MODIFIES"
    return "REFERENCES"


async def populate_edges(dry_run: bool = False) -> None:
    """Populate edges between laws using BOE /analisis API."""

    logger.info("🚀 Starting legal graph edge population...")

    await legal_graph.initialize()

    all_laws = await legal_graph.get_all_laws()
    if not all_laws:
        logger.error("No laws found in graph. Run seed_legal_graph.py first.")
        return

    boe_ids_in_graph = {law["boe_id"] for law in all_laws}
    short_names = {law["boe_id"]: law.get("short_name", law["boe_id"]) for law in all_laws}
    logger.info(f"📊 Found {len(boe_ids_in_graph)} laws in graph")

    edges_created = 0
    edges_skipped = 0

    for law in all_laws:
        boe_id = law["boe_id"]
        sn = short_names.get(boe_id, boe_id)
        logger.info(f"📖 Processing {sn} ({boe_id})...")

        analysis = await fetch_boe_analysis(boe_id)

        # Posterior = laws that act ON this law (modify/derogate this law)
        for ref in analysis["posterior"]:
            ref_id = ref["id_norma"]
            if ref_id in boe_ids_in_graph:
                rel_type = classify_relation(ref.get("relacion", ""))
                texto = (ref.get("texto", "") or "")[:200]
                ref_sn = short_names.get(ref_id, ref_id)
                if dry_run:
                    logger.info(f"  [DRY] {ref_sn} --{rel_type}--> {sn} ({texto[:60]})")
                else:
                    if await legal_graph.add_reference(ref_id, boe_id, rel_type, context_snippet=texto):
                        edges_created += 1
                    else:
                        edges_skipped += 1
            else:
                edges_skipped += 1

        # Anterior = laws this law acts on (references/modifies/derogates)
        for ref in analysis["anterior"]:
            ref_id = ref["id_norma"]
            if ref_id in boe_ids_in_graph:
                rel_type = classify_relation(ref.get("relacion", ""))
                texto = (ref.get("texto", "") or "")[:200]
                ref_sn = short_names.get(ref_id, ref_id)
                if dry_run:
                    logger.info(f"  [DRY] {sn} --{rel_type}--> {ref_sn} ({texto[:60]})")
                else:
                    if await legal_graph.add_reference(boe_id, ref_id, rel_type, context_snippet=texto):
                        edges_created += 1
                    else:
                        edges_skipped += 1
            else:
                edges_skipped += 1

        await asyncio.sleep(0.3)

    logger.info(f"✅ Done! Created {edges_created} edges, skipped {edges_skipped}")

    stats = await legal_graph.get_graph_stats()
    logger.info(f"📊 Graph stats: {stats}")


async def main():
    parser = argparse.ArgumentParser(description="Populate legal graph edges from BOE API")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created")
    args = parser.parse_args()
    await populate_edges(dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
