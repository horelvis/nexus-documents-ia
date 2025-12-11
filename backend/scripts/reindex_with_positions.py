#!/usr/bin/env python3
"""
Weaviate Reindexer with Positions

Reindexes documents with full position information for PDF annotations:
- page_start, page_end: Pages where chunk appears
- char_start, char_end: Character positions in full text
- bbox_start_*, bbox_end_*: Coordinates for PDF annotation

Pipeline:
1. Get documents from PostgreSQL
2. Fetch PDF from GCS
3. Extract text via Apache Tika (high quality)
4. Extract coordinates via PyMuPDF
5. Align text with coordinates (TextAlignmentService)
6. Create positioned chunks (SemanticChunker)
7. Index in Weaviate with position properties

Usage:
    docker compose exec weaviate-service python -m scripts.reindex_with_positions
    docker compose exec weaviate-service python -m scripts.reindex_with_positions --tenant <tenant_id>
    docker compose exec weaviate-service python -m scripts.reindex_with_positions --dry-run
"""

import asyncio
import os
import sys
import logging
import argparse
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

# Add project path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "microservices" / "weaviate-service"))

import httpx
from dataclasses import dataclass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Configuration
API_URL = os.getenv("API_URL", "http://api:8000")
WEAVIATE_SERVICE_URL = os.getenv("WEAVIATE_SERVICE_URL", "http://weaviate-service:8007")
STORAGE_SERVICE_URL = os.getenv("STORAGE_SERVICE_URL", "http://storage-service:8003")
TIKA_URL = os.getenv("TIKA_URL", "http://tika:9998")
MICROSERVICES_API_KEY = os.getenv("MICROSERVICES_API_KEY", "dev_microservice_key_12345")
BATCH_SIZE = int(os.getenv("REINDEX_BATCH_SIZE", "10"))


@dataclass
class DocumentInfo:
    """Document information from API."""
    id: str
    title: str
    filename: str
    file_path: str
    tenant_id: str
    category: Optional[str] = None


