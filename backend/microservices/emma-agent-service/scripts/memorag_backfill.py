#!/usr/bin/env python3
"""Backfill MemoRAG memory from existing documents.

Usage:
    docker compose exec emma-agent-service python scripts/memorag_backfill.py \\
        --tenant-id <TENANT> \\
        --input-file /tmp/doc_ids.txt

    docker compose exec emma-agent-service python scripts/memorag_backfill.py \\
        --tenant-id <TENANT> \\
        --document-ids doc-1,doc-2,doc-3
"""

import argparse
import asyncio
import logging
from typing import List

import httpx

from app.core.config import settings
from app.services.memorag import get_memorag_service

logger = logging.getLogger(__name__)


def _parse_ids(value: str) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _read_ids(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


async def _fetch_document_content(client: httpx.AsyncClient, tenant_id: str, document_id: str) -> dict:
    response = await client.get(
        f"{settings.weaviate_service_url}/documents/{tenant_id}/{document_id}/content",
        headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
    )
    if response.status_code != 200:
        raise RuntimeError(f"content fetch failed ({response.status_code})")
    return response.json()


async def _run(args: argparse.Namespace) -> int:
    doc_ids: List[str] = []
    if args.document_ids:
        doc_ids.extend(_parse_ids(args.document_ids))
    if args.input_file:
        doc_ids.extend(_read_ids(args.input_file))
    doc_ids = list(dict.fromkeys(doc_ids))

    if not doc_ids:
        logger.error("No document IDs provided. Use --document-ids or --input-file.")
        return 1

    memorag = get_memorag_service()

    success = 0
    failed = 0

    async with httpx.AsyncClient(timeout=60.0) as client:
        for idx, document_id in enumerate(doc_ids, start=1):
            try:
                data = await _fetch_document_content(client, args.tenant_id, document_id)
                content = data.get("content") or ""
                filename = data.get("title") or ""
                if not content:
                    raise RuntimeError("empty content")

                result = await memorag.memorize(
                    tenant_id=args.tenant_id,
                    document_id=document_id,
                    document_text=content,
                    filename=filename,
                    domain=args.domain or "",
                    semantic_type=args.semantic_type or "",
                )
                if result.get("success"):
                    success += 1
                    logger.info(f"[{idx}/{len(doc_ids)}] memorized {document_id}")
                else:
                    failed += 1
                    logger.warning(f"[{idx}/{len(doc_ids)}] failed {document_id}: {result.get('error')}")
            except Exception as e:
                failed += 1
                logger.warning(f"[{idx}/{len(doc_ids)}] failed {document_id}: {e}")

            if args.sleep_ms > 0:
                await asyncio.sleep(args.sleep_ms / 1000.0)

    logger.info(f"Backfill complete: success={success} failed={failed}")
    return 0 if failed == 0 else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill MemoRAG memory from existing documents.")
    parser.add_argument("--tenant-id", required=True, help="Tenant ID")
    parser.add_argument("--document-ids", default="", help="Comma-separated document IDs")
    parser.add_argument("--input-file", default="", help="File with one document_id per line")
    parser.add_argument("--domain", default="", help="Optional domain override")
    parser.add_argument("--semantic-type", default="", help="Optional semantic_type override")
    parser.add_argument("--sleep-ms", type=int, default=0, help="Delay between docs (ms)")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