class PositionedReindexer:
    """Reindexes documents with position data."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.headers = {
            "Authorization": f"Bearer {MICROSERVICES_API_KEY}",
            "X-API-Key": MICROSERVICES_API_KEY,
            "Content-Type": "application/json"
        }
        self.stats = {
            "documents_processed": 0,
            "documents_indexed": 0,
            "documents_failed": 0,
            "documents_skipped": 0,
            "chunks_created": 0,
        }

    async def check_services(self) -> bool:
        """Check if all required services are available."""
        services = [
            (WEAVIATE_SERVICE_URL, "/health"),
            (TIKA_URL, "/version"),
        ]

        async with httpx.AsyncClient(timeout=10.0) as client:
            for base_url, path in services:
                try:
                    response = await client.get(f"{base_url}{path}")
                    if response.status_code not in [200, 204]:
                        logger.error(f"Service {base_url} returned {response.status_code}")
                        return False
                    logger.info(f"✅ Service {base_url} is healthy")
                except Exception as e:
                    logger.error(f"❌ Service {base_url} not available: {e}")
                    return False

        return True

    async def get_documents(self, tenant_id: str) -> List[DocumentInfo]:
        """Get documents for a tenant from the API."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{API_URL}/api/v1/documents",
                    params={"tenant_id": tenant_id, "limit": 1000},
                    headers=self.headers
                )
                response.raise_for_status()
                data = response.json()

                documents = []
                for doc in data.get("documents", []):
                    documents.append(DocumentInfo(
                        id=doc["id"],
                        title=doc.get("title") or doc.get("filename", "Untitled"),
                        filename=doc.get("filename", ""),
                        file_path=doc.get("file_path", ""),
                        tenant_id=tenant_id,
                        category=doc.get("category"),
                    ))

                return documents

        except Exception as e:
            logger.error(f"Error getting documents: {e}")
            return []

    async def download_pdf(self, tenant_id: str, file_path: str) -> Optional[bytes]:
        """Download PDF from storage service."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(
                    f"{STORAGE_SERVICE_URL}/api/v1/storage/download/{tenant_id}/{file_path}",
                    headers=self.headers
                )
                if response.status_code == 200:
                    return response.content
                else:
                    logger.warning(f"Storage returned {response.status_code} for {file_path}")
                    return None
        except Exception as e:
            logger.error(f"Error downloading {file_path}: {e}")
            return None

    async def extract_text_tika(self, pdf_bytes: bytes, filename: str) -> Optional[str]:
        """Extract text from PDF using Apache Tika."""
        ext = filename.split('.')[-1].lower() if '.' in filename else 'pdf'
        content_types = {
            'pdf': 'application/pdf',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        }
        content_type = content_types.get(ext, 'application/pdf')

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.put(
                    f"{TIKA_URL}/tika",
                    content=pdf_bytes,
                    headers={
                        "Content-Type": content_type,
                        "Accept": "text/plain"
                    }
                )
                response.raise_for_status()
                return response.text.strip()
        except Exception as e:
            logger.error(f"Tika extraction failed: {e}")
            return None

    async def process_document_with_positions(
        self,
        doc: DocumentInfo,
        pdf_bytes: bytes,
        tika_text: str
    ) -> Optional[Dict[str, Any]]:
        """
        Process document through the weaviate-service pipeline with positions.

        This calls the indexing_pipeline.process_file_with_positions() via API.
        """
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                # Use the weaviate-service internal endpoint for positioned indexing
                # Since this is a script, we'll call the pipeline directly
                # via a special endpoint or replicate the logic

                # For now, use the existing index endpoint with position flag
                files = {
                    "file": (doc.filename, pdf_bytes, "application/pdf"),
                }
                data = {
                    "document_id": doc.id,
                    "tenant_id": doc.tenant_id,
                    "title": doc.title,
                    "tika_text": tika_text,  # Pass pre-extracted text
                    "extract_positions": "true",  # Request position extraction
                }

                response = await client.post(
                    f"{WEAVIATE_SERVICE_URL}/weaviate/index-with-positions",
                    files=files,
                    data=data,
                    headers={"Authorization": f"Bearer {MICROSERVICES_API_KEY}"},
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    # Endpoint doesn't exist yet, use fallback
                    logger.warning("Positioned indexing endpoint not available, using fallback")
                    return await self._fallback_index(doc, pdf_bytes, tika_text)
                else:
                    logger.error(f"Indexing failed: {response.status_code} - {response.text}")
                    return None

        except Exception as e:
            logger.error(f"Error processing document {doc.id}: {e}")
            return None

    async def _fallback_index(
        self,
        doc: DocumentInfo,
        pdf_bytes: bytes,
        tika_text: str
    ) -> Optional[Dict[str, Any]]:
        """Fallback indexing when positioned endpoint is not available."""
        # Import services directly
        try:
            from app.services.text_alignment_service import text_alignment_service
            from app.services.rag.semantic_chunker import semantic_chunker
            from app.services.weaviate_service import weaviate_service

            # 1. Align text with coordinates
            alignment_result = text_alignment_service.align_text_with_coordinates(
                pdf_bytes=pdf_bytes,
                tika_text=tika_text,
                use_tika_text=True,
            )

            if not alignment_result.aligned_blocks:
                logger.warning(f"No blocks aligned for {doc.id}")
                return None

            logger.info(
                f"Aligned {len(alignment_result.aligned_blocks)} blocks "
                f"(quality: {alignment_result.alignment_quality:.1%})"
            )

            # 2. Create positioned chunks
            metadata = {
                "title": doc.title,
                "filename": doc.filename,
                "category": doc.category or "general",
            }

            positioned_chunks = semantic_chunker.chunk_document_with_positions(
                aligned_blocks=alignment_result.aligned_blocks,
                metadata=metadata,
            )

            logger.info(f"Created {len(positioned_chunks)} positioned chunks")

            if not positioned_chunks:
                return None

            # 3. Index chunks in Weaviate
            collection_name = f"Nexus_{doc.tenant_id.replace('-', '_')}_documents"

            indexed_count = 0
            for i, chunk in enumerate(positioned_chunks):
                chunk_data = {
                    "id": f"{doc.id}_chunk_{i}",
                    "document_id": doc.id,
                    "title": doc.title,
                    "content": chunk.content,
                    "tenant_id": doc.tenant_id,
                    "document_type": doc.category or "general",
                    # Position properties
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    "bbox_start_x0": chunk.bbox_start[0],
                    "bbox_start_y0": chunk.bbox_start[1],
                    "bbox_start_x1": chunk.bbox_start[2],
                    "bbox_start_y1": chunk.bbox_start[3],
                    "bbox_end_x0": chunk.bbox_end[0],
                    "bbox_end_y0": chunk.bbox_end[1],
                    "bbox_end_x1": chunk.bbox_end[2],
                    "bbox_end_y1": chunk.bbox_end[3],
                }

                if not self.dry_run:
                    try:
                        await weaviate_service.add_document(
                            collection_name=collection_name,
                            document=chunk_data
                        )
                        indexed_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to index chunk {i}: {e}")
                else:
                    indexed_count += 1
                    logger.debug(f"[DRY-RUN] Would index chunk {i}")

            return {
                "document_id": doc.id,
                "chunks_indexed": indexed_count,
                "total_chunks": len(positioned_chunks),
                "alignment_quality": alignment_result.alignment_quality,
            }

        except ImportError as e:
            logger.error(f"Import error (run inside weaviate-service container): {e}")
            return None
        except Exception as e:
            logger.error(f"Fallback indexing error: {e}")
            return None

    async def reindex_tenant(self, tenant_id: str, recreate: bool = True):
        """Reindex all documents for a tenant with positions."""
        logger.info(f"{'='*60}")
        logger.info(f"Processing tenant: {tenant_id}")

        # Get documents
        documents = await self.get_documents(tenant_id)
        if not documents:
            logger.info(f"No documents found for tenant {tenant_id}")
            return

        logger.info(f"Found {len(documents)} documents to process")

        # Optionally recreate collection
        if recreate and not self.dry_run:
            collection_name = f"Nexus_{tenant_id.replace('-', '_')}_documents"
            logger.info(f"Recreating collection: {collection_name}")
            # Delete and recreate collection via API
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    await client.delete(
                        f"{WEAVIATE_SERVICE_URL}/weaviate/collections/{collection_name}",
                        headers=self.headers
                    )
                    await client.post(
                        f"{WEAVIATE_SERVICE_URL}/weaviate/collections/{collection_name}/create",
                        json={},
                        headers=self.headers
                    )
            except Exception as e:
                logger.warning(f"Collection recreation failed: {e}")

        # Process documents
        for i, doc in enumerate(documents, 1):
            logger.info(f"[{i}/{len(documents)}] Processing: {doc.title or doc.filename}")

            # Download PDF
            pdf_bytes = await self.download_pdf(tenant_id, doc.file_path)
            if not pdf_bytes:
                logger.warning(f"Could not download PDF for {doc.id}")
                self.stats["documents_skipped"] += 1
                continue

            # Extract text with Tika
            tika_text = await self.extract_text_tika(pdf_bytes, doc.filename)
            if not tika_text:
                logger.warning(f"Could not extract text for {doc.id}")
                self.stats["documents_skipped"] += 1
                continue

            logger.info(f"  Extracted {len(tika_text)} chars via Tika")

            # Process with positions
            result = await self.process_document_with_positions(doc, pdf_bytes, tika_text)

            if result:
                self.stats["documents_indexed"] += 1
                self.stats["chunks_created"] += result.get("chunks_indexed", 0)
                logger.info(
                    f"  ✅ Indexed {result.get('chunks_indexed', 0)} chunks "
                    f"(quality: {result.get('alignment_quality', 0):.1%})"
                )
            else:
                self.stats["documents_failed"] += 1
                logger.error(f"  ❌ Failed to index")

            self.stats["documents_processed"] += 1

            # Small delay to avoid overwhelming services
            if i % 5 == 0:
                await asyncio.sleep(0.5)

    async def run(self, tenant_id: Optional[str] = None, recreate: bool = True):
        """Run the reindexing process."""
        if self.dry_run:
            logger.info("DRY-RUN MODE - No changes will be made")

        # Check services
        if not await self.check_services():
            logger.error("Required services not available")
            return

        if tenant_id:
            await self.reindex_tenant(tenant_id, recreate)
        else:
            # Get all tenants from API
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(
                        f"{API_URL}/api/v1/tenants",
                        headers=self.headers
                    )
                    if response.status_code == 200:
                        tenants = response.json().get("tenants", [])
                        for tenant in tenants:
                            await self.reindex_tenant(tenant["id"], recreate)
                    else:
                        logger.error(f"Could not get tenants: {response.status_code}")
            except Exception as e:
                logger.error(f"Error getting tenants: {e}")

        # Print summary
        logger.info("=" * 60)
        logger.info("REINDEX COMPLETE")
        logger.info(f"  Documents processed: {self.stats['documents_processed']}")
        logger.info(f"  Documents indexed: {self.stats['documents_indexed']}")
        logger.info(f"  Documents failed: {self.stats['documents_failed']}")
        logger.info(f"  Documents skipped: {self.stats['documents_skipped']}")
        logger.info(f"  Chunks created: {self.stats['chunks_created']}")


async def main():
    parser = argparse.ArgumentParser(description="Reindex documents with position data")
    parser.add_argument("--tenant", type=str, help="Specific tenant ID to reindex")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--no-recreate", action="store_true", help="Don't recreate collections")
    args = parser.parse_args()

    reindexer = PositionedReindexer(dry_run=args.dry_run)

    try:
        await reindexer.run(
            tenant_id=args.tenant,
            recreate=not args.no_recreate
        )
    except KeyboardInterrupt:
        logger.info("Reindex interrupted by user")
    except Exception as e:
        logger.exception(f"Reindex failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
